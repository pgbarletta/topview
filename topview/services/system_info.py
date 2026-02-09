"""System information table builders derived from parm7 sections."""

from __future__ import annotations

import logging
import math
import time
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

from topview.model.state import Parm7Section
from topview.services.parm7 import describe_section, parse_pointers

logger = logging.getLogger(__name__)

LJ_MIN_COEF = 1.0e-10
OPTIONAL_CONSUMED_FLOAT_SECTIONS = frozenset(
    {"SCEE_SCALE_FACTOR", "SCNB_SCALE_FACTOR"}
)


def build_system_info_tables(
    sections: Dict[str, Parm7Section],
) -> Dict[str, Dict[str, object]]:
    """Build system info tables for the Info panel.

    Parameters
    ----------
    sections
        Parm7 sections keyed by flag name.

    Returns
    -------
    dict
        Mapping of table identifiers to column/row payloads.

    Raises
    ------
    ValueError
        If required sections are missing or value counts mismatch POINTERS.
    """

    pointer_section = sections.get("POINTERS")
    if not pointer_section or not pointer_section.tokens:
        raise ValueError("POINTERS section missing")
    pointers = parse_pointers(pointer_section)
    natom = _pointer_value(pointers, "NATOM")
    ntypes = _pointer_value(pointers, "NTYPES")
    if natom <= 0 or ntypes <= 0:
        raise ValueError(f"Invalid POINTERS NATOM/NTYPES {natom}/{ntypes}")
    nbondh = _pointer_value(pointers, "NBONH")
    mbona = _pointer_value(pointers, "MBONA")
    nth_eth = _pointer_value(pointers, "NTHETH")
    mtheta = _pointer_value(pointers, "MTHETA")
    nphih = _pointer_value(pointers, "NPHIH")
    mphia = _pointer_value(pointers, "MPHIA")
    numbnd = _pointer_value(pointers, "NUMBND")
    numang = _pointer_value(pointers, "NUMANG")
    nptra = _pointer_value(pointers, "NPTRA")
    nphb = _pointer_value(pointers, "NPHB")

    atom_type_indices = _parse_int_section(
        sections, "ATOM_TYPE_INDEX", natom
    )
    atom_names = _parse_string_section(sections, "ATOM_NAME", natom)
    amber_atom_types = _parse_string_section(
        sections, "AMBER_ATOM_TYPE", natom
    )
    masses = _parse_float_section(sections, "MASS", natom)
    nonbond_index = _parse_int_section(
        sections, "NONBONDED_PARM_INDEX", ntypes * ntypes
    )
    acoef = _parse_float_section(
        sections, "LENNARD_JONES_ACOEF", ntypes * (ntypes + 1) // 2
    )
    bcoef = _parse_float_section(
        sections, "LENNARD_JONES_BCOEF", ntypes * (ntypes + 1) // 2
    )
    hbond_acoef = _parse_float_section(sections, "HBOND_ACOEF", nphb)
    hbond_bcoef = _parse_float_section(sections, "HBOND_BCOEF", nphb)

    bond_force = _parse_float_section(sections, "BOND_FORCE_CONSTANT", numbnd)
    bond_equil = _parse_float_section(sections, "BOND_EQUIL_VALUE", numbnd)
    angle_force = _parse_float_section(sections, "ANGLE_FORCE_CONSTANT", numang)
    angle_equil = _parse_float_section(sections, "ANGLE_EQUIL_VALUE", numang)
    dihedral_force = _parse_float_section(
        sections, "DIHEDRAL_FORCE_CONSTANT", nptra
    )
    dihedral_periodicity = _parse_float_section(
        sections, "DIHEDRAL_PERIODICITY", nptra
    )
    dihedral_phase = _parse_float_section(sections, "DIHEDRAL_PHASE", nptra)
    scee_scale = _parse_optional_float_section(
        sections, "SCEE_SCALE_FACTOR", nptra
    )
    scnb_scale = _parse_optional_float_section(
        sections, "SCNB_SCALE_FACTOR", nptra
    )

    type_name_map = _build_type_name_map(atom_type_indices, amber_atom_types, ntypes)
    atom_types_df = _build_atom_type_table(
        atom_type_indices,
        type_name_map,
        nonbond_index,
        acoef,
        bcoef,
        ntypes,
    )
    bond_df = _build_bond_table(
        sections,
        atom_type_indices,
        type_name_map,
        nbondh,
        mbona,
        bond_force,
        bond_equil,
    )
    bond_adjacency = _build_bond_adjacency(sections, nbondh, mbona)
    angle_df = _build_angle_table(
        sections,
        atom_type_indices,
        type_name_map,
        nth_eth,
        mtheta,
        angle_force,
        angle_equil,
    )
    dihedral_df = _build_dihedral_table(
        sections,
        atom_names,
        amber_atom_types,
        nphih,
        mphia,
        dihedral_force,
        dihedral_periodicity,
        dihedral_phase,
        scee_scale,
        scnb_scale,
        nbondh,
        mbona,
        masses,
    )
    improper_df = _build_improper_table(
        sections,
        atom_names,
        amber_atom_types,
        nphih,
        mphia,
        dihedral_force,
        dihedral_periodicity,
        dihedral_phase,
        scee_scale,
        scnb_scale,
        bond_adjacency,
    )
    one_four_df = _build_one_four_table(
        sections,
        atom_type_indices,
        type_name_map,
        nphih,
        mphia,
        scee_scale,
        scnb_scale,
        nonbond_index,
        acoef,
        bcoef,
        hbond_acoef,
        hbond_bcoef,
        ntypes,
    )
    nonbonded_df = _build_nonbonded_table(
        nonbond_index,
        type_name_map,
        acoef,
        bcoef,
        hbond_acoef,
        hbond_bcoef,
        ntypes,
    )

    return {
        "atom_types": _df_to_table(atom_types_df),
        "bond_types": _df_to_table(bond_df),
        "angle_types": _df_to_table(angle_df),
        "dihedral_types": _df_to_table(dihedral_df),
        "improper_types": _df_to_table(improper_df),
        "one_four_nonbonded": _df_to_table(one_four_df),
        "nonbonded_pairs": _df_to_table(nonbonded_df),
    }


