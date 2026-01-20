"""Lennard-Jones table builders."""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np

from topview.model.state import Parm7Token
from topview.services.parm7 import parse_float_token_value, parse_int_token_value

LJ_MIN_COEF = 1.0e-10
LJ_ONE_SIXTH = 1.0 / 6.0


def _parse_fixed_int_values(
    values: List[str], expected_count: int, label: str
) -> List[int]:
    """Parse integer values using a vectorized backend.

    Parameters
    ----------
    values
        Raw string values.
    expected_count
        Expected number of values.
    label
        Section label for error reporting.

    Returns
    -------
    list
        Parsed integer values.

    Raises
    ------
    ValueError
        If the parsed length does not match the expected count.
    """

    if len(values) != expected_count:
        raise ValueError(
            f"{label} length {len(values)} does not match expected {expected_count}"
        )
    text = " ".join(values)
    parsed = np.fromstring(text, sep=" ", dtype=float)
    if parsed.size != expected_count:
        raise ValueError(
            f"{label} parsed {parsed.size} values but expected {expected_count}"
        )
    return parsed.astype(int).tolist()


def _parse_fixed_float_values(
    values: List[str], expected_count: int, label: str
) -> List[float]:
    """Parse float values using a vectorized backend.

    Parameters
    ----------
    values
        Raw string values.
    expected_count
        Expected number of values.
    label
        Section label for error reporting.

    Returns
    -------
    list
        Parsed float values.

    Raises
    ------
    ValueError
        If the parsed length does not match the expected count.
    """

    if len(values) != expected_count:
        raise ValueError(
            f"{label} length {len(values)} does not match expected {expected_count}"
        )
    text = " ".join(values).replace("D", "E").replace("d", "e")
    parsed = np.fromstring(text, sep=" ", dtype=float)
    if parsed.size != expected_count:
        raise ValueError(
            f"{label} parsed {parsed.size} values but expected {expected_count}"
        )
    return parsed.tolist()


def build_lj_by_type(
    atom_type_indices: List[int],
    nonbond_index: List[int],
    acoef_values: List[float],
    bcoef_values: List[float],
) -> Dict[int, Dict[str, float]]:
    """Compute diagonal LJ parameters indexed by atom type.

    Parameters
    ----------
    atom_type_indices
        Atom type indices per atom.
    nonbond_index
        Flattened nonbonded index array.
    acoef_values
        LENNARD_JONES_ACOEF values.
    bcoef_values
        LENNARD_JONES_BCOEF values.

    Returns
    -------
    dict
        Mapping of type index to LJ parameters.
    """

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
        entry = {
            "rmin": 0.0,
            "epsilon": 0.0,
            "acoef": None,
            "bcoef": None,
            "pair_index": None,
        }
        if offset >= len(nonbond_index):
            lj_by_type[type_index] = entry
            continue
        pair_index = nonbond_index[offset]
        entry["pair_index"] = int(pair_index)
        if pair_index > 0:
            pair_offset = pair_index - 1
            if pair_offset < len(acoef_values) and pair_offset < len(bcoef_values):
                acoef = acoef_values[pair_offset]
                bcoef = bcoef_values[pair_offset]
                entry["acoef"] = acoef
                entry["bcoef"] = bcoef
                if acoef >= LJ_MIN_COEF and bcoef >= LJ_MIN_COEF:
                    factor = 2.0 * acoef / bcoef
                    entry["rmin"] = pow(factor, LJ_ONE_SIXTH) * 0.5
                    entry["epsilon"] = bcoef / 2.0 / factor
        lj_by_type[type_index] = entry
    return lj_by_type


