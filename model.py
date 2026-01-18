import base64
from concurrent.futures import ThreadPoolExecutor
import logging
import math
import mmap
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import MDAnalysis as mda
from MDAnalysis.exceptions import NoDataError

from pdb_writer import write_pdb

logger = logging.getLogger(__name__)

CHARGE_SCALE = 18.2223
_PARM7_DESCRIPTIONS: Optional[Dict[str, str]] = None
_PARM7_DEPRECATED: Optional[set] = None


@dataclass(frozen=True)
class ResidueMeta:
    resid: int
    resname: str
    segid: Optional[str] = None
    chain: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "resid": self.resid,
            "resname": self.resname,
            "segid": self.segid,
            "chain": self.chain,
        }


@dataclass(frozen=True)
class AtomMeta:
    serial: int
    atom_name: str
    element: Optional[str]
    residue: ResidueMeta
    residue_index: int
    coords: Tuple[float, float, float]
    parm7: Dict[str, Optional[object]]

    def to_dict(self) -> Dict[str, object]:
        return {
            "serial": self.serial,
            "atom_name": self.atom_name,
            "element": self.element,
            "residue": self.residue.to_dict(),
            "coords": {"x": self.coords[0], "y": self.coords[1], "z": self.coords[2]},
            "parm7": self.parm7,
        }


@dataclass(frozen=True)
class Parm7Token:
    value: str
    line: int
    start: int
    end: int


@dataclass(frozen=True)
class Parm7Section:
    name: str
    count: int
    width: int
    flag_line: int
    end_line: int
    tokens: List[Parm7Token]