def build_system_info_tables_with_timing(
    sections: Dict[str, Parm7Section],
) -> Tuple[Dict[str, Dict[str, object]], float]:
    """Build system info tables and return elapsed time.

    Parameters
    ----------
    sections
        Parm7 sections keyed by flag name.

    Returns
    -------
    tuple
        Tables payload and elapsed seconds.
    """

    start = time.perf_counter()
    tables = build_system_info_tables(sections)
    return tables, time.perf_counter() - start


def _pointer_value(pointers: Dict[str, int], name: str) -> int:
    value = int(pointers.get(name, 0))
    if value < 0:
        logger.error("POINTERS %s value is negative: %d", name, value)
        raise ValueError(f"POINTERS {name} value {value} is negative")
    return value


def _parse_int_section(
    sections: Dict[str, Parm7Section], name: str, expected: int
) -> np.ndarray:
    if expected == 0:
        section = sections.get(name)
        if section and section.tokens:
            logger.error(
                "Parm7 section %s length mismatch: expected=%d actual=%d; %s",
                name,
                expected,
                len(section.tokens),
                describe_section(section),
            )
            raise ValueError(
                f"{name} length {len(section.tokens)} does not match expected {expected}"
            )
        return np.zeros(0, dtype=int)
    section = sections.get(name)
    if not section or not section.tokens:
        logger.error(
            "Parm7 section missing: %s expected=%d; %s",
            name,
            expected,
            describe_section(section),
        )
        raise ValueError(f"{name} section missing")
    if len(section.tokens) != expected:
        logger.error(
            "Parm7 section %s length mismatch: expected=%d actual=%d; %s",
            name,
            expected,
            len(section.tokens),
            describe_section(section),
        )
        raise ValueError(
            f"{name} length {len(section.tokens)} does not match expected {expected}"
        )
    raw = " ".join(token.value for token in section.tokens)
    values = np.fromstring(raw, sep=" ", dtype=int)
    if values.size != expected:
        logger.error(
            "Parm7 section %s parsed value mismatch: parsed=%d expected=%d; %s",
            name,
            values.size,
            expected,
            describe_section(section),
        )
        raise ValueError(
            f"{name} parsed {values.size} values but expected {expected}"
        )
    return values


def _parse_float_section(
    sections: Dict[str, Parm7Section], name: str, expected: int
) -> np.ndarray:
    if expected == 0:
        section = sections.get(name)
        if section and section.tokens:
            logger.error(
                "Parm7 section %s length mismatch: expected=%d actual=%d; %s",
                name,
                expected,
                len(section.tokens),
                describe_section(section),
            )
            raise ValueError(
                f"{name} length {len(section.tokens)} does not match expected {expected}"
            )
        return np.zeros(0, dtype=float)
    section = sections.get(name)
    if not section or not section.tokens:
        logger.error(
            "Parm7 section missing: %s expected=%d; %s",
            name,
            expected,
            describe_section(section),
        )
        raise ValueError(f"{name} section missing")
    if len(section.tokens) != expected:
        logger.error(
            "Parm7 section %s length mismatch: expected=%d actual=%d; %s",
            name,
            expected,
            len(section.tokens),
            describe_section(section),
        )
        raise ValueError(
            f"{name} length {len(section.tokens)} does not match expected {expected}"
        )
    raw = " ".join(token.value for token in section.tokens)
    raw = raw.replace("D", "E").replace("d", "e")
    values = np.fromstring(raw, sep=" ", dtype=float)
    if values.size != expected:
        logger.error(
            "Parm7 section %s parsed value mismatch: parsed=%d expected=%d; %s",
            name,
            values.size,
            expected,
            describe_section(section),
        )
        raise ValueError(
            f"{name} parsed {values.size} values but expected {expected}"
        )
    return values


