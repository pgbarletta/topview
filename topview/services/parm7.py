"""Parsing utilities for parm7 topology files."""

from __future__ import annotations

import mmap
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from topview.config import PARM7_REFERENCE_PATH, PARM7_TOKEN_SECTIONS
from topview.model.state import Parm7Section, Parm7Token

_PARM7_DESCRIPTIONS: Optional[Dict[str, str]] = None
_PARM7_DEPRECATED: Optional[set] = None

POINTER_NAMES = [
    "NATOM",
    "NTYPES",
    "NBONH",
    "MBONA",
    "NTHETH",
    "MTHETA",
    "NPHIH",
    "MPHIA",
    "NHPARM",
    "NPARM",
    "NNB",
    "NRES",
    "NBONA",
    "NTHETA",
    "NPHIA",
    "NUMBND",
    "NUMANG",
    "NPTRA",
    "NATYP",
    "NPHB",
    "IFPERT",
    "NBPER",
    "NGPER",
    "NDPER",
    "MBPER",
    "MGPER",
    "MDPER",
    "IFBOX",
    "NMXRS",
    "IFCAP",
    "NUMEXTRA",
    "NCOPY",
]


def parse_parm7(path: str) -> Tuple[str, Dict[str, Parm7Section]]:
    """Parse a parm7 file into raw text and tokenized sections.

    Parameters
    ----------
    path
        Path to the parm7 file.

    Returns
    -------
    tuple
        Raw text and a dict of parm7 sections keyed by flag.
    """

    with open(path, "rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            text = mm.read().decode("utf-8", errors="replace")
    lines = text.splitlines()
    sections: Dict[str, Parm7Section] = {}
    fmt_re = re.compile(r"%FORMAT\((\d+)([a-zA-Z])(\d+)(?:\.(\d+))?\)")

    current_name: Optional[str] = None
    current_count = 0
    current_width = 0
    current_tokens: List[Parm7Token] = []
    current_flag_line = 0
    collect_tokens = False

    def finalize_section(end_line: int) -> None:
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
            collect_tokens = bool(current_name and current_name in PARM7_TOKEN_SECTIONS)
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


def load_parm7_descriptions() -> Dict[str, str]:
    """Load section descriptions from the parm7 reference markdown.

    Returns
    -------
    dict
        Mapping of section flag to description text.
    """

    global _PARM7_DESCRIPTIONS
    if _PARM7_DESCRIPTIONS is not None:
        return _PARM7_DESCRIPTIONS
    if not PARM7_REFERENCE_PATH.exists():
        _PARM7_DESCRIPTIONS = {}
        return _PARM7_DESCRIPTIONS
    descriptions: Dict[str, str] = {}
    current_flag = None
    capturing = False
    buffer: List[str] = []
    lines = PARM7_REFERENCE_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        flag_match = re.search(r"\*\*Flag:\*\*\s*`%FLAG\s+([A-Z0-9_]+)`", line)
        if flag_match:
            if current_flag and buffer:
                text = " ".join(buffer)
                descriptions[current_flag] = re.sub(r"\s+", " ", text).strip()
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
                    descriptions[current_flag] = re.sub(r"\s+", " ", text).strip()
                capturing = False
                buffer = []
                continue
            if line.startswith("## "):
                if current_flag and buffer:
                    text = " ".join(buffer)
                    descriptions[current_flag] = re.sub(r"\s+", " ", text).strip()
                capturing = False
                buffer = []
                continue
            buffer.append(line.strip())
    if current_flag and buffer:
        text = " ".join(buffer)
        descriptions[current_flag] = re.sub(r"\s+", " ", text).strip()
    _PARM7_DESCRIPTIONS = descriptions
    return _PARM7_DESCRIPTIONS


def load_parm7_deprecated_flags() -> set:
    """Return a set of deprecated parm7 flag names.

    Returns
    -------
    set
        Set of deprecated section flag names.
    """

    global _PARM7_DEPRECATED
    if _PARM7_DEPRECATED is not None:
        return _PARM7_DEPRECATED
    if not PARM7_REFERENCE_PATH.exists():
        _PARM7_DEPRECATED = set()
        return _PARM7_DEPRECATED
    lines = PARM7_REFERENCE_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    deprecated: set = set()
    current_flags: List[str] = []
    found_deprecated = False

    def flush_flags() -> None:
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


def parse_pointers(section: Parm7Section) -> Dict[str, int]:
    """Parse the POINTERS section into a name/value mapping.

    Parameters
    ----------
    section
        POINTERS section metadata.

    Returns
    -------
    dict
        Mapping of pointer names to integer values.

    Raises
    ------
    ValueError
        If the number of pointer values is not 31 or 32.
    """

    raw = " ".join(token.value for token in section.tokens)
    values = np.fromstring(raw, sep=" ", dtype=int)
    if values.size not in (31, 32):
        raise ValueError(
            f"POINTERS section length {values.size} does not match expected 31 or 32 values"
        )
    names = POINTER_NAMES[: values.size]
    return {name: int(value) for name, value in zip(names, values.tolist())}


def parse_int_tokens(tokens: List[Parm7Token]) -> List[int]:
    """Parse parm7 integer tokens.

    Parameters
    ----------
    tokens
        Parm7 tokens to parse.

    Returns
    -------
    list
        Parsed integer values.
    """

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
                values.append(0)
    return values


def parse_float_tokens(tokens: List[Parm7Token]) -> List[float]:
    """Parse parm7 float tokens, supporting Fortran D notation.

    Parameters
    ----------
    tokens
        Parm7 tokens to parse.

    Returns
    -------
    list
        Parsed float values.
    """

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
            values.append(0.0)
    return values


def parse_int_values(values: List[str]) -> List[int]:
    """Parse integer values from strings (multiprocessing friendly).

    Parameters
    ----------
    values
        Raw string values to parse.

    Returns
    -------
    list
        Parsed integer values.
    """

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


def parse_float_values(values: List[str]) -> List[float]:
    """Parse float values from strings (multiprocessing friendly).

    Parameters
    ----------
    values
        Raw string values to parse.

    Returns
    -------
    list
        Parsed float values.
    """

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


def parse_int_token_value(token: Parm7Token) -> int:
    """Parse a single integer token value.

    Parameters
    ----------
    token
        Parm7 token to parse.

    Returns
    -------
    int
        Parsed integer value.
    """

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


def parse_float_token_value(token: Parm7Token) -> float:
    """Parse a single float token value.

    Parameters
    ----------
    token
        Parm7 token to parse.

    Returns
    -------
    float
        Parsed float value.
    """

    raw = token.value.strip()
    if not raw:
        return 0.0
    raw = raw.replace("D", "E").replace("d", "e")
    try:
        return float(raw)
    except ValueError:
        return 0.0