class ModelError(Exception):
    def __init__(self, code: str, message: str, details: Optional[object] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_result(self) -> Dict[str, object]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


def _parse_int_tokens(tokens: List[Parm7Token]) -> List[int]:
    values: List[int] = []
    for token in tokens:
        raw = token.value.strip()
        if not raw:
            values.append(0)
            continue
        try:
            values.append(int(raw))
        except ValueError:
            try:
                values.append(int(float(raw)))
            except ValueError:
                logger.debug("Failed to parse int token: %s", raw)
                values.append(0)
    return values


def _parse_float_tokens(tokens: List[Parm7Token]) -> List[float]:
    values: List[float] = []
    for token in tokens:
        raw = token.value.strip()
        if not raw:
            values.append(0.0)
            continue
        raw = raw.replace("D", "E").replace("d", "e")
        try:
            values.append(float(raw))
        except ValueError:
            logger.debug("Failed to parse float token: %s", raw)
            values.append(0.0)
    return values


def _parse_int_values(values: List[str]) -> List[int]:
    parsed: List[int] = []
    for raw in values:
        text = (raw or "").strip()
        if not text:
            parsed.append(0)
            continue
        try:
            parsed.append(int(text))
        except ValueError:
            try:
                parsed.append(int(float(text)))
            except ValueError:
                parsed.append(0)
    return parsed


def _parse_float_values(values: List[str]) -> List[float]:
    parsed: List[float] = []
    for raw in values:
        text = (raw or "").strip()
        if not text:
            parsed.append(0.0)
            continue
        text = text.replace("D", "E").replace("d", "e")
        try:
            parsed.append(float(text))
        except ValueError:
            parsed.append(0.0)
    return parsed


def _parse_int_token_value(token: Parm7Token) -> int:
    raw = token.value.strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        try:
            return int(float(raw))
        except ValueError:
            return 0


def _parse_float_token_value(token: Parm7Token) -> float:
    raw = token.value.strip()
    if not raw:
        return 0.0
    raw = raw.replace("D", "E").replace("d", "e")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _build_lj_by_type(
    atom_type_indices: List[int],
    nonbond_index: List[int],
    acoef_values: List[float],
    bcoef_values: List[float],
) -> Dict[int, Dict[str, float]]:
    lj_by_type: Dict[int, Dict[str, float]] = {}
    ntypes = 0
    if nonbond_index:
        matrix_size = int(round(math.sqrt(len(nonbond_index))))
        if matrix_size * matrix_size == len(nonbond_index):
            ntypes = matrix_size
    if not ntypes and atom_type_indices:
        ntypes = max(atom_type_indices)
    if not ntypes:
        return lj_by_type
    for type_index in range(1, ntypes + 1):
        offset = (type_index - 1) * ntypes + (type_index - 1)
        if offset >= len(nonbond_index):
            continue
        pair_index = nonbond_index[offset]
        if pair_index <= 0:
            continue
        pair_offset = pair_index - 1
        if pair_offset >= len(acoef_values) or pair_offset >= len(bcoef_values):
            continue
        acoef = acoef_values[pair_offset]
        bcoef = bcoef_values[pair_offset]
        if acoef <= 0.0 or bcoef <= 0.0:
            continue
        epsilon = (bcoef * bcoef) / (4.0 * acoef)
        rmin = pow(2.0 * acoef / bcoef, 1.0 / 6.0)
        lj_by_type[type_index] = {
            "rmin": rmin,
            "epsilon": epsilon,
            "acoef": acoef,
            "bcoef": bcoef,
            "pair_index": int(pair_index),
        }
    return lj_by_type


def _build_lj_by_type_from_tokens(
    atom_type_indices: List[int],
    nonbond_tokens: List[Parm7Token],
    acoef_tokens: List[Parm7Token],
    bcoef_tokens: List[Parm7Token],
) -> Dict[int, Dict[str, float]]:
    lj_by_type: Dict[int, Dict[str, float]] = {}
    if not atom_type_indices:
        return lj_by_type
    ntypes = max(atom_type_indices)
    if ntypes <= 0:
        return lj_by_type
    for type_index in range(1, ntypes + 1):
        offset = (type_index - 1) * ntypes + (type_index - 1)
        if offset >= len(nonbond_tokens):
            continue
        pair_index = _parse_int_token_value(nonbond_tokens[offset])
        if pair_index <= 0:
            continue
        pair_offset = pair_index - 1
        if pair_offset >= len(acoef_tokens) or pair_offset >= len(bcoef_tokens):
            continue
        acoef = _parse_float_token_value(acoef_tokens[pair_offset])
        bcoef = _parse_float_token_value(bcoef_tokens[pair_offset])
        if acoef <= 0.0 or bcoef <= 0.0:
            continue
        epsilon = (bcoef * bcoef) / (4.0 * acoef)
        rmin = pow(2.0 * acoef / bcoef, 1.0 / 6.0)
        lj_by_type[type_index] = {
            "rmin": rmin,
            "epsilon": epsilon,
            "acoef": acoef,
            "bcoef": bcoef,
            "pair_index": int(pair_index),
        }
    return lj_by_type


def compute_lj_tables(
    atom_type_values: List[str],
    nonbond_values: List[str],
    acoef_values: List[str],
    bcoef_values: List[str],
) -> Dict[str, object]:
    atom_type_indices = _parse_int_values(atom_type_values)
    nonbond_index = _parse_int_values(nonbond_values)
    acoef = _parse_float_values(acoef_values)
    bcoef = _parse_float_values(bcoef_values)
    lj_by_type = _build_lj_by_type(atom_type_indices, nonbond_index, acoef, bcoef)
    return {"atom_type_indices": atom_type_indices, "lj_by_type": lj_by_type}


def _timed_call(fn: Callable[..., object], *args: object, **kwargs: object):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


def _load_parm7_descriptions() -> Dict[str, str]:
    global _PARM7_DESCRIPTIONS
    if _PARM7_DESCRIPTIONS is not None:
        return _PARM7_DESCRIPTIONS
    ref_path = os.path.join(os.path.dirname(__file__), "daux", "src_parm7_ref.md")
    if not os.path.exists(ref_path):
        _PARM7_DESCRIPTIONS = {}
        return _PARM7_DESCRIPTIONS
    descriptions: Dict[str, str] = {}
    current_flag = None
    capturing = False
    buffer: List[str] = []
    with open(ref_path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    for line in lines:
        flag_match = re.search(r"\*\*Flag:\*\*\s*`%FLAG\s+([A-Z0-9_]+)`", line)
        if flag_match:
            if current_flag and buffer:
                text = " ".join(buffer)
                descriptions[current_flag] = re.sub(r"\\s+", " ", text).strip()
            current_flag = flag_match.group(1)
            capturing = False
            buffer = []
            continue
        if current_flag and "**Contents:**" in line:
            content = line.split("**Contents:**", 1)[1].strip()
            if content:
                buffer.append(content)
            capturing = True
            continue
        if capturing:
            if not line.strip():
                if current_flag and buffer:
                    text = " ".join(buffer)
                    descriptions[current_flag] = re.sub(r"\\s+", " ", text).strip()
                capturing = False
                buffer = []
                continue
            if line.startswith("## "):
                if current_flag and buffer:
                    text = " ".join(buffer)
                    descriptions[current_flag] = re.sub(r"\\s+", " ", text).strip()
                capturing = False
                buffer = []
                continue
            buffer.append(line.strip())
    if current_flag and buffer:
        text = " ".join(buffer)
        descriptions[current_flag] = re.sub(r"\\s+", " ", text).strip()
    _PARM7_DESCRIPTIONS = descriptions
    return _PARM7_DESCRIPTIONS


def _load_parm7_deprecated_flags() -> set:
    global _PARM7_DEPRECATED
    if _PARM7_DEPRECATED is not None:
        return _PARM7_DEPRECATED
    ref_path = os.path.join(os.path.dirname(__file__), "daux", "src_parm7_ref.md")
    if not os.path.exists(ref_path):
        _PARM7_DEPRECATED = set()
        return _PARM7_DEPRECATED
    with open(ref_path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    deprecated: set = set()
    current_flags: List[str] = []
    found_deprecated = False

    def flush_flags():
        nonlocal current_flags, found_deprecated
        if current_flags and found_deprecated:
            deprecated.update(current_flags)
        current_flags = []
        found_deprecated = False

    for line in lines:
        flag_names = re.findall(r"%FLAG\s+([A-Z0-9_]+)", line)
        if flag_names:
            flush_flags()
            current_flags = flag_names
            if "deprecated" in line.lower():
                found_deprecated = True
            continue
        if current_flags and line.startswith("## "):
            flush_flags()
            continue
        if current_flags and "deprecated" in line.lower():
            found_deprecated = True
    flush_flags()
    explicit_add = {"HBCUT", "JOIN_ARRAY", "IROTAT", "IPOL"}
    explicit_remove = {"POINTERS", "BOX_DIMENSIONS"}
    _PARM7_DEPRECATED = (deprecated | explicit_add) - explicit_remove
    return _PARM7_DEPRECATED


def _guess_element(atom_name: str) -> Optional[str]:
    name = (atom_name or "").strip()
    if not name:
        return None
    i = 0
    while i < len(name) and name[i].isdigit():
        i += 1
    name = name[i:]
    if not name:
        return None
    upper = name[:2].upper()
    two_letter = {
        "CL",
        "BR",
        "NA",
        "MG",
        "ZN",
        "FE",
        "CA",
        "LI",
        "SI",
        "AL",
        "CU",
        "MN",
        "CO",
        "NI",
        "CD",
        "HG",
        "PB",
        "AG",
        "AU",
    }
    if upper in two_letter:
        return upper[0] + upper[1].lower()
    if len(name) > 1 and name[1].islower():
        return name[0].upper() + name[1].lower()
    return name[0].upper()


def _safe_attr(atoms, attr: str) -> Optional[List[object]]:
    try:
        values = getattr(atoms, attr)
    except (AttributeError, NoDataError):
        return None
    try:
        return list(values)
    except Exception:
        return None


class Model:
    def __init__(self, cpu_submit: Optional[Callable[..., object]] = None) -> None:
        self._lock = threading.Lock()
        self._meta_by_serial: Dict[int, AtomMeta] = {}
        self._meta_list: List[AtomMeta] = []
        self._residue_keys_by_resid: Dict[int, List[str]] = {}
        self._residue_index: Dict[str, List[int]] = {}
        self._parm7_text_b64: Optional[str] = None
        self._parm7_sections: Dict[str, Parm7Section] = {}
        self._int_section_cache: Dict[str, List[int]] = {}
        self._float_section_cache: Dict[str, List[float]] = {}
        self._loaded = False
        self._cpu_submit = cpu_submit

    def _parse_parm7(self, path: str) -> Tuple[str, Dict[str, Parm7Section]]:
        with open(path, "rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                text = mm.read().decode("utf-8", errors="replace")
        lines = text.splitlines()
        sections: Dict[str, Parm7Section] = {}

        fmt_re = re.compile(r"%FORMAT\((\d+)([a-zA-Z])(\d+)(?:\.(\d+))?\)")
        token_sections = {
            "ATOM_NAME",
            "CHARGE",
            "ATOMIC_NUMBER",
            "MASS",
            "ATOM_TYPE_INDEX",
            "AMBER_ATOM_TYPE",
            "RESIDUE_LABEL",
            "RESIDUE_POINTER",
            "BONDS_INC_HYDROGEN",
            "BONDS_WITHOUT_HYDROGEN",
            "BOND_FORCE_CONSTANT",
            "BOND_EQUIL_VALUE",
            "ANGLES_INC_HYDROGEN",
            "ANGLES_WITHOUT_HYDROGEN",
            "ANGLE_FORCE_CONSTANT",
            "ANGLE_EQUIL_VALUE",
            "DIHEDRALS_INC_HYDROGEN",
            "DIHEDRALS_WITHOUT_HYDROGEN",
            "DIHEDRAL_FORCE_CONSTANT",
            "DIHEDRAL_PERIODICITY",
            "DIHEDRAL_PHASE",
            "SCEE_SCALE_FACTOR",
            "SCNB_SCALE_FACTOR",
            "NONBONDED_PARM_INDEX",
            "LENNARD_JONES_ACOEF",
            "LENNARD_JONES_BCOEF",
            "HBOND_ACOEF",
            "HBOND_BCOEF",
            "HBCUT",
        }
        current_name: Optional[str] = None
        current_count = 0
        current_width = 0
        current_tokens: List[Parm7Token] = []
        current_flag_line = 0
        collect_tokens = False

        def finalize_section(end_line: int):
            if current_name:
                sections[current_name] = Parm7Section(
                    name=current_name,
                    count=current_count,
                    width=current_width,
                    flag_line=current_flag_line,
                    end_line=end_line,
                    tokens=list(current_tokens),
                )

        for idx, line in enumerate(lines):
            if line.startswith("%FLAG"):
                if current_name is not None:
                    finalize_section(idx - 1)
                parts = line.split()
                current_name = parts[1] if len(parts) > 1 else None
                current_count = 0
                current_width = 0
                current_tokens = []
                current_flag_line = idx
                collect_tokens = bool(current_name and current_name in token_sections)
                continue
            if line.startswith("%FORMAT"):
                match = fmt_re.search(line)
                if match:
                    current_count = int(match.group(1))
                    current_width = int(match.group(3))
                continue
            if collect_tokens and current_name and current_count and current_width:
                for slot in range(current_count):
                    start = slot * current_width
                    end = start + current_width
                    if start >= len(line):
                        break
                    raw = line[start:end]
                    if not raw.strip():
                        continue
                    current_tokens.append(
                        Parm7Token(
                            value=raw,
                            line=idx,
                            start=start,
                            end=min(end, len(line)),
                        )
                    )

        if current_name is not None:
            finalize_section(len(lines) - 1)
        return text, sections

    def get_parm7_text(self) -> Dict[str, object]:
        with self._lock:
            if not self._loaded or not self._parm7_text_b64:
                raise ModelError("not_loaded", "No parm7 text loaded")
            return {"ok": True, "parm7_text_b64": self._parm7_text_b64}

    def get_parm7_sections(self) -> Dict[str, object]:
        with self._lock:
            if not self._loaded or not self._parm7_sections:
                raise ModelError("not_loaded", "No parm7 sections available")
            descriptions = _load_parm7_descriptions()
            deprecated_flags = _load_parm7_deprecated_flags()
            sections = [
                {
                    "name": section.name,
                    "line": section.flag_line,
                    "end_line": section.end_line,
                    "description": descriptions.get(section.name, ""),
                    "deprecated": section.name in deprecated_flags,
                }
                for section in self._parm7_sections.values()
            ]
        sections.sort(key=lambda item: item["line"])
        return {"ok": True, "sections": sections}

    def _build_parm7_highlights(
        self, meta: AtomMeta, sections: Dict[str, Parm7Section]
    ) -> List[Dict[str, object]]:
        highlights: List[Dict[str, object]] = []
        per_atom_sections = [
            "ATOM_NAME",
            "CHARGE",
            "ATOMIC_NUMBER",
            "MASS",
            "ATOM_TYPE_INDEX",
            "AMBER_ATOM_TYPE",
        ]
        for name in per_atom_sections:
            section = sections.get(name)
            if not section:
                continue
            index = meta.serial - 1
            if 0 <= index < len(section.tokens):
                token = section.tokens[index]
                highlights.append(
                    {"line": token.line, "start": token.start, "end": token.end, "section": name}
                )

        residue_sections = ["RESIDUE_LABEL", "RESIDUE_POINTER"]
        residue_index = meta.residue_index - 1
        for name in residue_sections:
            section = sections.get(name)
            if not section:
                continue
            if 0 <= residue_index < len(section.tokens):
                token = section.tokens[residue_index]
                highlights.append(
                    {"line": token.line, "start": token.start, "end": token.end, "section": name}
                )
        return highlights

    def _get_int_section(self, name: str, section: Parm7Section) -> List[int]:
        cached = self._int_section_cache.get(name)
        if cached is not None:
            return cached
        values = _parse_int_tokens(section.tokens)
        self._int_section_cache[name] = values
        return values

    def _get_float_section(self, name: str, section: Parm7Section) -> List[float]:
        cached = self._float_section_cache.get(name)
        if cached is not None:
            return cached
        values = _parse_float_tokens(section.tokens)
        self._float_section_cache[name] = values
        return values

    @staticmethod
    def _pointer_to_serial(value: int) -> int:
        return abs(value) // 3 + 1

    @staticmethod
    def _match_triplet(a: int, b: int, c: int, serials: Sequence[int]) -> bool:
        if len(serials) < 3:
            return False
        return (a == serials[0] and b == serials[1] and c == serials[2]) or (
            a == serials[2] and b == serials[1] and c == serials[0]
        )

    @staticmethod
    def _match_quad(a: int, b: int, c: int, d: int, serials: Sequence[int]) -> bool:
        if len(serials) < 4:
            return False
        return (a, b, c, d) == tuple(serials[:4]) or (d, c, b, a) == tuple(serials[:4])

    def _add_highlight(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        section: Parm7Section,
        token_index: int,
    ) -> None:
        if token_index < 0 or token_index >= len(section.tokens):
            return
        token = section.tokens[token_index]
        key = (token.line, token.start, token.end)
        if key in seen:
            return
        seen.add(key)
        highlights.append(
            {"line": token.line, "start": token.start, "end": token.end, "section": section.name}
        )

    def _add_param_highlight(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        sections: Dict[str, Parm7Section],
        section_name: str,
        param_index: int,
    ) -> None:
        if param_index <= 0:
            return
        section = sections.get(section_name)
        if not section:
            return
        self._add_highlight(highlights, seen, section, param_index - 1)

    def _get_param_value(
        self,
        sections: Dict[str, Parm7Section],
        section_name: str,
        param_index: int,
    ) -> Optional[float]:
        if param_index <= 0:
            return None
        section = sections.get(section_name)
        if not section:
            return None
        values = self._get_float_section(section_name, section)
        index = param_index - 1
        if index < 0 or index >= len(values):
            return None
        return values[index]

    def _get_ntypes(
        self, sections: Dict[str, Parm7Section], values: Sequence[int]
    ) -> Optional[int]:
        if not values:
            return None
        ntypes = int(math.sqrt(len(values)))
        if ntypes > 0 and ntypes * ntypes == len(values):
            return ntypes
        acoef_section = sections.get("LENNARD_JONES_ACOEF")
        if not acoef_section:
            return None
        acoef_count = len(acoef_section.tokens)
        if acoef_count <= 0:
            return None
        estimate = int((math.sqrt(8 * acoef_count + 1) - 1) / 2)
        if estimate > 0 and estimate * (estimate + 1) // 2 == acoef_count:
            return estimate
        return None

    def _nonbond_index(
        self, values: Sequence[int], ntypes: int, type_a: int, type_b: int
    ) -> Optional[Tuple[int, int]]:
        idx = (type_a - 1) * ntypes + (type_b - 1)
        if idx < 0 or idx >= len(values):
            return None
        return idx, int(values[idx])

    def _extract_bond_params(
        self, sections: Dict[str, Parm7Section], serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 2:
            return []
        target = {int(serials[0]), int(serials[1])}
        results: List[Dict[str, object]] = []
        for name in ("BONDS_INC_HYDROGEN", "BONDS_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 2, 3):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                if {atom_a, atom_b} != target:
                    continue
                param_index = abs(values[idx + 2])
                results.append(
                    {
                        "serials": [atom_a, atom_b],
                        "param_index": param_index,
                        "force_constant": self._get_param_value(
                            sections, "BOND_FORCE_CONSTANT", param_index
                        ),
                        "equil_value": self._get_param_value(
                            sections, "BOND_EQUIL_VALUE", param_index
                        ),
                    }
                )
        return results

    def _extract_angle_params(
        self, sections: Dict[str, Parm7Section], serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 3:
            return []
        results: List[Dict[str, object]] = []
        for name in ("ANGLES_INC_HYDROGEN", "ANGLES_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 3, 4):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                atom_c = self._pointer_to_serial(values[idx + 2])
                if not self._match_triplet(atom_a, atom_b, atom_c, serials):
                    continue
                param_index = abs(values[idx + 3])
                results.append(
                    {
                        "serials": [atom_a, atom_b, atom_c],
                        "param_index": param_index,
                        "force_constant": self._get_param_value(
                            sections, "ANGLE_FORCE_CONSTANT", param_index
                        ),
                        "equil_value": self._get_param_value(
                            sections, "ANGLE_EQUIL_VALUE", param_index
                        ),
                    }
                )
        return results

    def _extract_dihedral_params(
        self, sections: Dict[str, Parm7Section], serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 4:
            return []
        results: List[Dict[str, object]] = []
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                if not self._match_quad(atom_i, atom_j, atom_k, atom_l, serials):
                    continue
                param_index = abs(raw_param)
                results.append(
                    {
                        "serials": [atom_i, atom_j, atom_k, atom_l],
                        "param_index": param_index,
                        "force_constant": self._get_param_value(
                            sections, "DIHEDRAL_FORCE_CONSTANT", param_index
                        ),
                        "periodicity": self._get_param_value(
                            sections, "DIHEDRAL_PERIODICITY", param_index
                        ),
                        "phase": self._get_param_value(
                            sections, "DIHEDRAL_PHASE", param_index
                        ),
                        "scee": self._get_param_value(
                            sections, "SCEE_SCALE_FACTOR", param_index
                        ),
                        "scnb": self._get_param_value(
                            sections, "SCNB_SCALE_FACTOR", param_index
                        ),
                    }
                )
        return results

    def _extract_14_params(
        self, sections: Dict[str, Parm7Section], serials: Sequence[int]
    ) -> List[Dict[str, object]]:
        if len(serials) < 2:
            return []
        target = {int(serials[0]), int(serials[1])}
        results: List[Dict[str, object]] = []
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                if raw_k < 0 or raw_l < 0:
                    continue
                atom_i = self._pointer_to_serial(raw_i)
                atom_l = self._pointer_to_serial(raw_l)
                if {atom_i, atom_l} != target:
                    continue
                param_index = abs(raw_param)
                results.append(
                    {
                        "serials": [atom_i, atom_l],
                        "param_index": param_index,
                        "scee": self._get_param_value(
                            sections, "SCEE_SCALE_FACTOR", param_index
                        ),
                        "scnb": self._get_param_value(
                            sections, "SCNB_SCALE_FACTOR", param_index
                        ),
                    }
                )
        return results

    def _extract_nonbonded_params(
        self,
        sections: Dict[str, Parm7Section],
        meta_by_serial: Dict[int, AtomMeta],
        serials: Sequence[int],
    ) -> Optional[Dict[str, object]]:
        if len(serials) < 2:
            return None
        meta_a = meta_by_serial.get(int(serials[0]))
        meta_b = meta_by_serial.get(int(serials[1]))
        if not meta_a or not meta_b:
            return None
        type_a = meta_a.parm7.get("atom_type_index")
        type_b = meta_b.parm7.get("atom_type_index")
        if not type_a or not type_b:
            return None
        section = sections.get("NONBONDED_PARM_INDEX")
        if not section or not section.tokens:
            return None
        values = self._get_int_section("NONBONDED_PARM_INDEX", section)
        if not values:
            return None
        ntypes = self._get_ntypes(sections, values)
        if not ntypes:
            return None
        primary = self._nonbond_index(values, ntypes, int(type_a), int(type_b))
        secondary = self._nonbond_index(values, ntypes, int(type_b), int(type_a))
        nb_index = primary[1] if primary else 0
        if nb_index == 0 and secondary:
            nb_index = secondary[1]
        acoef = None
        bcoef = None
        rmin = None
        epsilon = None
        if nb_index > 0:
            acoef = self._get_param_value(sections, "LENNARD_JONES_ACOEF", nb_index)
            bcoef = self._get_param_value(sections, "LENNARD_JONES_BCOEF", nb_index)
            if acoef and bcoef:
                epsilon = (bcoef * bcoef) / (4.0 * acoef)
                rmin = pow(2.0 * acoef / bcoef, 1.0 / 6.0)
        return {
            "serials": [int(serials[0]), int(serials[1])],
            "type_indices": [int(type_a), int(type_b)],
            "nb_index": nb_index,
            "acoef": acoef,
            "bcoef": bcoef,
            "rmin": rmin,
            "epsilon": epsilon,
        }

    def _highlight_nonbonded_pair(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        sections: Dict[str, Parm7Section],
        meta_by_serial: Dict[int, AtomMeta],
        serials: Sequence[int],
        pairs: Optional[Sequence[Sequence[int]]] = None,
    ) -> None:
        if len(serials) < 2 and not pairs:
            return
        section = sections.get("NONBONDED_PARM_INDEX")
        if not section or not section.tokens:
            return
        values = self._get_int_section("NONBONDED_PARM_INDEX", section)
        if not values:
            return
        ntypes = self._get_ntypes(sections, values)
        if not ntypes:
            return
        serial_pairs = pairs or [serials[:2]]
        nb_indices: set = set()
        for pair in serial_pairs:
            if len(pair) < 2:
                continue
            meta_a = meta_by_serial.get(int(pair[0]))
            meta_b = meta_by_serial.get(int(pair[1]))
            if not meta_a or not meta_b:
                continue
            type_a = meta_a.parm7.get("atom_type_index")
            type_b = meta_b.parm7.get("atom_type_index")
            if not type_a or not type_b:
                continue
            candidates = [
                self._nonbond_index(values, ntypes, int(type_a), int(type_b)),
                self._nonbond_index(values, ntypes, int(type_b), int(type_a)),
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                idx, nb_index = candidate
                self._add_highlight(highlights, seen, section, idx)
                if nb_index != 0:
                    nb_indices.add(nb_index)
        for nb_index in nb_indices:
            if nb_index > 0:
                self._add_param_highlight(
                    highlights, seen, sections, "LENNARD_JONES_ACOEF", nb_index
                )
                self._add_param_highlight(
                    highlights, seen, sections, "LENNARD_JONES_BCOEF", nb_index
                )
            else:
                hb_index = abs(nb_index)
                self._add_param_highlight(
                    highlights, seen, sections, "HBOND_ACOEF", hb_index
                )
                self._add_param_highlight(
                    highlights, seen, sections, "HBOND_BCOEF", hb_index
                )
                hbc_section = sections.get("HBCUT")
                if hbc_section and hbc_section.tokens:
                    self._add_highlight(highlights, seen, hbc_section, 0)

    def _highlight_bond_entries(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        sections: Dict[str, Parm7Section],
        serials: Sequence[int],
    ) -> None:
        if len(serials) < 2:
            return
        target = {int(serials[0]), int(serials[1])}
        for name in ("BONDS_INC_HYDROGEN", "BONDS_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 2, 3):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                if {atom_a, atom_b} != target:
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                param_index = abs(values[idx + 2])
                self._add_param_highlight(
                    highlights, seen, sections, "BOND_FORCE_CONSTANT", param_index
                )
                self._add_param_highlight(
                    highlights, seen, sections, "BOND_EQUIL_VALUE", param_index
                )

    def _highlight_angle_entries(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        sections: Dict[str, Parm7Section],
        serials: Sequence[int],
    ) -> None:
        if len(serials) < 3:
            return
        for name in ("ANGLES_INC_HYDROGEN", "ANGLES_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 3, 4):
                atom_a = self._pointer_to_serial(values[idx])
                atom_b = self._pointer_to_serial(values[idx + 1])
                atom_c = self._pointer_to_serial(values[idx + 2])
                if not self._match_triplet(atom_a, atom_b, atom_c, serials):
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                param_index = abs(values[idx + 3])
                self._add_param_highlight(
                    highlights, seen, sections, "ANGLE_FORCE_CONSTANT", param_index
                )
                self._add_param_highlight(
                    highlights, seen, sections, "ANGLE_EQUIL_VALUE", param_index
                )

    def _highlight_dihedral_entries(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        sections: Dict[str, Parm7Section],
        serials: Sequence[int],
        require_14: Optional[bool] = None,
    ) -> None:
        if len(serials) < 4:
            return
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                atom_i = self._pointer_to_serial(raw_i)
                atom_j = self._pointer_to_serial(raw_j)
                atom_k = self._pointer_to_serial(raw_k)
                atom_l = self._pointer_to_serial(raw_l)
                if require_14 is not None:
                    if require_14 and (raw_k < 0 or raw_l < 0):
                        continue
                    if not require_14 and raw_k < 0:
                        continue
                if not self._match_quad(atom_i, atom_j, atom_k, atom_l, serials):
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                self._add_highlight(highlights, seen, section, idx + 4)
                param_index = abs(raw_param)
                for param_section in (
                    "DIHEDRAL_FORCE_CONSTANT",
                    "DIHEDRAL_PERIODICITY",
                    "DIHEDRAL_PHASE",
                    "SCEE_SCALE_FACTOR",
                    "SCNB_SCALE_FACTOR",
                ):
                    self._add_param_highlight(
                        highlights, seen, sections, param_section, param_index
                    )

    def _highlight_14_pairs(
        self,
        highlights: List[Dict[str, object]],
        seen: set,
        sections: Dict[str, Parm7Section],
        serials: Sequence[int],
    ) -> None:
        if len(serials) < 2:
            return
        target = {int(serials[0]), int(serials[1])}
        for name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
            section = sections.get(name)
            if not section or not section.tokens:
                continue
            values = self._get_int_section(name, section)
            for idx in range(0, len(values) - 4, 5):
                raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
                if raw_k < 0 or raw_l < 0:
                    continue
                atom_i = self._pointer_to_serial(raw_i)
                atom_l = self._pointer_to_serial(raw_l)
                if {atom_i, atom_l} != target:
                    continue
                self._add_highlight(highlights, seen, section, idx)
                self._add_highlight(highlights, seen, section, idx + 1)
                self._add_highlight(highlights, seen, section, idx + 2)
                self._add_highlight(highlights, seen, section, idx + 3)
                self._add_highlight(highlights, seen, section, idx + 4)
                param_index = abs(raw_param)
                for param_section in ("SCEE_SCALE_FACTOR", "SCNB_SCALE_FACTOR"):
                    self._add_param_highlight(
                        highlights, seen, sections, param_section, param_index
                    )

    def get_parm7_highlights(
        self, serials: Sequence[int], mode: Optional[str] = None
    ) -> Dict[str, object]:
        with self._lock:
            if not self._loaded:
                raise ModelError("not_loaded", "No system loaded")
            sections = dict(self._parm7_sections)
            meta_by_serial = self._meta_by_serial
            if not sections:
                raise ModelError("not_loaded", "No parm7 sections available")

            if not serials:
                return {"ok": True, "highlights": []}
            highlights: List[Dict[str, object]] = []
            seen: set = set()
            missing: List[str] = []
            for serial in serials:
                try:
                    serial_int = int(serial)
                except (TypeError, ValueError):
                    missing.append(str(serial))
                    continue
                meta = meta_by_serial.get(serial_int)
                if meta is None:
                    missing.append(str(serial))
                    continue
                for hl in self._build_parm7_highlights(meta, sections):
                    key = (hl["line"], hl["start"], hl["end"])
                    if key in seen:
                        continue
                    seen.add(key)
                    highlights.append(hl)
            if missing:
                raise ModelError(
                    "not_found", f"Atom serial(s) {', '.join(missing)} not found"
                )
            normalized_mode = (mode or "Atom").strip()
            interaction: Optional[Dict[str, object]] = None
            if normalized_mode == "Bond":
                self._highlight_bond_entries(highlights, seen, sections, serials)
                interaction = {
                    "mode": normalized_mode,
                    "bonds": self._extract_bond_params(sections, serials),
                }
            elif normalized_mode == "Angle":
                self._highlight_angle_entries(highlights, seen, sections, serials)
                interaction = {
                    "mode": normalized_mode,
                    "angles": self._extract_angle_params(sections, serials),
                }
            elif normalized_mode == "Dihedral":
                self._highlight_dihedral_entries(highlights, seen, sections, serials)
                interaction = {
                    "mode": normalized_mode,
                    "dihedrals": self._extract_dihedral_params(sections, serials),
                }
            elif normalized_mode == "1-4 Nonbonded":
                one_four = self._extract_14_params(sections, serials)
                pair_serials = [entry["serials"] for entry in one_four] if one_four else None
                self._highlight_14_pairs(highlights, seen, sections, serials)
                self._highlight_nonbonded_pair(
                    highlights,
                    seen,
                    sections,
                    meta_by_serial,
                    serials,
                    pairs=pair_serials,
                )
                interaction = {
                    "mode": normalized_mode,
                    "one_four": one_four,
                    "nonbonded": self._extract_nonbonded_params(
                        sections,
                        meta_by_serial,
                        pair_serials[0] if pair_serials else serials,
                    ),
                }
            elif normalized_mode == "Non-bonded":
                self._highlight_nonbonded_pair(
                    highlights, seen, sections, meta_by_serial, serials
                )
                interaction = {
                    "mode": normalized_mode,
                    "nonbonded": self._extract_nonbonded_params(
                        sections, meta_by_serial, serials
                    ),
                }
            return {
                "ok": True,
                "highlights": highlights,
                "interaction": interaction,
            }

    def get_atom_bundle(self, serial: int) -> Dict[str, object]:
        with self._lock:
            if not self._loaded:
                raise ModelError("not_loaded", "No system loaded")
            meta = self._meta_by_serial.get(int(serial))
            sections = dict(self._parm7_sections)
        if meta is None:
            raise ModelError("not_found", f"Atom serial {serial} not found")
        if not sections:
            raise ModelError("not_loaded", "No parm7 sections available")
        highlights = self._build_parm7_highlights(meta, sections)
        return {"ok": True, "atom": meta.to_dict(), "highlights": highlights}

    def load_system(self, parm7_path: str, rst7_path: str) -> Dict[str, object]:
        if not parm7_path or not rst7_path:
            raise ModelError("invalid_input", "parm7 and rst7 paths are required")
        if not os.path.exists(parm7_path):
            raise ModelError("file_not_found", "parm7 file not found", parm7_path)
        if not os.path.exists(rst7_path):
            raise ModelError("file_not_found", "rst7 file not found", rst7_path)

        total_start = time.perf_counter()
        logger.debug("Loading MDAnalysis Universe and parm7")
        universe_time = 0.0
        parm7_time = 0.0
        with ThreadPoolExecutor(max_workers=2) as executor:
            universe_future = executor.submit(
                _timed_call, mda.Universe, parm7_path, rst7_path, format="RESTRT"
            )
            parm7_future = executor.submit(_timed_call, self._parse_parm7, parm7_path)
            try:
                universe, universe_time = universe_future.result()
            except Exception as exc:
                parm7_future.cancel()
                logger.exception("MDAnalysis load failed")
                raise ModelError(
                    "load_failed", "Failed to load MDAnalysis Universe", str(exc)
                )
            try:
                (parm7_text, parm7_sections), parm7_time = parm7_future.result()
            except Exception as exc:
                logger.exception("Failed to parse parm7 file")
                raise ModelError(
                    "parm7_parse_failed", "Failed to parse parm7 file", str(exc)
                )

        parm7_text_b64 = base64.b64encode(parm7_text.encode("utf-8")).decode("ascii")

        charge_section = parm7_sections.get("CHARGE")
        charges = _safe_attr(universe.atoms, "charges")
        masses = _safe_attr(universe.atoms, "masses")
        types = _safe_attr(universe.atoms, "types")

        warnings: List[str] = []
        if charges is None:
            warnings.append("Atom charges not available in topology")
        if masses is None:
            warnings.append("Atom masses not available in topology")
        if types is None:
            warnings.append("Atom types not available in topology")
        if warnings:
            logger.debug("Topology warnings: %s", warnings)

        atom_type_index_section = parm7_sections.get("ATOM_TYPE_INDEX")
        nonbond_index_section = parm7_sections.get("NONBONDED_PARM_INDEX")
        acoef_section = parm7_sections.get("LENNARD_JONES_ACOEF")
        bcoef_section = parm7_sections.get("LENNARD_JONES_BCOEF")

        lj_start = time.perf_counter()
        atom_type_indices: List[int] = []
        lj_by_type: Dict[int, Dict[str, float]] = {}
        if atom_type_index_section:
            atom_type_indices = _parse_int_tokens(atom_type_index_section.tokens)
        if (
            atom_type_indices
            and nonbond_index_section
            and acoef_section
            and bcoef_section
        ):
            lj_by_type = _build_lj_by_type_from_tokens(
                atom_type_indices,
                nonbond_index_section.tokens,
                acoef_section.tokens,
                bcoef_section.tokens,
            )
        lj_time = time.perf_counter() - lj_start

        meta_list: List[AtomMeta] = []
        meta_by_serial: Dict[int, AtomMeta] = {}
        residue_keys_by_resid: Dict[int, List[str]] = {}
        residue_index_map: Dict[str, List[int]] = {}

        atoms = universe.atoms
        natoms = len(atoms)
        names = _safe_attr(atoms, "names") or [atom.name for atom in atoms]
        resids = _safe_attr(atoms, "resids") or [atom.residue.resid for atom in atoms]
        resnames = _safe_attr(atoms, "resnames") or [
            atom.residue.resname for atom in atoms
        ]
        resindices = _safe_attr(atoms, "resindices") or [
            atom.residue.ix for atom in atoms
        ]
        segids = _safe_attr(atoms, "segids")
        chains = _safe_attr(atoms, "chainIDs")
        elements = _safe_attr(atoms, "elements")
        positions = atoms.positions

        meta_start = time.perf_counter()
        for idx in range(natoms):
            serial = idx + 1
            resid = int(resids[idx])
            resname = str(resnames[idx]).strip()
            residue_serial_index = int(resindices[idx]) + 1
            segid = segids[idx] if segids is not None else None
            chain = chains[idx] if chains is not None else None
            residue_meta = ResidueMeta(
                resid=resid, resname=resname, segid=segid, chain=chain
            )

            element = elements[idx] if elements is not None else None
            if element:
                element = str(element).strip().title()
            else:
                element = _guess_element(str(names[idx]))

            atom_type = types[idx] if types is not None else None
            atom_type_index = None
            lj_rmin = None
            lj_epsilon = None
            lj_acoef = None
            lj_bcoef = None
            lj_pair_index = None
            if atom_type_indices and idx < len(atom_type_indices):
                atom_type_index = atom_type_indices[idx]
                if atom_type_index and atom_type_index in lj_by_type:
                    lj_entry = lj_by_type[atom_type_index]
                    lj_rmin = lj_entry.get("rmin")
                    lj_epsilon = lj_entry.get("epsilon")
                    lj_acoef = lj_entry.get("acoef")
                    lj_bcoef = lj_entry.get("bcoef")
                    lj_pair_index = lj_entry.get("pair_index")
            charge = charges[idx] if charges is not None else None
            charge_raw_str = None
            charge_e = None
            if charge_section and idx < len(charge_section.tokens):
                charge_raw_str = charge_section.tokens[idx].value.strip()
                try:
                    charge_raw_val = float(charge_raw_str)
                    charge_e = charge_raw_val / CHARGE_SCALE
                except ValueError:
                    charge_e = None
            if charge_e is None and charge is not None:
                try:
                    charge_e = float(charge)
                except (TypeError, ValueError):
                    charge_e = None
            mass = masses[idx] if masses is not None else None

            coords = (
                float(positions[idx][0]),
                float(positions[idx][1]),
                float(positions[idx][2]),
            )
            parm7 = {
                "atom_type": str(atom_type).strip() if atom_type is not None else None,
                "atom_type_index": atom_type_index,
                "charge": charge_e,
                "charge_raw": charge_raw_str,
                "charge_e": charge_e,
                "charge_mdanalysis": float(charge) if charge is not None else None,
                "mass": float(mass) if mass is not None else None,
                "lj_rmin": lj_rmin,
                "lj_epsilon": lj_epsilon,
                "lj_a_coef": lj_acoef,
                "lj_b_coef": lj_bcoef,
                "lj_pair_index": lj_pair_index,
            }

            meta = AtomMeta(
                serial=serial,
                atom_name=str(names[idx]).strip(),
                element=element,
                residue=residue_meta,
                residue_index=residue_serial_index,
                coords=coords,
                parm7=parm7,
            )

            meta_list.append(meta)
            meta_by_serial[serial] = meta

            residue_key = f"{segid or ''}:{resid}:{resname}"
            residue_index_map.setdefault(residue_key, []).append(serial)
            residue_keys_by_resid.setdefault(resid, []).append(residue_key)

        meta_time = time.perf_counter() - meta_start
        pdb_start = time.perf_counter()
        pdb_text = write_pdb(meta_list)
        pdb_time = time.perf_counter() - pdb_start
        pdb_b64 = base64.b64encode(pdb_text.encode("ascii")).decode("ascii")

        with self._lock:
            self._meta_list = meta_list
            self._meta_by_serial = meta_by_serial
            self._residue_index = residue_index_map
            self._residue_keys_by_resid = residue_keys_by_resid
            self._parm7_text_b64 = parm7_text_b64
            self._parm7_sections = parm7_sections
            self._int_section_cache = {}
            self._float_section_cache = {}
            self._loaded = True

        total_time = time.perf_counter() - total_start
        logger.debug(
            "System loaded: atoms=%d residues=%d",
            len(meta_list),
            len(universe.residues),
        )
        logger.debug(
            "Timings: universe=%.3fs parm7=%.3fs lj=%.3fs meta=%.3fs pdb=%.3fs total=%.3fs",
            universe_time,
            parm7_time,
            lj_time,
            meta_time,
            pdb_time,
            total_time,
        )

        return {
            "ok": True,
            "pdb_b64": pdb_b64,
            "natoms": len(meta_list),
            "nresidues": len(universe.residues),
            "warnings": warnings,
        }

    def get_atom_info(self, serial: int) -> Dict[str, object]:
        with self._lock:
            if not self._loaded:
                raise ModelError("not_loaded", "No system loaded")
            meta = self._meta_by_serial.get(int(serial))
        if meta is None:
            raise ModelError("not_found", f"Atom serial {serial} not found")
        logger.debug("Atom info requested serial=%s", serial)
        return {"ok": True, "atom": meta.to_dict()}

    def query_atoms(
        self, filters: Dict[str, object], max_results: int = 50000
    ) -> Dict[str, object]:
        if filters is None:
            filters = {}

        resname_contains = (
            str(filters.get("resname_contains", "") or "").strip().lower()
        )
        atomname_contains = (
            str(filters.get("atomname_contains", "") or "").strip().lower()
        )
        atom_type_equals = (
            str(filters.get("atom_type_equals", "") or "").strip().lower()
        )
        charge_min = filters.get("charge_min", None)
        charge_max = filters.get("charge_max", None)

        try:
            charge_min = (
                float(charge_min)
                if charge_min is not None and charge_min != ""
                else None
            )
        except (TypeError, ValueError):
            charge_min = None
        try:
            charge_max = (
                float(charge_max)
                if charge_max is not None and charge_max != ""
                else None
            )
        except (TypeError, ValueError):
            charge_max = None

        with self._lock:
            if not self._loaded:
                raise ModelError("not_loaded", "No system loaded")
            meta_list = list(self._meta_list)

        serials: List[int] = []
        for meta in meta_list:
            if (
                resname_contains
                and resname_contains not in meta.residue.resname.lower()
            ):
                continue
            if atomname_contains and atomname_contains not in meta.atom_name.lower():
                continue
            if atom_type_equals:
                atom_type = meta.parm7.get("atom_type")
                if atom_type is None or atom_type.lower() != atom_type_equals:
                    continue
            charge = meta.parm7.get("charge")
            if charge_min is not None:
                if charge is None or charge < charge_min:
                    continue
            if charge_max is not None:
                if charge is None or charge > charge_max:
                    continue
            serials.append(meta.serial)
            if len(serials) >= max_results:
                logger.debug("Query truncated at %d results", len(serials))
                return {
                    "ok": True,
                    "serials": serials,
                    "count": len(serials),
                    "truncated": True,
                }

        logger.debug("Query returned %d results", len(serials))
        return {
            "ok": True,
            "serials": serials,
            "count": len(serials),
            "truncated": False,
        }

    def get_residue_info(self, resid: int) -> Dict[str, object]:
        with self._lock:
            if not self._loaded:
                raise ModelError("not_loaded", "No system loaded")
            keys = self._residue_keys_by_resid.get(int(resid), [])
        if not keys:
            raise ModelError("not_found", f"Residue {resid} not found")
        if len(keys) > 1:
            raise ModelError("ambiguous", "Residue id is not unique", keys)
        key = keys[0]
        serials = self._residue_index.get(key, [])
        parts = key.split(":")
        segid = parts[0] or None
        resid_str = parts[1]
        resname = parts[2] if len(parts) > 2 else ""
        logger.debug("Residue info requested resid=%s", resid)
        return {
            "ok": True,
            "residue": {
                "segid": segid,
                "resid": int(resid_str),
                "resname": resname,
                "serials": serials,
            },
        }