def _parse_optional_float_section(
    sections: Dict[str, Parm7Section],
    name: str,
    expected: int,
    fill_value: float = np.nan,
) -> np.ndarray:
    section = sections.get(name)
    if section is None:
        if expected <= 0:
            return np.zeros(0, dtype=float)
        return np.full(expected, fill_value, dtype=float)
    if expected == 0:
        if section.tokens:
            logger.error(
                "Parm7 section %s length mismatch: expected=%d actual=%d; %s",
                name,
                expected,
                len(section.tokens),
                describe_section(section),
            )
            raise ValueError(
                f"{name} length {len(section.tokens)} does not match expected {expected}"
            )
        return np.zeros(0, dtype=float)
    if not section.tokens:
        logger.error(
            "Parm7 optional section %s is present but empty: expected=%d; %s",
            name,
            expected,
            describe_section(section),
        )
        raise ValueError(f"{name} section present but empty")
    return _parse_float_section(sections, name, expected)


def _parse_string_section(
    sections: Dict[str, Parm7Section], name: str, expected: int
) -> List[str]:
    if expected == 0:
        section = sections.get(name)
        if section and section.tokens:
            logger.error(
                "Parm7 section %s length mismatch: expected=%d actual=%d; %s",
                name,
                expected,
                len(section.tokens),
                describe_section(section),
            )
            raise ValueError(
                f"{name} length {len(section.tokens)} does not match expected {expected}"
            )
        return []
    section = sections.get(name)
    if not section or not section.tokens:
        logger.error(
            "Parm7 section missing: %s expected=%d; %s",
            name,
            expected,
            describe_section(section),
        )
        raise ValueError(f"{name} section missing")
    if len(section.tokens) != expected:
        logger.error(
            "Parm7 section %s length mismatch: expected=%d actual=%d; %s",
            name,
            expected,
            len(section.tokens),
            describe_section(section),
        )
        raise ValueError(
            f"{name} length {len(section.tokens)} does not match expected {expected}"
        )
    return [token.value.strip() for token in section.tokens]


def _build_type_name_map(
    atom_type_indices: np.ndarray, amber_atom_types: List[str], ntypes: int
) -> Dict[int, str]:
    df = pd.DataFrame(
        {
            "type_index": atom_type_indices.astype(int),
            "amber_type": amber_atom_types,
        }
    )
    grouped = (
        df.groupby("type_index", dropna=False)["amber_type"]
        .apply(lambda series: ", ".join(sorted({value for value in series if value})))
    )
    name_map = {int(idx): str(val) for idx, val in grouped.items()}
    for type_index in range(1, ntypes + 1):
        name_map.setdefault(type_index, "")
    return name_map


def _build_atom_type_table(
    atom_type_indices: np.ndarray,
    type_name_map: Dict[int, str],
    nonbond_index: np.ndarray,
    acoef: np.ndarray,
    bcoef: np.ndarray,
    ntypes: int,
) -> pd.DataFrame:
    type_indices = np.arange(1, ntypes + 1, dtype=int)
    diag_offsets = np.arange(ntypes, dtype=int) * (ntypes + 1)
    pair_index = np.zeros(ntypes, dtype=int)
    valid_offsets = diag_offsets < nonbond_index.size
    pair_index[valid_offsets] = nonbond_index[diag_offsets[valid_offsets]]
    acoef_diag = np.full(ntypes, np.nan, dtype=float)
    bcoef_diag = np.full(ntypes, np.nan, dtype=float)
    positive = (pair_index > 0) & (pair_index <= acoef.size) & (pair_index <= bcoef.size)
    acoef_diag[positive] = acoef[pair_index[positive] - 1]
    bcoef_diag[positive] = bcoef[pair_index[positive] - 1]
    rmin = np.zeros(ntypes, dtype=float)
    epsilon = np.zeros(ntypes, dtype=float)
    usable = positive & (acoef_diag >= LJ_MIN_COEF) & (bcoef_diag >= LJ_MIN_COEF)
    if usable.any():
        factor = 2.0 * acoef_diag[usable] / bcoef_diag[usable]
        rmin[usable] = np.power(factor, 1.0 / 6.0) * 0.5
        epsilon[usable] = bcoef_diag[usable] / 2.0 / factor

    counts = (
        pd.Series(atom_type_indices.astype(int))
        .value_counts()
        .rename_axis("type_index")
        .reset_index(name="atom_count")
    )
    names = pd.DataFrame(
        {
            "type_index": list(type_name_map.keys()),
            "amber_types": list(type_name_map.values()),
        }
    )
    lj_df = pd.DataFrame(
        {
            "type_index": type_indices,
            "pair_index": pair_index.astype(int),
            "acoef": acoef_diag,
            "bcoef": bcoef_diag,
            "rmin": rmin,
            "epsilon": epsilon,
        }
    )
    table = (
        pd.DataFrame({"type_index": type_indices})
        .merge(names, on="type_index", how="left")
        .merge(counts, on="type_index", how="left")
        .merge(lj_df, on="type_index", how="left")
    )
    table["atom_count"] = table["atom_count"].fillna(0).astype(int)
    return table.sort_values("type_index")


