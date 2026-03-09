"""Amber NMR restraint parsing utilities."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Dict, List


@dataclass(frozen=True)
class NmrRestraint:
    """Parsed Amber NMR restraint record."""

    kind: str
    serials: List[int]
    r1: float
    r2: float
    r3: float
    r4: float
    rk2: float
    rk3: float
    equilibrium_value: float
    line_start: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "serials": list(self.serials),
            "r1": self.r1,
            "r2": self.r2,
            "r3": self.r3,
            "r4": self.r4,
            "rk2": self.rk2,
            "rk3": self.rk3,
            "equilibrium_value": self.equilibrium_value,
            "line_start": self.line_start,
        }


def _parse_assignment_map(block_body: str, *, line_start: int) -> Dict[str, str]:
    chunks = [chunk.strip() for chunk in block_body.replace("\n", ",").split(",")]
    assignments: Dict[str, str] = {}
    current_key = None
    current_values: List[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        if "=" in chunk:
            if current_key is not None:
                assignments[current_key] = ",".join(current_values).strip()
            key, value = chunk.split("=", 1)
            current_key = key.strip().lower()
            current_values = [value.strip()]
        else:
            if current_key is None:
                raise ValueError(
                    f"Malformed NMR restraint near line {line_start}: unexpected value '{chunk}'"
                )
            current_values.append(chunk.strip())
    if current_key is not None:
        assignments[current_key] = ",".join(current_values).strip()
    return assignments


def _parse_iat(raw_value: str, *, natom: int, line_start: int) -> List[int]:
    serials: List[int] = []
    raw_serials: List[int] = []
    for token in raw_value.split(","):
        value = token.strip()
        if not value:
            continue
        try:
            serial = int(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid iat value '{value}' in NMR restraint near line {line_start}"
            ) from exc
        if serial < 0:
            raise ValueError(
                f"Unsupported group or zero-based restraint atom index {serial} near line {line_start}"
            )
        raw_serials.append(serial)
    if raw_serials and raw_serials[-1] == 0:
        raw_serials = raw_serials[:-1]
    for serial in raw_serials:
        if serial == 0:
            raise ValueError(
                f"Unsupported group or zero-based restraint atom index {serial} near line {line_start}"
            )
        if serial > natom:
            raise ValueError(
                f"Restraint atom index {serial} exceeds topology atom count {natom} near line {line_start}"
            )
        serials.append(serial)
    return serials


def _parse_float(assignments: Dict[str, str], key: str, *, line_start: int) -> float:
    raw = assignments.get(key)
    if raw is None:
        raise ValueError(f"Missing '{key}' in NMR restraint near line {line_start}")
    try:
        return float(raw.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise ValueError(
            f"Invalid '{key}' value '{raw}' in NMR restraint near line {line_start}"
        ) from exc


def _classify_restraint(serials: List[int], *, line_start: int) -> str:
    count = len(serials)
    if count == 2:
        return "distance"
    if count == 3:
        return "angle"
    if count == 4:
        return "dihedral"
    raise ValueError(
        f"Unsupported restraint atom count {count} near line {line_start}; expected 2, 3, or 4"
    )


def summarize_nmr_restraints(restraints: List[NmrRestraint]) -> Dict[str, int]:
    summary = {"distance": 0, "angle": 0, "dihedral": 0, "total": 0}
    for restraint in restraints:
        if restraint.kind in summary:
            summary[restraint.kind] += 1
        summary["total"] += 1
    return summary


def parse_nmr_restraints(path: str, *, natom: int) -> List[NmrRestraint]:
    """Parse an Amber NMR restraint file consisting of ``&rst`` blocks."""

    if not path:
        return []
    if not os.path.exists(path):
        raise ValueError(f"NMR restraint file not found: {path}")

    restraints: List[NmrRestraint] = []
    current_lines: List[str] = []
    block_start = None
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if block_start is None:
                if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                    continue
                if stripped.lower().startswith("&rst"):
                    block_start = line_no
                    current_lines = [line]
                    if "/" in line:
                        block_text = "".join(current_lines)
                        current_lines = []
                        block_start_local = block_start
                        block_start = None
                        restraints.append(
                            _parse_restraint_block(
                                block_text,
                                natom=natom,
                                line_start=block_start_local,
                            )
                        )
                continue

            current_lines.append(line)
            if "/" in line:
                block_text = "".join(current_lines)
                current_lines = []
                block_start_local = block_start
                block_start = None
                restraints.append(
                    _parse_restraint_block(
                        block_text,
                        natom=natom,
                        line_start=block_start_local,
                    )
                )

    if block_start is not None:
        raise ValueError(
            f"Unterminated NMR restraint block starting at line {block_start}"
        )
    if not restraints:
        raise ValueError(
            f"No Amber '&rst' restraint blocks found in NMR restraint file: {path}"
        )
    return restraints


def _parse_restraint_block(block_text: str, *, natom: int, line_start: int) -> NmrRestraint:
    body = block_text.strip()
    if not body.lower().startswith("&rst"):
        raise ValueError(f"Expected '&rst' at line {line_start}")
    body = body[4:]
    if "/" in body:
        body = body.split("/", 1)[0]
    assignments = _parse_assignment_map(body, line_start=line_start)
    serials = _parse_iat(assignments.get("iat", ""), natom=natom, line_start=line_start)
    kind = _classify_restraint(serials, line_start=line_start)
    return NmrRestraint(
        kind=kind,
        serials=serials,
        r1=_parse_float(assignments, "r1", line_start=line_start),
        r2=_parse_float(assignments, "r2", line_start=line_start),
        r3=_parse_float(assignments, "r3", line_start=line_start),
        r4=_parse_float(assignments, "r4", line_start=line_start),
        rk2=_parse_float(assignments, "rk2", line_start=line_start),
        rk3=_parse_float(assignments, "rk3", line_start=line_start),
        equilibrium_value=_parse_float(assignments, "r2", line_start=line_start),
        line_start=line_start,
    )
