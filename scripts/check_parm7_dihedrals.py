#!/usr/bin/env python3
"""Check parm7 dihedral ordering against bond topology from ParmEd.

The script parses DIHEDRALS_INC_HYDROGEN and DIHEDRALS_WITHOUT_HYDROGEN,
verifies 5-integer records, and checks whether j-k is the central bond.
If not, it attempts to classify the dihedral as improper by finding a
central atom bonded to the other three.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import re
from typing import Dict, List, Sequence, Tuple

import numpy as np
import parmed


def _pointer_to_serial(value: int) -> int:
    return abs(int(value)) // 3 + 1


def _parse_parm7_sections(path: Path) -> Dict[str, List[str]]:
    with path.open("rb") as handle:
        text = handle.read().decode("utf-8", errors="replace")
    lines = text.splitlines()
    fmt_re = re.compile(r"%FORMAT\((\d+)([a-zA-Z])(\d+)(?:\.(\d+))?\)")
    sections: Dict[str, List[str]] = {}
    current_name = None
    current_count = 0
    current_width = 0
    current_tokens: List[str] = []
    collect_tokens = False

    def finalize_section() -> None:
        if current_name:
            sections[current_name] = list(current_tokens)

    for line in lines:
        if line.startswith("%FLAG"):
            if current_name is not None:
                finalize_section()
            parts = line.split()
            current_name = parts[1] if len(parts) > 1 else None
            current_count = 0
            current_width = 0
            current_tokens = []
            collect_tokens = current_name is not None
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
                current_tokens.append(raw)

    if current_name is not None:
        finalize_section()
    return sections


def _parse_pointers(pointer_tokens: Sequence[str]) -> Dict[str, int]:
    pointer_names = [
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
    raw = " ".join(pointer_tokens)
    values = np.fromstring(raw, sep=" ", dtype=int)
    if values.size not in (31, 32):
        raise ValueError(
            f"POINTERS length {values.size} does not match expected 31 or 32"
        )
    names = pointer_names[: values.size]
    return {name: int(value) for name, value in zip(names, values.tolist())}


def _parse_int_tokens(tokens: Sequence[str]) -> List[int]:
    raw = " ".join(tokens)
    values = np.fromstring(raw, sep=" ", dtype=int)
    return values.astype(int).tolist()


def _build_adjacency(structure: parmed.Structure) -> Dict[int, set[int]]:
    adjacency: Dict[int, set[int]] = defaultdict(set)
    for bond in structure.bonds:
        a = bond.atom1.idx + 1
        b = bond.atom2.idx + 1
        adjacency[a].add(b)
        adjacency[b].add(a)
    return adjacency


def _is_bonded(adjacency: Dict[int, set[int]], a: int, b: int) -> bool:
    return b in adjacency.get(a, set())


def _is_improper_by_l_sign(raw_l: int) -> bool:
    return int(raw_l) < 0


def _format_dihedral(serials: Sequence[int]) -> str:
    return f"({serials[0]}, {serials[1]}, {serials[2]}, {serials[3]})"


def _parse_dihedral_records(values: Sequence[int]) -> List[Tuple[int, int, int, int, int]]:
    records: List[Tuple[int, int, int, int, int]] = []
    for idx in range(0, len(values), 5):
        chunk = values[idx : idx + 5]
        if len(chunk) < 5:
            break
        records.append((chunk[0], chunk[1], chunk[2], chunk[3], chunk[4]))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check parm7 dihedral ordering against bonded topology (ParmEd)."
        )
    )
    parser.add_argument("parm7", help="Path to parm7/prmtop file")
    parser.add_argument("rst7", help="Path to rst7/inpcrd file")
    args = parser.parse_args()

    parm7_path = Path(args.parm7)
    rst7_path = Path(args.rst7)
    if not parm7_path.exists():
        raise SystemExit(f"parm7 not found: {parm7_path}")
    if not rst7_path.exists():
        raise SystemExit(f"rst7 not found: {rst7_path}")

    structure = parmed.load_file(str(parm7_path), str(rst7_path))
    adjacency = _build_adjacency(structure)

    sections = _parse_parm7_sections(parm7_path)
    pointer_tokens = sections.get("POINTERS")
    if not pointer_tokens:
        raise SystemExit("POINTERS section missing in parm7")
    pointers = _parse_pointers(pointer_tokens)

    dihedral_sections = (
        ("DIHEDRALS_INC_HYDROGEN", int(pointers.get("NPHIH", 0))),
        ("DIHEDRALS_WITHOUT_HYDROGEN", int(pointers.get("MPHIA", 0))),
    )

    malformed_records: List[str] = []
    improper_records: List[str] = []
    improper_position_counts: Dict[str, int] = defaultdict(int)
    improper_section_counts: Dict[str, int] = defaultdict(int)
    section_totals: Dict[str, int] = defaultdict(int)
    j_k_not_bonded = 0
    improper_total = 0
    total = 0

    for section_name, count in dihedral_sections:
        section_tokens = sections.get(section_name)
        if count == 0:
            if section_tokens:
                malformed_records.append(
                    f"{section_name}: expected 0 entries but found {len(section_tokens)} tokens"
                )
            continue
        if not section_tokens:
            malformed_records.append(f"{section_name}: missing or empty section")
            continue
        if len(section_tokens) != count * 5:
            malformed_records.append(
                f"{section_name}: expected {count * 5} tokens but found {len(section_tokens)}"
            )
        values = _parse_int_tokens(section_tokens)
        if len(values) % 5 != 0:
            malformed_records.append(
                f"{section_name}: token count {len(values)} is not a multiple of 5"
            )
        records = _parse_dihedral_records(values)
        for raw_i, raw_j, raw_k, raw_l, raw_param in records:
            serials = (
                _pointer_to_serial(raw_i),
                _pointer_to_serial(raw_j),
                _pointer_to_serial(raw_k),
                _pointer_to_serial(raw_l),
            )
            total += 1
            section_totals[section_name] += 1
            if _is_improper_by_l_sign(raw_l):
                improper_total += 1
                improper_position_counts["k"] += 1
                improper_section_counts[section_name] += 1
                improper_records.append(
                    f"{section_name} dihedral {_format_dihedral(serials)} param={raw_param} "
                    "improper (l index negative)"
                )
                continue
            if _is_bonded(adjacency, serials[1], serials[2]):
                continue
            j_k_not_bonded += 1
            malformed_records.append(
                f"{section_name} dihedral {_format_dihedral(serials)} param={raw_param} "
                "has non-bonded j-k and no central atom"
            )

    print("Dihedral ordering check")
    print(f"  Total dihedrals checked: {total}")
    print(f"  impropers detected: {improper_total}")
    print(f"  j-k not bonded (non-improper): {j_k_not_bonded}")
    print("\nSection totals:")
    for section_name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
        print(f"  {section_name}: {section_totals.get(section_name, 0)}")

    if improper_records:
        print("\nImproper-like dihedrals (central bonded to other three):")
        for record in improper_records:
            print(f"  {record}")
    else:
        print("\nImproper-like dihedrals: none detected")

    print("\nImproper summary:")
    for label in ("i", "j", "k", "l"):
        count = improper_position_counts.get(label, 0)
        print(f"  central={label}: {count}")
    for section_name in ("DIHEDRALS_INC_HYDROGEN", "DIHEDRALS_WITHOUT_HYDROGEN"):
        count = improper_section_counts.get(section_name, 0)
        print(f"  {section_name}: {count}")
    if malformed_records:
        print("\nMalformed or unexpected records:")
        for record in malformed_records:
            print(f"  {record}")
    else:
        print("\nMalformed or unexpected records: none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