def _build_bond_table(
    sections: Dict[str, Parm7Section],
    atom_type_indices: np.ndarray,
    type_name_map: Dict[int, str],
    nbondh: int,
    mbona: int,
    bond_force: np.ndarray,
    bond_equil: np.ndarray,
) -> pd.DataFrame:
    tables: List[pd.DataFrame] = []
    for name, count in (
        ("BONDS_INC_HYDROGEN", nbondh),
        ("BONDS_WITHOUT_HYDROGEN", mbona),
    ):
        values = _parse_int_section(sections, name, count * 3)
        if values.size == 0:
            continue
        records = values.reshape(-1, 3)
        atom_serials = _pointer_to_serial(records[:, :2])
        type_pairs = atom_type_indices[atom_serials - 1]
        type_a = type_pairs[:, 0]
        type_b = type_pairs[:, 1]
        param_index = np.abs(records[:, 2])
        force = _lookup_params(bond_force, param_index)
        equil = _lookup_params(bond_equil, param_index)
        swap = type_a > type_b
        type_min = np.where(swap, type_b, type_a)
        type_max = np.where(swap, type_a, type_b)
        df = pd.DataFrame(
            {
                "type_a": type_min.astype(int),
                "type_b": type_max.astype(int),
                "param_index": param_index.astype(int),
                "force_constant": force,
                "equil_value": equil,
            }
        )
        tables.append(df)
    if not tables:
        return _empty_table(
            [
                "type_a",
                "type_b",
                "type_a_name",
                "type_b_name",
                "param_index",
                "force_constant",
                "equil_value",
                "count",
            ]
        )
    combined = pd.concat(tables, ignore_index=True)
    grouped = (
        combined.groupby(
            ["type_a", "type_b", "param_index", "force_constant", "equil_value"],
            dropna=False,
        )
        .size()
        .reset_index(name="count")
    )
    grouped["type_a_name"] = grouped["type_a"].map(type_name_map)
    grouped["type_b_name"] = grouped["type_b"].map(type_name_map)
    return grouped[
        [
            "type_a",
            "type_a_name",
            "type_b",
            "type_b_name",
            "param_index",
            "force_constant",
            "equil_value",
            "count",
        ]
    ].sort_values(["type_a", "type_b", "param_index"])


def _build_bond_adjacency(
    sections: Dict[str, Parm7Section], nbondh: int, mbona: int
) -> Dict[int, set[int]]:
    adjacency: Dict[int, set[int]] = {}
    for name, count in (
        ("BONDS_INC_HYDROGEN", nbondh),
        ("BONDS_WITHOUT_HYDROGEN", mbona),
    ):
        values = _parse_int_section(sections, name, count * 3)
        if values.size == 0:
            continue
        records = values.reshape(-1, 3)
        atom_serials = _pointer_to_serial(records[:, :2])
        for row in atom_serials:
            atom_a = int(row[0])
            atom_b = int(row[1])
            adjacency.setdefault(atom_a, set()).add(atom_b)
            adjacency.setdefault(atom_b, set()).add(atom_a)
    return adjacency


def _build_rotatable_bonds(
    sections: Dict[str, Parm7Section],
    nbondh: int,
    mbona: int,
    nphih: int,
    mphia: int,
    masses: np.ndarray,
) -> Set[Tuple[int, int]]:
    bonds: Set[Tuple[int, int]] = set()
    for name, count in (
        ("BONDS_INC_HYDROGEN", nbondh),
        ("BONDS_WITHOUT_HYDROGEN", mbona),
    ):
        values = _parse_int_section(sections, name, count * 3)
        if values.size == 0:
            continue
        records = values.reshape(-1, 3)
        atom_serials = _pointer_to_serial(records[:, :2])
        for row in atom_serials:
            atom_a = int(row[0])
            atom_b = int(row[1])
            bonds.add(_sorted_pair(atom_a, atom_b))

    heavy_bonds: Set[Tuple[int, int]] = set()
    for atom_a, atom_b in bonds:
        if atom_a <= 0 or atom_b <= 0:
            continue
        if atom_a > masses.size or atom_b > masses.size:
            continue
        if masses[atom_a - 1] > 3.1 and masses[atom_b - 1] > 3.1:
            heavy_bonds.add((atom_a, atom_b))

    central_bonds: Set[Tuple[int, int]] = set()
    terminal_triplets: Dict[int, List[Tuple[int, int, int]]] = {}
    for name, count in (
        ("DIHEDRALS_INC_HYDROGEN", nphih),
        ("DIHEDRALS_WITHOUT_HYDROGEN", mphia),
    ):
        values = _parse_int_section(sections, name, count * 5)
        if values.size == 0:
            continue
        records = values.reshape(-1, 5)
        atom_serials = _pointer_to_serial(records[:, :4])
        for row in atom_serials:
            atom_i = int(row[0])
            atom_j = int(row[1])
            atom_k = int(row[2])
            atom_l = int(row[3])
            central_bonds.add(_sorted_pair(atom_j, atom_k))
            terminal_triplets.setdefault(atom_i, []).append(
                (atom_j, atom_k, atom_l)
            )
            terminal_triplets.setdefault(atom_l, []).append(
                (atom_i, atom_j, atom_k)
            )

    rotatable: Set[Tuple[int, int]] = set()
    for atom_a, atom_b in heavy_bonds:
        if (atom_a, atom_b) not in central_bonds:
            continue
        neighbors_a: Set[int] = set()
        neighbors_b: Set[int] = set()
        for triple in terminal_triplets.get(atom_a, []):
            if atom_b in triple:
                continue
            neighbors_a.update(triple)
        for triple in terminal_triplets.get(atom_b, []):
            if atom_a in triple:
                continue
            neighbors_b.update(triple)
        if neighbors_a.isdisjoint(neighbors_b):
            rotatable.add((atom_a, atom_b))
    return rotatable