def build_lj_by_type_from_tokens(
    atom_type_indices: List[int],
    nonbond_tokens: List[Parm7Token],
    acoef_tokens: List[Parm7Token],
    bcoef_tokens: List[Parm7Token],
) -> Dict[int, Dict[str, float]]:
    """Compute LJ tables using raw parm7 tokens.

    Parameters
    ----------
    atom_type_indices
        Atom type indices per atom.
    nonbond_tokens
        NONBONDED_PARM_INDEX tokens.
    acoef_tokens
        LENNARD_JONES_ACOEF tokens.
    bcoef_tokens
        LENNARD_JONES_BCOEF tokens.

    Returns
    -------
    dict
        Mapping of type index to LJ parameters.
    """

    lj_by_type: Dict[int, Dict[str, float]] = {}
    if not atom_type_indices:
        return lj_by_type
    ntypes = max(atom_type_indices)
    if ntypes <= 0:
        return lj_by_type
    for type_index in range(1, ntypes + 1):
        offset = (type_index - 1) * ntypes + (type_index - 1)
        entry = {
            "rmin": 0.0,
            "epsilon": 0.0,
            "acoef": None,
            "bcoef": None,
            "pair_index": None,
        }
        if offset >= len(nonbond_tokens):
            lj_by_type[type_index] = entry
            continue
        pair_index = parse_int_token_value(nonbond_tokens[offset])
        entry["pair_index"] = int(pair_index)
        if pair_index > 0:
            pair_offset = pair_index - 1
            if pair_offset < len(acoef_tokens) and pair_offset < len(bcoef_tokens):
                acoef = parse_float_token_value(acoef_tokens[pair_offset])
                bcoef = parse_float_token_value(bcoef_tokens[pair_offset])
                entry["acoef"] = acoef
                entry["bcoef"] = bcoef
                if acoef >= LJ_MIN_COEF and bcoef >= LJ_MIN_COEF:
                    factor = 2.0 * acoef / bcoef
                    entry["rmin"] = pow(factor, LJ_ONE_SIXTH) * 0.5
                    entry["epsilon"] = bcoef / 2.0 / factor
        lj_by_type[type_index] = entry
    return lj_by_type


def compute_lj_tables(
    atom_type_values: List[str],
    nonbond_values: List[str],
    acoef_values: List[str],
    bcoef_values: List[str],
    *,
    natom: Optional[int] = None,
    ntypes: Optional[int] = None,
) -> Dict[str, object]:
    """Compute LJ tables from raw string values (multiprocessing friendly).

    Parameters
    ----------
    atom_type_values
        Raw string values from ATOM_TYPE_INDEX.
    nonbond_values
        Raw string values from NONBONDED_PARM_INDEX.
    acoef_values
        Raw string values from LENNARD_JONES_ACOEF.
    bcoef_values
        Raw string values from LENNARD_JONES_BCOEF.
    natom
        Expected atom count from POINTERS (NATOM).
    ntypes
        Expected LJ type count from POINTERS (NTYPES).

    Returns
    -------
    dict
        Parsed atom type indices and LJ tables.

    Raises
    ------
    ValueError
        If expected counts are missing or parsing fails.
    """

    if natom is None or ntypes is None:
        raise ValueError("natom and ntypes are required for LJ table parsing")
    expected_nonbond = ntypes * ntypes
    expected_coef = ntypes * (ntypes + 1) // 2
    atom_type_indices = _parse_fixed_int_values(
        atom_type_values, natom, "ATOM_TYPE_INDEX"
    )
    nonbond_index = _parse_fixed_int_values(
        nonbond_values, expected_nonbond, "NONBONDED_PARM_INDEX"
    )
    acoef = _parse_fixed_float_values(
        acoef_values, expected_coef, "LENNARD_JONES_ACOEF"
    )
    bcoef = _parse_fixed_float_values(
        bcoef_values, expected_coef, "LENNARD_JONES_BCOEF"
    )
    lj_by_type = build_lj_by_type(atom_type_indices, nonbond_index, acoef, bcoef)
    return {"atom_type_indices": atom_type_indices, "lj_by_type": lj_by_type}
