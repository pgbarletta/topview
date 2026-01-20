"""System loading utilities."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import logging
import os
import time
from typing import Callable, Dict, List, Optional, Tuple

import MDAnalysis as mda
from MDAnalysis.exceptions import NoDataError

from topview.config import CHARGE_SCALE
from topview.errors import ModelError
from topview.model.state import AtomMeta, Parm7Section, ResidueMeta
from topview.services.lj import compute_lj_tables
from topview.services.parm7 import parse_parm7, parse_pointers
from topview.services.pdb_writer import write_pdb

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemLoadResult:
    """Result of loading a parm7/rst7 system.

    Attributes
    ----------
    meta_list
        List of atom metadata in serial order.
    meta_by_serial
        Atom metadata keyed by serial.
    residue_index
        Mapping of residue key to atom serials.
    residue_keys_by_resid
        Mapping of resid to possible residue keys.
    parm7_text_b64
        Base64-encoded parm7 text.
    parm7_sections
        Parsed parm7 sections keyed by flag.
    pdb_b64
        Base64-encoded PDB text.
    natoms
        Atom count.
    nresidues
        Residue count.
    warnings
        List of topology warnings.
    timings
        Timing breakdown for the load pipeline.
    """

    meta_list: List[AtomMeta]
    meta_by_serial: Dict[int, AtomMeta]
    residue_index: Dict[str, List[int]]
    residue_keys_by_resid: Dict[int, List[str]]
    parm7_text_b64: str
    parm7_sections: Dict[str, Parm7Section]
    pdb_b64: str
    natoms: int
    nresidues: int
    warnings: List[str]
    timings: Dict[str, float]


def _timed_call(fn: Callable[..., object], *args: object, **kwargs: object):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


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


def load_system_data(
    parm7_path: str,
    rst7_path: str,
    cpu_submit: Optional[Callable[..., object]] = None,
) -> SystemLoadResult:
    """Load the topology and coordinates into in-memory metadata.

    Parameters
    ----------
    parm7_path
        Path to the parm7/prmtop file.
    rst7_path
        Path to the rst7/inpcrd file.
    cpu_submit
        Optional executor submission function for CPU-heavy work.

    Returns
    -------
    SystemLoadResult
        Parsed metadata, PDB text, and parm7 sections.

    Raises
    ------
    ModelError
        If files are missing or loading fails.
    """

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
        parm7_future = executor.submit(_timed_call, parse_parm7, parm7_path)
        try:
            universe, universe_time = universe_future.result()
        except Exception as exc:
            parm7_future.cancel()
            logger.exception("MDAnalysis load failed")
            raise ModelError(
                "load_failed", "Failed to load MDAnalysis Universe", str(exc)
            ) from exc
        try:
            (parm7_text, parm7_sections), parm7_time = parm7_future.result()
        except Exception as exc:
            logger.exception("Failed to parse parm7 file")
            raise ModelError(
                "parm7_parse_failed", "Failed to parse parm7 file", str(exc)
            ) from exc

    parm7_text_b64 = base64.b64encode(parm7_text.encode("utf-8")).decode("ascii")

    pointer_section = parm7_sections.get("POINTERS")
    if not pointer_section or not pointer_section.tokens:
        raise ModelError("parm7_parse_failed", "POINTERS section missing")
    try:
        pointers = parse_pointers(pointer_section)
    except ValueError as exc:
        raise ModelError("parm7_parse_failed", "Failed to parse POINTERS", str(exc)) from exc

    natom = int(pointers.get("NATOM", 0))
    ntypes = int(pointers.get("NTYPES", 0))
    if natom <= 0 or ntypes <= 0:
        raise ModelError(
            "parm7_parse_failed",
            "Invalid POINTERS values for NATOM/NTYPES",
            {"NATOM": natom, "NTYPES": ntypes},
        )

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
        atom_type_values = [token.value for token in atom_type_index_section.tokens]
        nonbond_values = (
            [token.value for token in nonbond_index_section.tokens]
            if nonbond_index_section
            else []
        )
        acoef_values = (
            [token.value for token in acoef_section.tokens]
            if acoef_section
            else []
        )
        bcoef_values = (
            [token.value for token in bcoef_section.tokens]
            if bcoef_section
            else []
        )
        if not nonbond_values or not acoef_values or not bcoef_values:
            raise ModelError(
                "parm7_parse_failed",
                "Missing LJ sections required for nonbonded parameters",
            )
        try:
            result = compute_lj_tables(
                atom_type_values,
                nonbond_values,
                acoef_values,
                bcoef_values,
                natom=natom,
                ntypes=ntypes,
            )
        except ValueError as exc:
            raise ModelError("parm7_parse_failed", "Failed to parse LJ tables", str(exc)) from exc
        atom_type_indices = result.get("atom_type_indices", [])
        lj_by_type = result.get("lj_by_type", {})
    lj_time = time.perf_counter() - lj_start

    meta_list: List[AtomMeta] = []
    meta_by_serial: Dict[int, AtomMeta] = {}
    residue_keys_by_resid: Dict[int, List[str]] = {}
    residue_index_map: Dict[str, List[int]] = {}

    atoms = universe.atoms
    natoms = len(atoms)

    attrs_start = time.perf_counter()
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
    meta_attrs_time = time.perf_counter() - attrs_start

    build_start = time.perf_counter()
    guess_element = _guess_element
    element_cache: Dict[str, Optional[str]] = {}
    cache_missing = object()
    charge_tokens = charge_section.tokens if charge_section else None
    atom_type_indices_local = atom_type_indices
    lj_by_type_local = lj_by_type
    names_list = names
    resids_list = resids
    resnames_list = resnames
    resindices_list = resindices
    segids_list = segids
    chains_list = chains
    elements_list = elements
    positions_arr = positions
    charges_list = charges
    masses_list = masses
    types_list = types
    ResidueMetaCls = ResidueMeta
    AtomMetaCls = AtomMeta
    meta_list_append = meta_list.append
    meta_by_serial_set = meta_by_serial.__setitem__
    residue_index_map_setdefault = residue_index_map.setdefault
    residue_keys_by_resid_setdefault = residue_keys_by_resid.setdefault

    for idx in range(natoms):
        serial = idx + 1
        resid = int(resids_list[idx])
        resname = str(resnames_list[idx]).strip()
        residue_serial_index = int(resindices_list[idx]) + 1
        segid = segids_list[idx] if segids_list is not None else None
        chain = chains_list[idx] if chains_list is not None else None
        residue_meta = ResidueMetaCls(
            resid=resid, resname=resname, segid=segid, chain=chain
        )

        name_str = str(names_list[idx]).strip()
        element = elements_list[idx] if elements_list is not None else None
        if element:
            element = str(element).strip().title()
        else:
            cached = element_cache.get(name_str, cache_missing)
            if cached is cache_missing:
                cached = guess_element(name_str)
                element_cache[name_str] = cached
            element = cached

        atom_type = types_list[idx] if types_list is not None else None
        atom_type_index = None
        lj_rmin = None
        lj_epsilon = None
        lj_acoef = None
        lj_bcoef = None
        lj_pair_index = None
        if atom_type_indices_local and idx < len(atom_type_indices_local):
            atom_type_index = atom_type_indices_local[idx]
            if atom_type_index and atom_type_index in lj_by_type_local:
                lj_entry = lj_by_type_local[atom_type_index]
                lj_rmin = lj_entry.get("rmin")
                lj_epsilon = lj_entry.get("epsilon")
                lj_acoef = lj_entry.get("acoef")
                lj_bcoef = lj_entry.get("bcoef")
                lj_pair_index = lj_entry.get("pair_index")
        charge = charges_list[idx] if charges_list is not None else None
        charge_raw_str = None
        charge_e = None
        if charge_tokens and idx < len(charge_tokens):
            charge_raw_str = charge_tokens[idx].value.strip()
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
        mass = masses_list[idx] if masses_list is not None else None

        coords = (
            float(positions_arr[idx][0]),
            float(positions_arr[idx][1]),
            float(positions_arr[idx][2]),
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

        meta = AtomMetaCls(
            serial=serial,
            atom_name=name_str,
            element=element,
            residue=residue_meta,
            residue_index=residue_serial_index,
            coords=coords,
            parm7=parm7,
        )

        meta_list_append(meta)
        meta_by_serial_set(serial, meta)

        residue_key = f"{segid or ''}:{resid}:{resname}"
        residue_index_map_setdefault(residue_key, []).append(serial)
        residue_keys_by_resid_setdefault(resid, []).append(residue_key)

    meta_build_time = time.perf_counter() - build_start
    pdb_start = time.perf_counter()
    pdb_text = write_pdb(meta_list)
    pdb_time = time.perf_counter() - pdb_start
    pdb_b64 = base64.b64encode(pdb_text.encode("ascii")).decode("ascii")

    total_time = time.perf_counter() - total_start
    logger.debug(
        "System loaded: atoms=%d residues=%d",
        len(meta_list),
        len(universe.residues),
    )
    timings = {
        "universe": universe_time,
        "parm7": parm7_time,
        "lj": lj_time,
        "meta_attrs": meta_attrs_time,
        "meta_build": meta_build_time,
        "pdb": pdb_time,
        "total": total_time,
    }

    return SystemLoadResult(
        meta_list=meta_list,
        meta_by_serial=meta_by_serial,
        residue_index=residue_index_map,
        residue_keys_by_resid=residue_keys_by_resid,
        parm7_text_b64=parm7_text_b64,
        parm7_sections=parm7_sections,
        pdb_b64=pdb_b64,
        natoms=len(meta_list),
        nresidues=len(universe.residues),
        warnings=warnings,
        timings=timings,
    )