def _build_angle_table(
    sections: Dict[str, Parm7Section],
    atom_type_indices: np.ndarray,
    type_name_map: Dict[int, str],
    nth_eth: int,
    mtheta: int,
    angle_force: np.ndarray,
    angle_equil: np.ndarray,
) -> pd.DataFrame:
    tables: List[pd.DataFrame] = []
    for name, count in (
        ("ANGLES_INC_HYDROGEN", nth_eth),
        ("ANGLES_WITHOUT_HYDROGEN", mtheta),
    ):
        values = _parse_int_section(sections, name, count * 4)
        if values.size == 0:
            continue
        records = values.reshape(-1, 4)
        atom_serials = _pointer_to_serial(records[:, :3])
        type_triplets = atom_type_indices[atom_serials - 1]
        type_i = type_triplets[:, 0]
        type_j = type_triplets[:, 1]
        type_k = type_triplets[:, 2]
        param_index = np.abs(records[:, 3])
        force = _lookup_params(angle_force, param_index)
        equil = _lookup_params(angle_equil, param_index)
        swap = type_i > type_k
        type_i_c = np.where(swap, type_k, type_i)
        type_k_c = np.where(swap, type_i, type_k)
        df = pd.DataFrame(
            {
                "type_i": type_i_c.astype(int),
                "type_j": type_j.astype(int),
                "type_k": type_k_c.astype(int),
                "param_index": param_index.astype(int),
                "force_constant": force,
                "equil_value": equil,
            }
        )
        tables.append(df)
    if not tables:
        return _empty_table(
            [
                "type_i",
                "type_j",
                "type_k",
                "type_i_name",
                "type_j_name",
                "type_k_name",
                "param_index",
                "force_constant",
                "equil_value",
                "count",
            ]
        )
    combined = pd.concat(tables, ignore_index=True)
    grouped = (
        combined.groupby(
            [
                "type_i",
                "type_j",
                "type_k",
                "param_index",
                "force_constant",
                "equil_value",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="count")
    )
    grouped["type_i_name"] = grouped["type_i"].map(type_name_map)
    grouped["type_j_name"] = grouped["type_j"].map(type_name_map)
    grouped["type_k_name"] = grouped["type_k"].map(type_name_map)
    return grouped[
        [
            "type_i",
            "type_i_name",
            "type_j",
            "type_j_name",
            "type_k",
            "type_k_name",
            "param_index",
            "force_constant",
            "equil_value",
            "count",
        ]
    ].sort_values(["type_i", "type_j", "type_k", "param_index"])


def _build_dihedral_table(
    sections: Dict[str, Parm7Section],
    atom_names: List[str],
    amber_atom_types: List[str],
    nphih: int,
    mphia: int,
    dihedral_force: np.ndarray,
    dihedral_periodicity: np.ndarray,
    dihedral_phase: np.ndarray,
    scee_scale: np.ndarray,
    scnb_scale: np.ndarray,
    nbondh: int,
    mbona: int,
    masses: np.ndarray,
) -> pd.DataFrame:
    rotatable_bonds = _build_rotatable_bonds(
        sections, nbondh, mbona, nphih, mphia, masses
    )
    entries: List[Tuple[int, int, int, int, int, int]] = []
    term_idx = 1
    for name, count in (
        ("DIHEDRALS_INC_HYDROGEN", nphih),
        ("DIHEDRALS_WITHOUT_HYDROGEN", mphia),
    ):
        values = _parse_int_section(sections, name, count * 5)
        if values.size == 0:
            continue
        records = values.reshape(-1, 5)
        atom_serials = _pointer_to_serial(records[:, :4])
        param_index = np.abs(records[:, 4]).astype(int)
        for idx in range(atom_serials.shape[0]):
            atom_i = int(atom_serials[idx, 0])
            atom_j = int(atom_serials[idx, 1])
            atom_k = int(atom_serials[idx, 2])
            atom_l = int(atom_serials[idx, 3])
            entries.append((atom_i, atom_j, atom_k, atom_l, int(param_index[idx]), term_idx))
            term_idx += 1
    if not entries:
        return _empty_table(
            [
                "ID",
                "idx",
                "ijkl indices",
                "ijkl names",
                "ijkl types",
                "rotatable",
                "k",
                "pdcty",
                "phase",
                "scee",
                "scnb",
            ]
        )

    entries_array = np.array(entries, dtype=int)
    atoms = entries_array[:, :4]
    param_index = entries_array[:, 4]
    idx_values = entries_array[:, 5]
    force = _lookup_params(dihedral_force, param_index)
    periodicity = _lookup_params(dihedral_periodicity, param_index)
    phase = _lookup_params(dihedral_phase, param_index)
    scee = _lookup_params(scee_scale, param_index)
    scnb = _lookup_params(scnb_scale, param_index)
    rows: List[Dict[str, object]] = []
    id_by_ijkl: Dict[Tuple[int, int, int, int], int] = {}
    next_id = 1
    for idx in range(entries_array.shape[0]):
        atom_i, atom_j, atom_k, atom_l = atoms[idx]
        key = (int(atom_i), int(atom_j), int(atom_k), int(atom_l))
        if key not in id_by_ijkl:
            id_by_ijkl[key] = next_id
            next_id += 1
        name_i, name_j, name_k, name_l = _lookup_ijkl_labels(atom_names, atom_i, atom_j, atom_k, atom_l)
        type_i, type_j, type_k, type_l = _lookup_ijkl_labels(
            amber_atom_types, atom_i, atom_j, atom_k, atom_l
        )
        bond_key = _sorted_pair(int(atom_j), int(atom_k))
        rotatable = "T" if bond_key in rotatable_bonds else "F"
        rows.append(
            {
                "ID": id_by_ijkl[key],
                "idx": int(idx_values[idx]),
                "ijkl indices": f"{atom_i}, {atom_j}, {atom_k}, {atom_l}",
                "ijkl names": f"{name_i}, {name_j}, {name_k}, {name_l}",
                "ijkl types": f"{type_i}, {type_j}, {type_k}, {type_l}",
                "rotatable": rotatable,
                "k": force[idx],
                "pdcty": periodicity[idx],
                "phase": phase[idx],
                "scee": scee[idx],
                "scnb": scnb[idx],
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "ID",
            "idx",
            "ijkl indices",
            "ijkl names",
            "ijkl types",
            "rotatable",
            "k",
            "pdcty",
            "phase",
            "scee",
            "scnb",
        ],
    )


def _build_improper_table(
    sections: Dict[str, Parm7Section],
    atom_names: List[str],
    amber_atom_types: List[str],
    nphih: int,
    mphia: int,
    dihedral_force: np.ndarray,
    dihedral_periodicity: np.ndarray,
    dihedral_phase: np.ndarray,
    scee_scale: np.ndarray,
    scnb_scale: np.ndarray,
    adjacency: Dict[int, set[int]],
) -> pd.DataFrame:
    entries: List[Tuple[int, int, int, int, int, int]] = []
    term_idx = 1
    for name, count in (
        ("DIHEDRALS_INC_HYDROGEN", nphih),
        ("DIHEDRALS_WITHOUT_HYDROGEN", mphia),
    ):
        values = _parse_int_section(sections, name, count * 5)
        if values.size == 0:
            continue
        records = values.reshape(-1, 5)
        atom_serials = _pointer_to_serial(records[:, :4])
        param_index = np.abs(records[:, 4]).astype(int)
        for idx in range(atom_serials.shape[0]):
            raw_l = int(records[idx, 3])
            if raw_l < 0:
                atom_i = int(atom_serials[idx, 0])
                atom_j = int(atom_serials[idx, 1])
                atom_k = int(atom_serials[idx, 2])
                atom_l = int(atom_serials[idx, 3])
                entries.append(
                    (
                        atom_i,
                        atom_j,
                        atom_k,
                        atom_l,
                        int(param_index[idx]),
                        term_idx,
                    )
                )
            term_idx += 1
    if not entries:
        return _empty_table(
            [
                "ID",
                "idx",
                "ijkl indices",
                "ijkl names",
                "ijkl types",
                "force_constant",
                "periodicity",
                "phase",
                "scee",
                "scnb",
            ]
        )

    entries_array = np.array(entries, dtype=int)
    atoms = entries_array[:, :4]
    param_index = entries_array[:, 4]
    idx_values = entries_array[:, 5]
    force = _lookup_params(dihedral_force, param_index)
    periodicity = _lookup_params(dihedral_periodicity, param_index)
    phase = _lookup_params(dihedral_phase, param_index)
    scee = _lookup_params(scee_scale, param_index)
    scnb = _lookup_params(scnb_scale, param_index)
    rows: List[Dict[str, object]] = []
    id_by_ijkl: Dict[Tuple[int, int, int, int], int] = {}
    next_id = 1
    for idx in range(entries_array.shape[0]):
        atom_i, atom_j, atom_k, atom_l = atoms[idx]
        key = (int(atom_i), int(atom_j), int(atom_k), int(atom_l))
        if key not in id_by_ijkl:
            id_by_ijkl[key] = next_id
            next_id += 1
        name_i, name_j, name_k, name_l = _lookup_ijkl_labels(
            atom_names, atom_i, atom_j, atom_k, atom_l
        )
        type_i, type_j, type_k, type_l = _lookup_ijkl_labels(
            amber_atom_types, atom_i, atom_j, atom_k, atom_l
        )
        rows.append(
            {
                "ID": id_by_ijkl[key],
                "idx": int(idx_values[idx]),
                "ijkl indices": f"{atom_i}, {atom_j}, {atom_k}, {atom_l}",
                "ijkl names": f"{name_i}, {name_j}, {name_k}, {name_l}",
                "ijkl types": f"{type_i}, {type_j}, {type_k}, {type_l}",
                "force_constant": force[idx],
                "periodicity": periodicity[idx],
                "phase": phase[idx],
                "scee": scee[idx],
                "scnb": scnb[idx],
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "ID",
            "idx",
            "ijkl indices",
            "ijkl names",
            "ijkl types",
            "force_constant",
            "periodicity",
            "phase",
            "scee",
            "scnb",
        ],
    )


def _build_one_four_table(
    sections: Dict[str, Parm7Section],
    atom_type_indices: np.ndarray,
    type_name_map: Dict[int, str],
    nphih: int,
    mphia: int,
    scee_scale: np.ndarray,
    scnb_scale: np.ndarray,
    nonbond_index: np.ndarray,
    acoef: np.ndarray,
    bcoef: np.ndarray,
    hbond_acoef: np.ndarray,
    hbond_bcoef: np.ndarray,
    ntypes: int,
) -> pd.DataFrame:
    tables: List[pd.DataFrame] = []
    for name, count in (
        ("DIHEDRALS_INC_HYDROGEN", nphih),
        ("DIHEDRALS_WITHOUT_HYDROGEN", mphia),
    ):
        values = _parse_int_section(sections, name, count * 5)
        if values.size == 0:
            continue
        records = values.reshape(-1, 5)
        mask = (records[:, 2] >= 0) & (records[:, 3] >= 0)
        if not mask.any():
            continue
        records = records[mask]
        atom_serials = _pointer_to_serial(records[:, [0, 3]])
        type_pairs = atom_type_indices[atom_serials - 1]
        type_a = type_pairs[:, 0]
        type_b = type_pairs[:, 1]
        param_index = np.abs(records[:, 4])
        scee = _lookup_params(scee_scale, param_index)
        scnb = _lookup_params(scnb_scale, param_index)
        pair_index, a_pair, b_pair, rmin, epsilon, source = _lookup_nonbonded_pair(
            nonbond_index,
            acoef,
            bcoef,
            hbond_acoef,
            hbond_bcoef,
            ntypes,
            type_a,
            type_b,
        )
        swap = type_a > type_b
        type_min = np.where(swap, type_b, type_a)
        type_max = np.where(swap, type_a, type_b)
        df = pd.DataFrame(
            {
                "type_a": type_min.astype(int),
                "type_b": type_max.astype(int),
                "param_index": param_index.astype(int),
                "scee": scee,
                "scnb": scnb,
                "pair_index": pair_index,
                "acoef": a_pair,
                "bcoef": b_pair,
                "rmin": rmin,
                "epsilon": epsilon,
                "source": source,
            }
        )
        tables.append(df)
    if not tables:
        return _empty_table(
            [
                "type_a",
                "type_b",
                "type_a_name",
                "type_b_name",
                "param_index",
                "scee",
                "scnb",
                "pair_index",
                "acoef",
                "bcoef",
                "rmin",
                "epsilon",
                "source",
                "count",
            ]
        )
    combined = pd.concat(tables, ignore_index=True)
    grouped = (
        combined.groupby(
            [
                "type_a",
                "type_b",
                "param_index",
                "scee",
                "scnb",
                "pair_index",
                "acoef",
                "bcoef",
                "rmin",
                "epsilon",
                "source",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="count")
    )
    grouped["type_a_name"] = grouped["type_a"].map(type_name_map)
    grouped["type_b_name"] = grouped["type_b"].map(type_name_map)
    return grouped[
        [
            "type_a",
            "type_a_name",
            "type_b",
            "type_b_name",
            "param_index",
            "scee",
            "scnb",
            "pair_index",
            "acoef",
            "bcoef",
            "rmin",
            "epsilon",
            "source",
            "count",
        ]
    ].sort_values(["type_a", "type_b", "param_index"])


def _build_nonbonded_table(
    nonbond_index: np.ndarray,
    type_name_map: Dict[int, str],
    acoef: np.ndarray,
    bcoef: np.ndarray,
    hbond_acoef: np.ndarray,
    hbond_bcoef: np.ndarray,
    ntypes: int,
) -> pd.DataFrame:
    matrix = nonbond_index.reshape(ntypes, ntypes)
    idx_i, idx_j = np.triu_indices(ntypes)
    type_a = idx_i + 1
    type_b = idx_j + 1
    pair_index = matrix[idx_i, idx_j]
    a_pair, b_pair, rmin, epsilon, source = _lookup_pair_values(
        pair_index, acoef, bcoef, hbond_acoef, hbond_bcoef
    )
    df = pd.DataFrame(
        {
            "type_a": type_a.astype(int),
            "type_b": type_b.astype(int),
            "pair_index": pair_index.astype(int),
            "acoef": a_pair,
            "bcoef": b_pair,
            "rmin": rmin,
            "epsilon": epsilon,
            "source": source,
        }
    )
    df["type_a_name"] = df["type_a"].map(type_name_map)
    df["type_b_name"] = df["type_b"].map(type_name_map)
    df = df[
        [
            "type_a",
            "type_a_name",
            "type_b",
            "type_b_name",
            "pair_index",
            "acoef",
            "bcoef",
            "rmin",
            "epsilon",
            "source",
        ]
    ]
    return df.sort_values(["type_a", "type_b"])


def _pointer_to_serial(values: np.ndarray) -> np.ndarray:
    return np.abs(values) // 3 + 1


def _lookup_params(values: np.ndarray, indices: np.ndarray) -> np.ndarray:
    result = np.full(indices.shape, np.nan, dtype=float)
    if values.size == 0:
        return result
    valid = (indices > 0) & (indices <= values.size)
    result[valid] = values[indices[valid] - 1]
    return result


def _sorted_pair(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a <= b else (b, a)




def _lookup_pair_values(
    pair_index: np.ndarray,
    acoef: np.ndarray,
    bcoef: np.ndarray,
    hbond_acoef: np.ndarray,
    hbond_bcoef: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    a_pair = np.full(pair_index.shape, np.nan, dtype=float)
    b_pair = np.full(pair_index.shape, np.nan, dtype=float)
    rmin = np.full(pair_index.shape, np.nan, dtype=float)
    epsilon = np.full(pair_index.shape, np.nan, dtype=float)
    source = np.full(pair_index.shape, "", dtype=object)
    positive = pair_index > 0
    negative = pair_index < 0
    if positive.any():
        a_pair[positive] = acoef[pair_index[positive] - 1]
        b_pair[positive] = bcoef[pair_index[positive] - 1]
        valid = positive & (a_pair > 0) & (b_pair > 0)
        epsilon[valid] = (b_pair[valid] ** 2) / (4.0 * a_pair[valid])
        rmin[valid] = np.power(2.0 * a_pair[valid] / b_pair[valid], 1.0 / 6.0)
        source[positive] = "LJ"
    if negative.any() and hbond_acoef.size and hbond_bcoef.size:
        hb_index = np.abs(pair_index[negative]) - 1
        valid_hb = hb_index < hbond_acoef.size
        hb_a = np.full(hb_index.shape, np.nan, dtype=float)
        hb_b = np.full(hb_index.shape, np.nan, dtype=float)
        hb_a[valid_hb] = hbond_acoef[hb_index[valid_hb]]
        hb_b[valid_hb] = hbond_bcoef[hb_index[valid_hb]]
        a_pair[negative] = hb_a
        b_pair[negative] = hb_b
        source[negative] = "HBOND"
    return a_pair, b_pair, rmin, epsilon, source


def _lookup_nonbonded_pair(
    nonbond_index: np.ndarray,
    acoef: np.ndarray,
    bcoef: np.ndarray,
    hbond_acoef: np.ndarray,
    hbond_bcoef: np.ndarray,
    ntypes: int,
    type_a: np.ndarray,
    type_b: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    idx = (type_a - 1) * ntypes + (type_b - 1)
    idx_rev = (type_b - 1) * ntypes + (type_a - 1)
    pair_index = nonbond_index[idx]
    alt = nonbond_index[idx_rev]
    use_alt = (pair_index == 0) & (alt != 0)
    pair_index = np.where(use_alt, alt, pair_index)
    a_pair, b_pair, rmin, epsilon, source = _lookup_pair_values(
        pair_index, acoef, bcoef, hbond_acoef, hbond_bcoef
    )
    return (
        pair_index.astype(int),
        a_pair,
        b_pair,
        rmin,
        epsilon,
        source,
    )


def _lookup_ijkl_labels(
    values: List[str], atom_i: int, atom_j: int, atom_k: int, atom_l: int
) -> Tuple[str, str, str, str]:
    return (
        _lookup_label(values, atom_i),
        _lookup_label(values, atom_j),
        _lookup_label(values, atom_k),
        _lookup_label(values, atom_l),
    )


def _lookup_label(values: List[str], atom_index: int) -> str:
    idx = int(atom_index) - 1
    if idx < 0 or idx >= len(values):
        return ""
    return str(values[idx]).strip()


def _empty_table(columns: Iterable[str]) -> pd.DataFrame:
    return pd.DataFrame({column: pd.Series(dtype=object) for column in columns})


def _df_to_table(df: pd.DataFrame) -> Dict[str, object]:
    safe = df.where(pd.notnull(df), None)
    columns = [str(col) for col in safe.columns]
    rows = [[_to_native(value) for value in row] for row in safe.itertuples(index=False)]
    return {"columns": columns, "rows": rows}


def _to_native(value: object) -> Optional[object]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.bool_):
        return bool(value)
    return value
