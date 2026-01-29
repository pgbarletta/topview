"""Selection index builders for system info tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from topview.model.state import Parm7Section
from topview.services.parm7 import parse_int_tokens, parse_pointers


@dataclass
class SystemInfoSelectionIndex:
    """Lookup tables for mapping system info rows to atom serial selections."""

    atom_serials_by_type: Dict[int, List[int]]
    bonds_by_key: Dict[Tuple[int, int, int], List[Tuple[int, int]]]
    angles_by_key: Dict[Tuple[int, int, int, int], List[Tuple[int, int, int]]]
    dihedrals_by_idx: Dict[int, Tuple[int, int, int, int]]
    one_four_by_key: Dict[Tuple[int, int, int], List[Tuple[int, int]]]


def build_system_info_selection_index(
    sections: Dict[str, Parm7Section],
) -> SystemInfoSelectionIndex:
    """Build lookup tables for system info row selections.

    Parameters
    ----------
    sections
        Parm7 sections keyed by flag name.

    Returns
    -------
    SystemInfoSelectionIndex
        Selection index derived from parm7 sections.
    """

    pointer_section = sections.get("POINTERS")
    if not pointer_section or not pointer_section.tokens:
        raise ValueError("POINTERS section missing")
    pointers = parse_pointers(pointer_section)
    natom = _pointer_value(pointers, "NATOM")
    if natom <= 0:
        raise ValueError(f"Invalid POINTERS NATOM {natom}")

    atom_type_indices = _parse_int_section(
        sections, "ATOM_TYPE_INDEX", natom
    )
    atom_serials_by_type = _build_atom_serials_by_type(atom_type_indices)

    bonds_by_key: Dict[Tuple[int, int, int], List[Tuple[int, int]]] = {}
    nbondh = _pointer_value(pointers, "NBONH")
    mbona = _pointer_value(pointers, "MBONA")
    for name, count in (
        ("BONDS_INC_HYDROGEN", nbondh),
        ("BONDS_WITHOUT_HYDROGEN", mbona),
    ):
        values = _parse_int_section(sections, name, count * 3)
        _accumulate_bond_records(values, atom_type_indices, bonds_by_key)

    angles_by_key: Dict[Tuple[int, int, int, int], List[Tuple[int, int, int]]] = {}
    nth_eth = _pointer_value(pointers, "NTHETH")
    mtheta = _pointer_value(pointers, "MTHETA")
    for name, count in (
        ("ANGLES_INC_HYDROGEN", nth_eth),
        ("ANGLES_WITHOUT_HYDROGEN", mtheta),
    ):
        values = _parse_int_section(sections, name, count * 4)
        _accumulate_angle_records(values, atom_type_indices, angles_by_key)

    dihedrals_by_idx: Dict[int, Tuple[int, int, int, int]] = {}
    one_four_by_key: Dict[Tuple[int, int, int], List[Tuple[int, int]]] = {}
    nphih = _pointer_value(pointers, "NPHIH")
    mphia = _pointer_value(pointers, "MPHIA")
    term_idx = 1
    for name, count in (
        ("DIHEDRALS_INC_HYDROGEN", nphih),
        ("DIHEDRALS_WITHOUT_HYDROGEN", mphia),
    ):
        values = _parse_int_section(sections, name, count * 5)
        term_idx = _accumulate_dihedral_records(
            values,
            atom_type_indices,
            term_idx,
            dihedrals_by_idx,
            one_four_by_key,
        )

    return SystemInfoSelectionIndex(
        atom_serials_by_type=atom_serials_by_type,
        bonds_by_key=bonds_by_key,
        angles_by_key=angles_by_key,
        dihedrals_by_idx=dihedrals_by_idx,
        one_four_by_key=one_four_by_key,
    )


def nonbonded_pair_total(
    serials_a: Sequence[int],
    serials_b: Sequence[int],
    same_type: bool,
) -> int:
    """Compute total nonbonded selections for the given type lists."""

    if same_type:
        count = len(serials_a)
        return count * (count - 1) // 2
    return len(serials_a) * len(serials_b)


def nonbonded_pair_for_cursor(
    serials_a: Sequence[int],
    serials_b: Sequence[int],
    cursor: int,
    same_type: bool,
) -> Tuple[int, int]:
    """Select a nonbonded pair for a cursor index."""

    total = nonbonded_pair_total(serials_a, serials_b, same_type)
    if total <= 0:
        raise ValueError("No nonbonded pairs available")
    idx = int(cursor) % total
    if same_type:
        i, j = _combination_pair_index(len(serials_a), idx)
        return int(serials_a[i]), int(serials_a[j])
    if not serials_a or not serials_b:
        raise ValueError("No nonbonded pairs available")
    j = idx % len(serials_b)
    i = idx // len(serials_b)
    return int(serials_a[i]), int(serials_b[j])


def _pointer_value(pointers: Dict[str, int], name: str) -> int:
    value = int(pointers.get(name, 0))
    if value < 0:
        raise ValueError(f"POINTERS {name} value {value} is negative")
    return value


def _parse_int_section(
    sections: Dict[str, Parm7Section], name: str, expected: int
) -> List[int]:
    if expected == 0:
        section = sections.get(name)
        if section and section.tokens:
            raise ValueError(
                f"{name} length {len(section.tokens)} does not match expected {expected}"
            )
        return []
    section = sections.get(name)
    if not section or not section.tokens:
        raise ValueError(f"{name} section missing")
    if len(section.tokens) != expected:
        raise ValueError(
            f"{name} length {len(section.tokens)} does not match expected {expected}"
        )
    return parse_int_tokens(section.tokens)


def _build_atom_serials_by_type(
    atom_type_indices: Sequence[int],
) -> Dict[int, List[int]]:
    atom_serials_by_type: Dict[int, List[int]] = {}
    for idx, type_index in enumerate(atom_type_indices):
        if type_index is None:
            continue
        try:
            type_int = int(type_index)
        except (TypeError, ValueError):
            continue
        if type_int <= 0:
            continue
        serial = idx + 1
        atom_serials_by_type.setdefault(type_int, []).append(serial)
    return atom_serials_by_type


def _accumulate_bond_records(
    values: Sequence[int],
    atom_type_indices: Sequence[int],
    bonds_by_key: Dict[Tuple[int, int, int], List[Tuple[int, int]]],
) -> None:
    if not values:
        return
    for idx in range(0, len(values) - 2, 3):
        raw_a, raw_b, raw_param = values[idx : idx + 3]
        serial_a = _pointer_to_serial(raw_a)
        serial_b = _pointer_to_serial(raw_b)
        type_a = _type_index(atom_type_indices, serial_a)
        type_b = _type_index(atom_type_indices, serial_b)
        if type_a is None or type_b is None:
            continue
        param_index = abs(int(raw_param))
        type_min, type_max = _sorted_pair(type_a, type_b)
        bonds_by_key.setdefault((type_min, type_max, param_index), []).append(
            (serial_a, serial_b)
        )


def _accumulate_angle_records(
    values: Sequence[int],
    atom_type_indices: Sequence[int],
    angles_by_key: Dict[Tuple[int, int, int, int], List[Tuple[int, int, int]]],
) -> None:
    if not values:
        return
    for idx in range(0, len(values) - 3, 4):
        raw_i, raw_j, raw_k, raw_param = values[idx : idx + 4]
        serial_i = _pointer_to_serial(raw_i)
        serial_j = _pointer_to_serial(raw_j)
        serial_k = _pointer_to_serial(raw_k)
        type_i = _type_index(atom_type_indices, serial_i)
        type_j = _type_index(atom_type_indices, serial_j)
        type_k = _type_index(atom_type_indices, serial_k)
        if type_i is None or type_j is None or type_k is None:
            continue
        param_index = abs(int(raw_param))
        type_i_c, type_k_c = (type_i, type_k)
        if type_i_c > type_k_c:
            type_i_c, type_k_c = type_k_c, type_i_c
        angles_by_key.setdefault(
            (type_i_c, type_j, type_k_c, param_index), []
        ).append((serial_i, serial_j, serial_k))


def _accumulate_dihedral_records(
    values: Sequence[int],
    atom_type_indices: Sequence[int],
    term_idx: int,
    dihedrals_by_idx: Dict[int, Tuple[int, int, int, int]],
    one_four_by_key: Dict[Tuple[int, int, int], List[Tuple[int, int]]],
) -> int:
    if not values:
        return term_idx
    for idx in range(0, len(values) - 4, 5):
        raw_i, raw_j, raw_k, raw_l, raw_param = values[idx : idx + 5]
        serial_i = _pointer_to_serial(raw_i)
        serial_j = _pointer_to_serial(raw_j)
        serial_k = _pointer_to_serial(raw_k)
        serial_l = _pointer_to_serial(raw_l)
        dihedrals_by_idx[term_idx] = (serial_i, serial_j, serial_k, serial_l)
        term_idx += 1
        if raw_k < 0 or raw_l < 0:
            continue
        type_i = _type_index(atom_type_indices, serial_i)
        type_l = _type_index(atom_type_indices, serial_l)
        if type_i is None or type_l is None:
            continue
        param_index = abs(int(raw_param))
        type_min, type_max = _sorted_pair(type_i, type_l)
        one_four_by_key.setdefault((type_min, type_max, param_index), []).append(
            (serial_i, serial_l)
        )
    return term_idx


def _pointer_to_serial(value: int) -> int:
    return abs(int(value)) // 3 + 1


def _type_index(atom_type_indices: Sequence[int], serial: int) -> Optional[int]:
    idx = serial - 1
    if idx < 0 or idx >= len(atom_type_indices):
        return None
    value = atom_type_indices[idx]
    if value is None:
        return None
    try:
        type_index = int(value)
    except (TypeError, ValueError):
        return None
    if type_index <= 0:
        return None
    return type_index


def _sorted_pair(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _combination_pair_index(count: int, idx: int) -> Tuple[int, int]:
    if count < 2:
        raise ValueError("Need at least two atoms to form a pair")
    remaining = int(idx)
    for i in range(count - 1):
        span = count - i - 1
        if remaining < span:
            return i, i + 1 + remaining
        remaining -= span
    raise ValueError("Index out of range for combination pairs")
