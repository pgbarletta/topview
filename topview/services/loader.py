"""System loading utilities."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import logging
import os
import time
import warnings
from typing import Callable, Dict, List, Optional, Tuple

import MDAnalysis as mda
from MDAnalysis.exceptions import NoDataError

from topview.config import CHARGE_SCALE, DEFAULT_RESNAME, RESNAME_ALL
from topview.errors import ModelError
from topview.model.state import AtomMeta, Parm7Section, ResidueMeta
from topview.services.lj import compute_lj_tables
from topview.services.nmr_restraints import (
    parse_nmr_restraints,
    summarize_nmr_restraints,
)
from topview.services.parm7 import describe_section, parse_int_tokens, parse_parm7, parse_pointers
from topview.services.pdb_writer import write_pdb

logger = logging.getLogger(__name__)

_BOND_ORDER_SINGLE = 1
_BOND_ORDER_DOUBLE = 2
_BOND_ORDER_TRIPLE = 3
_BOND_ORDER_AROMATIC = 4

_AMBER_TYPE_PAIR_BOND_ORDER: Dict[Tuple[str, str], int] = {
    # --- C=O double bonds (any carbon with 'o': one-connected O) ---
    ("c", "o"): _BOND_ORDER_DOUBLE,
    ("c1", "o"): _BOND_ORDER_DOUBLE,
    ("c2", "o"): _BOND_ORDER_DOUBLE,
    ("c3", "o"): _BOND_ORDER_DOUBLE,
    ("c5", "o"): _BOND_ORDER_DOUBLE,
    ("c6", "o"): _BOND_ORDER_DOUBLE,
    ("ca", "o"): _BOND_ORDER_DOUBLE,
    ("cc", "o"): _BOND_ORDER_DOUBLE,
    ("cd", "o"): _BOND_ORDER_DOUBLE,
    ("ce", "o"): _BOND_ORDER_DOUBLE,
    ("cf", "o"): _BOND_ORDER_DOUBLE,
    ("cg", "o"): _BOND_ORDER_DOUBLE,
    ("ch", "o"): _BOND_ORDER_DOUBLE,
    ("cp", "o"): _BOND_ORDER_DOUBLE,
    ("cq", "o"): _BOND_ORDER_DOUBLE,
    ("cs", "o"): _BOND_ORDER_DOUBLE,
    ("cu", "o"): _BOND_ORDER_DOUBLE,
    ("cv", "o"): _BOND_ORDER_DOUBLE,
    ("cx", "o"): _BOND_ORDER_DOUBLE,
    ("cy", "o"): _BOND_ORDER_DOUBLE,
    ("cz", "o"): _BOND_ORDER_DOUBLE,
    # --- C=S double bonds (any carbon with 's': one-connected S) ---
    ("c", "s"): _BOND_ORDER_DOUBLE,
    ("c1", "s"): _BOND_ORDER_DOUBLE,
    ("c2", "s"): _BOND_ORDER_DOUBLE,
    ("ca", "s"): _BOND_ORDER_DOUBLE,
    ("cc", "s"): _BOND_ORDER_DOUBLE,
    ("cd", "s"): _BOND_ORDER_DOUBLE,
    ("ce", "s"): _BOND_ORDER_DOUBLE,
    ("cf", "s"): _BOND_ORDER_DOUBLE,
    ("cs", "s"): _BOND_ORDER_DOUBLE,
    # --- C≡C triple bonds ---
    ("c1", "c1"): _BOND_ORDER_TRIPLE,
    # --- C≡N triple bonds (Sp C with Sp N) ---
    ("c1", "n1"): _BOND_ORDER_TRIPLE,
    ("cg", "n1"): _BOND_ORDER_TRIPLE,
    ("ch", "n1"): _BOND_ORDER_TRIPLE,
    # --- N≡N triple bonds ---
    ("n1", "n1"): _BOND_ORDER_TRIPLE,
    # --- Conjugated Sp C–C double bonds ---
    ("c1", "cg"): _BOND_ORDER_DOUBLE,
    ("c1", "ch"): _BOND_ORDER_DOUBLE,
    ("cg", "cg"): _BOND_ORDER_DOUBLE,
    ("cg", "ch"): _BOND_ORDER_DOUBLE,
    ("ch", "ch"): _BOND_ORDER_DOUBLE,
    # --- C=N double bonds (only with non-aromatic sp2 N types) ---
    ("c1", "n"): _BOND_ORDER_DOUBLE,
    ("c1", "n2"): _BOND_ORDER_DOUBLE,
    ("c2", "n"): _BOND_ORDER_DOUBLE,
    ("c2", "n2"): _BOND_ORDER_DOUBLE,
    ("ca", "n2"): _BOND_ORDER_DOUBLE,
    ("cc", "n"): _BOND_ORDER_DOUBLE,
    ("cc", "n2"): _BOND_ORDER_DOUBLE,
    ("cd", "n"): _BOND_ORDER_DOUBLE,
    ("cd", "n2"): _BOND_ORDER_DOUBLE,
    ("ce", "n"): _BOND_ORDER_DOUBLE,
    ("ce", "n2"): _BOND_ORDER_DOUBLE,
    ("cf", "n"): _BOND_ORDER_DOUBLE,
    ("cf", "n2"): _BOND_ORDER_DOUBLE,
    ("cu", "n2"): _BOND_ORDER_DOUBLE,
    ("cv", "n2"): _BOND_ORDER_DOUBLE,
    # --- C=N double bonds (c1/c2 with nc/nd/ne/nf: non-ring imine) ---
    ("c1", "nc"): _BOND_ORDER_DOUBLE,
    ("c1", "nd"): _BOND_ORDER_DOUBLE,
    ("c1", "ne"): _BOND_ORDER_DOUBLE,
    ("c1", "nf"): _BOND_ORDER_DOUBLE,
    ("c2", "nc"): _BOND_ORDER_DOUBLE,
    ("c2", "nd"): _BOND_ORDER_DOUBLE,
    ("c2", "ne"): _BOND_ORDER_DOUBLE,
    ("c2", "nf"): _BOND_ORDER_DOUBLE,
    # --- Guanidine C=N partial double bonds ---
    ("cz", "na"): _BOND_ORDER_DOUBLE,
    ("cz", "nh"): _BOND_ORDER_DOUBLE,
    ("cz", "ns"): _BOND_ORDER_DOUBLE,
    ("cz", "nu"): _BOND_ORDER_DOUBLE,
    ("cz", "nv"): _BOND_ORDER_DOUBLE,
    # --- N=N double bonds (non-aromatic) ---
    ("n1", "n2"): _BOND_ORDER_DOUBLE,
    ("n1", "ne"): _BOND_ORDER_DOUBLE,
    ("n1", "nf"): _BOND_ORDER_DOUBLE,
    ("n2", "n2"): _BOND_ORDER_DOUBLE,
    # --- N=S double bonds (Sp2 N with one-connected S) ---
    ("n1", "s"): _BOND_ORDER_DOUBLE,
    ("n2", "s"): _BOND_ORDER_DOUBLE,
    ("ne", "s"): _BOND_ORDER_DOUBLE,
    ("nf", "s"): _BOND_ORDER_DOUBLE,
    ("nc", "s"): _BOND_ORDER_DOUBLE,
    ("nd", "s"): _BOND_ORDER_DOUBLE,
    # --- Aromatic bonds (pure: ca/cp/cq/nb) ---
    ("ca", "ca"): _BOND_ORDER_AROMATIC,
    ("ca", "cp"): _BOND_ORDER_AROMATIC,
    ("ca", "cq"): _BOND_ORDER_AROMATIC,
    ("ca", "nb"): _BOND_ORDER_AROMATIC,
    ("cp", "cp"): _BOND_ORDER_AROMATIC,
    ("cp", "cq"): _BOND_ORDER_AROMATIC,
    ("cp", "nb"): _BOND_ORDER_AROMATIC,
    ("cq", "cq"): _BOND_ORDER_AROMATIC,
    ("cq", "nb"): _BOND_ORDER_AROMATIC,
    ("nb", "nb"): _BOND_ORDER_AROMATIC,
    # --- Aromatic bonds (non-pure: cc/cd cross aromatic) ---
    ("ca", "cc"): _BOND_ORDER_AROMATIC,
    ("ca", "cd"): _BOND_ORDER_AROMATIC,
    ("cc", "cc"): _BOND_ORDER_AROMATIC,
    ("cc", "cd"): _BOND_ORDER_AROMATIC,
    ("cc", "cp"): _BOND_ORDER_AROMATIC,
    ("cc", "cq"): _BOND_ORDER_AROMATIC,
    ("cc", "nb"): _BOND_ORDER_AROMATIC,
    ("cd", "cd"): _BOND_ORDER_AROMATIC,
    ("cd", "cp"): _BOND_ORDER_AROMATIC,
    ("cd", "cq"): _BOND_ORDER_AROMATIC,
    ("cd", "nb"): _BOND_ORDER_AROMATIC,
    ("nb", "nc"): _BOND_ORDER_AROMATIC,
    ("nb", "nd"): _BOND_ORDER_AROMATIC,
    # --- Aromatic bonds (conjugated: ce/cf with aromatic types) ---
    ("ca", "ce"): _BOND_ORDER_AROMATIC,
    ("ca", "cf"): _BOND_ORDER_AROMATIC,
    ("cc", "ce"): _BOND_ORDER_AROMATIC,
    ("cc", "cf"): _BOND_ORDER_AROMATIC,
    ("cd", "ce"): _BOND_ORDER_AROMATIC,
    ("cd", "cf"): _BOND_ORDER_AROMATIC,
    ("ce", "ce"): _BOND_ORDER_AROMATIC,
    ("ce", "cf"): _BOND_ORDER_AROMATIC,
    ("ce", "cp"): _BOND_ORDER_AROMATIC,
    ("ce", "cq"): _BOND_ORDER_AROMATIC,
    ("ce", "nb"): _BOND_ORDER_AROMATIC,
    ("cf", "cf"): _BOND_ORDER_AROMATIC,
    ("cf", "cp"): _BOND_ORDER_AROMATIC,
    ("cf", "cq"): _BOND_ORDER_AROMATIC,
    ("cf", "nb"): _BOND_ORDER_AROMATIC,
    # --- Aromatic bonds (conjugated N: ne/nf with aromatic types) ---
    ("ca", "ne"): _BOND_ORDER_AROMATIC,
    ("ca", "nf"): _BOND_ORDER_AROMATIC,
    ("cc", "ne"): _BOND_ORDER_AROMATIC,
    ("cc", "nf"): _BOND_ORDER_AROMATIC,
    ("cc", "nc"): _BOND_ORDER_AROMATIC,
    ("cc", "nd"): _BOND_ORDER_AROMATIC,
    ("cd", "ne"): _BOND_ORDER_AROMATIC,
    ("cd", "nf"): _BOND_ORDER_AROMATIC,
    ("cd", "nc"): _BOND_ORDER_AROMATIC,
    ("cd", "nd"): _BOND_ORDER_AROMATIC,
    ("ce", "ne"): _BOND_ORDER_AROMATIC,
    ("ce", "nf"): _BOND_ORDER_AROMATIC,
    ("ce", "nc"): _BOND_ORDER_AROMATIC,
    ("ce", "nd"): _BOND_ORDER_AROMATIC,
    ("cf", "ne"): _BOND_ORDER_AROMATIC,
    ("cf", "nf"): _BOND_ORDER_AROMATIC,
    ("cf", "nc"): _BOND_ORDER_AROMATIC,
    ("cf", "nd"): _BOND_ORDER_AROMATIC,
    ("cu", "ne"): _BOND_ORDER_AROMATIC,
    ("cu", "nf"): _BOND_ORDER_AROMATIC,
    ("cv", "ne"): _BOND_ORDER_AROMATIC,
    ("cv", "nf"): _BOND_ORDER_AROMATIC,
    ("ne", "ne"): _BOND_ORDER_AROMATIC,
    ("ne", "nf"): _BOND_ORDER_AROMATIC,
    ("nf", "nf"): _BOND_ORDER_AROMATIC,
    ("nc", "nc"): _BOND_ORDER_AROMATIC,
    ("nc", "nd"): _BOND_ORDER_AROMATIC,
    ("nd", "nd"): _BOND_ORDER_AROMATIC,
    ("nb", "ne"): _BOND_ORDER_AROMATIC,
    ("nb", "nf"): _BOND_ORDER_AROMATIC,
}

_REQ_DOUBLE_BOND_THRESHOLDS: Dict[Tuple[str, str], float] = {
    ("C", "O"): 1.28,
    ("O", "C"): 1.28,
    ("C", "N"): 1.32,
    ("N", "C"): 1.32,
    ("C", "C"): 1.38,
    ("N", "N"): 1.24,
    ("C", "S"): 1.62,
    ("S", "C"): 1.62,
    ("N", "S"): 1.60,
    ("S", "N"): 1.60,
}


def _infer_bond_order_from_atom_types(
    type_a: Optional[str],
    type_b: Optional[str],
) -> Optional[int]:
    if not type_a or not type_b:
        return None
    key = (type_a.strip().lower(), type_b.strip().lower())
    result = _AMBER_TYPE_PAIR_BOND_ORDER.get(key)
    if result is not None:
        return result
    rev = (key[1], key[0])
    return _AMBER_TYPE_PAIR_BOND_ORDER.get(rev)


def _infer_bond_order_from_req(
    elem_a: Optional[str],
    elem_b: Optional[str],
    req: Optional[float],
) -> Optional[int]:
    if req is None or not elem_a or not elem_b:
        return None
    threshold = _REQ_DOUBLE_BOND_THRESHOLDS.get((elem_a, elem_b))
    if threshold is not None and req < threshold:
        return _BOND_ORDER_DOUBLE
    return None


@dataclass(frozen=True)
class SystemLoadResult:
    """Result of loading a parm7/rst7 system.

    Attributes
    ----------
    view_mode
        Viewer mode ("3d" or "2d").
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
        Base64-encoded PDB text (3D mode only).
    depiction
        RDKit depiction payload (2D mode only).
    natoms
        Atom count.
    nresidues
        Residue count.
    warnings
        List of topology warnings.
    timings
        Timing breakdown for the load pipeline.
    """

    view_mode: str
    meta_list: List[AtomMeta]
    meta_by_serial: Dict[int, AtomMeta]
    residue_index: Dict[str, List[int]]
    residue_keys_by_resid: Dict[int, List[str]]
    parm7_text_b64: str
    parm7_sections: Dict[str, Parm7Section]
    pdb_b64: Optional[str]
    depiction: Optional[Dict[str, object]]
    natoms: int
    nresidues: int
    warnings: List[str]
    nmr_restraints: List[Dict[str, object]]
    nmr_summary: Dict[str, int]
    timings: Dict[str, float]


def _timed_call(fn: Callable[..., object], *args: object, **kwargs: object):
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


def _load_universe(parm7_path: str, rst7_path: str) -> mda.Universe:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Unknown ATOMIC_NUMBER value found for some atoms*",
            category=UserWarning,
            module=r"MDAnalysis\\.topology\\.TOPParser",
        )
        return mda.Universe(
            parm7_path,
            rst7_path,
            format="RESTRT",
            topology_format="PARM7",
        )


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


def _is_resname_all(resname: Optional[str]) -> bool:
    return (resname or "").strip().lower() == RESNAME_ALL


def _extract_bond_pairs(
    parm7_sections: Dict[str, Parm7Section],
) -> List[Tuple[int, int]]:
    bonds: List[Tuple[int, int]] = []
    for section_name in ("BONDS_INC_HYDROGEN", "BONDS_WITHOUT_HYDROGEN"):
        section = parm7_sections.get(section_name)
        if not section or not section.tokens:
            continue
        values = parse_int_tokens(section.tokens)
        for i in range(0, len(values) - 2, 3):
            sa = abs(values[i]) // 3 + 1
            sb = abs(values[i + 1]) // 3 + 1
            bonds.append((sa, sb))
    return bonds


def _compute_lj_tables(
    parm7_sections: Dict[str, Parm7Section],
    natom: int,
    ntypes: int,
) -> Tuple[List[int], Dict[int, Dict[str, float]], float]:
    lj_start = time.perf_counter()
    atom_type_indices: List[int] = []
    lj_by_type: Dict[int, Dict[str, float]] = {}
    atom_type_index_section = parm7_sections.get("ATOM_TYPE_INDEX")
    nonbond_index_section = parm7_sections.get("NONBONDED_PARM_INDEX")
    acoef_section = parm7_sections.get("LENNARD_JONES_ACOEF")
    bcoef_section = parm7_sections.get("LENNARD_JONES_BCOEF")
    if atom_type_index_section:
        atom_type_values = [token.value for token in atom_type_index_section.tokens]
        nonbond_values = (
            [token.value for token in nonbond_index_section.tokens]
            if nonbond_index_section
            else []
        )
        acoef_values = (
            [token.value for token in acoef_section.tokens] if acoef_section else []
        )
        bcoef_values = (
            [token.value for token in bcoef_section.tokens] if bcoef_section else []
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
            expected_nonbond = ntypes * ntypes
            expected_coef = ntypes * (ntypes + 1) // 2
            logger.error("Failed to parse LJ tables: %s", exc)
            logger.error(
                "LJ context: natom=%d ntypes=%d expected_nonbond=%d expected_coef=%d",
                natom,
                ntypes,
                expected_nonbond,
                expected_coef,
            )
            logger.error(
                "LJ section ATOM_TYPE_INDEX expected=%d actual=%d; %s",
                natom,
                len(atom_type_values),
                describe_section(atom_type_index_section),
            )
            logger.error(
                "LJ section NONBONDED_PARM_INDEX expected=%d actual=%d; %s",
                expected_nonbond,
                len(nonbond_values),
                describe_section(nonbond_index_section),
            )
            logger.error(
                "LJ section LENNARD_JONES_ACOEF expected=%d actual=%d; %s",
                expected_coef,
                len(acoef_values),
                describe_section(acoef_section),
            )
            logger.error(
                "LJ section LENNARD_JONES_BCOEF expected=%d actual=%d; %s",
                expected_coef,
                len(bcoef_values),
                describe_section(bcoef_section),
            )
            raise ModelError(
                "parm7_parse_failed", "Failed to parse LJ tables", str(exc)
            ) from exc
        atom_type_indices = result.get("atom_type_indices", [])
        lj_by_type = result.get("lj_by_type", {})
    lj_time = time.perf_counter() - lj_start
    return atom_type_indices, lj_by_type, lj_time


def _build_rdkit_depiction_from_atoms(
    atoms: list,
    bond_entries: list,
    resname: str,
    resid: int,
    width: int = 600,
    height: int = 400,
) -> Tuple[Dict[str, object], Dict[int, Tuple[float, float, float]], float]:
    try:
        from rdkit import Chem
        from rdkit.Chem import rdDepictor
        from rdkit.Chem.Draw import rdMolDraw2D
    except Exception as exc:
        raise ModelError(
            "missing_dependency",
            "RDKit is required for 2D depiction. Install rdkit.",
            str(exc),
        ) from exc

    start = time.perf_counter()
    if not atoms:
        raise ModelError("not_found", f"Residue {resname} has no atoms")

    periodic = Chem.GetPeriodicTable()
    rw_mol = Chem.RWMol()
    atom_idx_by_serial: Dict[int, int] = {}
    atom_serials: List[int] = []
    atom_names: List[str] = []

    atom_types_by_serial: Dict[int, str] = {}
    atom_elements_by_serial: Dict[int, str] = {}

    for atom in atoms:
        serial = int(getattr(atom, "idx", 0)) + 1
        name = str(getattr(atom, "name", "") or "").strip()
        atomic_number = getattr(atom, "atomic_number", None)
        element = getattr(atom, "element", None)
        element_symbol = str(element).strip() if element else _guess_element(name) or ""
        if not atomic_number and element_symbol:
            try:
                atomic_number = periodic.GetAtomicNumber(element_symbol)
            except Exception:
                atomic_number = 0
        rd_atom = Chem.Atom(int(atomic_number)) if atomic_number else Chem.Atom(0)
        rd_atom.SetNoImplicit(True)
        rd_atom.SetNumExplicitHs(0)
        rd_idx = rw_mol.AddAtom(rd_atom)
        atom_idx_by_serial[serial] = rd_idx
        atom_serials.append(serial)
        atom_names.append(name)
        amber_type = str(getattr(atom, "type", "") or "").strip().lower()
        if amber_type:
            atom_types_by_serial[serial] = amber_type
        if element_symbol:
            atom_elements_by_serial[serial] = element_symbol

    for bond in bond_entries:
        atom1 = getattr(bond, "atom1", None)
        atom2 = getattr(bond, "atom2", None)
        if atom1 is None or atom2 is None:
            continue
        serial_a = int(getattr(atom1, "idx", 0)) + 1
        serial_b = int(getattr(atom2, "idx", 0)) + 1
        idx_a = atom_idx_by_serial.get(serial_a)
        idx_b = atom_idx_by_serial.get(serial_b)
        if idx_a is None or idx_b is None:
            continue
        if rw_mol.GetBondBetweenAtoms(idx_a, idx_b) is not None:
            continue
        bond_type = Chem.rdchem.BondType.SINGLE
        order = getattr(bond, "order", None)
        order_val = None
        if order is not None:
            try:
                order_val = float(order)
            except (TypeError, ValueError):
                order_val = None
        if order_val is not None and order_val != 1.0:
            if order_val == 2:
                bond_type = Chem.rdchem.BondType.DOUBLE
            elif order_val == 3:
                bond_type = Chem.rdchem.BondType.TRIPLE
            elif abs(order_val - 1.5) < 0.1:
                bond_type = Chem.rdchem.BondType.AROMATIC
        else:
            inferred = _infer_bond_order_from_atom_types(
                atom_types_by_serial.get(serial_a),
                atom_types_by_serial.get(serial_b),
            )
            if inferred is None:
                req = None
                bond_ff_type = getattr(bond, "type", None)
                if bond_ff_type is not None:
                    req = getattr(bond_ff_type, "req", None)
                inferred = _infer_bond_order_from_req(
                    atom_elements_by_serial.get(serial_a),
                    atom_elements_by_serial.get(serial_b),
                    req,
                )
            if inferred == _BOND_ORDER_DOUBLE:
                bond_type = Chem.rdchem.BondType.DOUBLE
            elif inferred == _BOND_ORDER_TRIPLE:
                bond_type = Chem.rdchem.BondType.TRIPLE
            elif inferred == _BOND_ORDER_AROMATIC:
                bond_type = Chem.rdchem.BondType.AROMATIC
        rw_mol.AddBond(idx_a, idx_b, bond_type)

    mol = rw_mol.GetMol()
    mol.UpdatePropertyCache(False)
    try:
        rdDepictor.Compute2DCoords(mol)
    except Exception as exc:
        raise ModelError(
            "rdkit_failed", "Failed to compute 2D coordinates", str(exc)
        ) from exc

    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()

    atom_coords: List[Dict[str, float]] = []
    coords_by_serial: Dict[int, Tuple[float, float, float]] = {}
    for atom_idx, serial in enumerate(atom_serials):
        point = drawer.GetDrawCoords(atom_idx)
        coords = (float(point.x), float(point.y), 0.0)
        atom_coords.append({"x": coords[0], "y": coords[1]})
        coords_by_serial[serial] = coords

    bond_pairs = [
        {
            "a": bond.GetBeginAtomIdx(),
            "b": bond.GetEndAtomIdx(),
            "bond_index": bond.GetIdx(),
        }
        for bond in mol.GetBonds()
    ]

    depiction = {
        "svg": svg,
        "width": width,
        "height": height,
        "atom_serials": atom_serials,
        "atom_coords": atom_coords,
        "bond_pairs": bond_pairs,
        "atom_names": atom_names,
        "resname": resname,
        "resid": resid,
    }
    rdkit_time = time.perf_counter() - start
    return depiction, coords_by_serial, rdkit_time


def _build_rdkit_depiction(
    residue,
    resname: str,
    width: int = 600,
    height: int = 400,
) -> Tuple[Dict[str, object], Dict[int, Tuple[float, float, float]], float]:
    atoms = list(getattr(residue, "atoms", []) or [])
    if not atoms:
        raise ModelError("not_found", f"Residue {resname} has no atoms")

    resid = getattr(residue, "number", None)
    if resid is None:
        resid = getattr(residue, "idx", 0) + 1
    else:
        resid = int(resid)

    bond_entries: List[object] = []
    residue_bonds = getattr(residue, "bonds", None)
    if residue_bonds:
        bond_entries = list(residue_bonds)
    else:
        for atom in atoms:
            bond_entries.extend(getattr(atom, "bonds", []) or [])

    filtered_bonds: List[object] = []
    for bond in bond_entries:
        atom1 = getattr(bond, "atom1", None)
        atom2 = getattr(bond, "atom2", None)
        if atom1 is None or atom2 is None:
            continue
        if (
            getattr(atom1, "residue", None) is not residue
            or getattr(atom2, "residue", None) is not residue
        ):
            continue
        filtered_bonds.append(bond)

    return _build_rdkit_depiction_from_atoms(
        atoms, filtered_bonds, resname, resid, width, height,
    )


def _parmed_import_error_message(exc: Exception) -> str:
    detail = str(exc)
    if "numpy.compat" in detail:
        return (
            "ParmEd failed to import due to NumPy compatibility. "
            "Try pinning numpy<2 or upgrading ParmEd."
        )
    return "ParmEd failed to import. Check dependency versions."


def load_system_data_3d(
    parm7_path: str,
    rst7_path: str,
    nmr_path: Optional[str] = None,
    cpu_submit: Optional[Callable[..., object]] = None,
) -> SystemLoadResult:
    """Load a parm7/rst7 pair into in-memory metadata.

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
            _timed_call,
            _load_universe,
            parm7_path,
            rst7_path,
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
        raise ModelError(
            "parm7_parse_failed", "Failed to parse POINTERS", str(exc)
        ) from exc

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

    warning_messages: List[str] = []
    warnings: List[str] = []
    if charges is None:
        warning_messages.append("Atom charges not available in topology")
    if masses is None:
        warning_messages.append("Atom masses not available in topology")
    if types is None:
        warning_messages.append("Atom types not available in topology")
    if warning_messages:
        logger.debug("Topology warnings: %s", warning_messages)
        warnings.extend(warning_messages)
    atom_type_indices, lj_by_type, lj_time = _compute_lj_tables(
        parm7_sections, natom, ntypes
    )
    try:
        nmr_records = parse_nmr_restraints(nmr_path, natom=natom) if nmr_path else []
    except ValueError as exc:
        raise ModelError(
            "nmr_parse_failed", "Failed to parse NMR restraints", str(exc)
        ) from exc
    nmr_restraints = [record.to_dict() for record in nmr_records]
    nmr_summary = summarize_nmr_restraints(nmr_records)

    meta_list: List[AtomMeta] = []
    meta_by_serial: Dict[int, AtomMeta] = {}
    residue_keys_by_resid: Dict[int, List[str]] = {}
    residue_index_map: Dict[str, List[int]] = {}

    atoms = universe.atoms
    natoms = len(atoms)

    attrs_start = time.perf_counter()
    names = _safe_attr(atoms, "names") or [atom.name for atom in atoms]
    resids = _safe_attr(atoms, "resids") or [atom.residue.resid for atom in atoms]
    resnames = _safe_attr(atoms, "resnames") or [atom.residue.resname for atom in atoms]
    resindices = _safe_attr(atoms, "resindices") or [atom.residue.ix for atom in atoms]
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
    bond_pairs = _extract_bond_pairs(parm7_sections)
    pdb_start = time.perf_counter()
    pdb_text = write_pdb(meta_list, bonds=bond_pairs)
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
        view_mode="3d",
        meta_list=meta_list,
        meta_by_serial=meta_by_serial,
        residue_index=residue_index_map,
        residue_keys_by_resid=residue_keys_by_resid,
        parm7_text_b64=parm7_text_b64,
        parm7_sections=parm7_sections,
        pdb_b64=pdb_b64,
        depiction=None,
        natoms=len(meta_list),
        nresidues=len(universe.residues),
        warnings=warnings,
        nmr_restraints=nmr_restraints,
        nmr_summary=nmr_summary,
        timings=timings,
    )


def load_system_data_2d(
    parm7_path: str,
    resname: Optional[str] = None,
    nmr_path: Optional[str] = None,
) -> SystemLoadResult:
    """Load a parm7-only system and build a 2D RDKit depiction."""

    if not parm7_path:
        raise ModelError("invalid_input", "parm7 path is required")
    if nmr_path:
        raise ModelError(
            "invalid_input",
            "NMR restraints require a 3D load with both parm7 and rst7 paths",
        )
    if not os.path.exists(parm7_path):
        raise ModelError("file_not_found", "parm7 file not found", parm7_path)

    total_start = time.perf_counter()
    parse_start = time.perf_counter()
    try:
        parm7_text, parm7_sections = parse_parm7(parm7_path)
    except Exception as exc:
        logger.exception("Failed to parse parm7 file")
        raise ModelError(
            "parm7_parse_failed", "Failed to parse parm7 file", str(exc)
        ) from exc
    parm7_time = time.perf_counter() - parse_start
    parm7_text_b64 = base64.b64encode(parm7_text.encode("utf-8")).decode("ascii")

    pointer_section = parm7_sections.get("POINTERS")
    if not pointer_section or not pointer_section.tokens:
        raise ModelError("parm7_parse_failed", "POINTERS section missing")
    try:
        pointers = parse_pointers(pointer_section)
    except ValueError as exc:
        raise ModelError(
            "parm7_parse_failed", "Failed to parse POINTERS", str(exc)
        ) from exc

    natom = int(pointers.get("NATOM", 0))
    ntypes = int(pointers.get("NTYPES", 0))
    if natom <= 0 or ntypes <= 0:
        raise ModelError(
            "parm7_parse_failed",
            "Invalid POINTERS values for NATOM/NTYPES",
            {"NATOM": natom, "NTYPES": ntypes},
        )

    atom_type_indices, lj_by_type, lj_time = _compute_lj_tables(
        parm7_sections, natom, ntypes
    )

    try:
        from parmed.amber import AmberParm
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("parmed"):
            raise ModelError(
                "missing_dependency",
                "ParmEd is required for parm7-only loads.",
                str(exc),
            ) from exc
        raise ModelError(
            "dependency_error",
            _parmed_import_error_message(exc),
            str(exc),
        ) from exc
    except Exception as exc:
        raise ModelError(
            "dependency_error",
            _parmed_import_error_message(exc),
            str(exc),
        ) from exc
    try:
        parm = AmberParm(parm7_path)
    except Exception as exc:
        logger.exception("Failed to parse parm7 topology")
        raise ModelError(
            "load_failed", "Failed to load parm7 topology", str(exc)
        ) from exc

    atoms = list(parm.atoms)
    residues = list(parm.residues)
    if len(atoms) != natom:
        logger.debug(
            "Atom count mismatch: POINTERS NATOM=%d parmed=%d", natom, len(atoms)
        )

    warning_messages: List[str] = []
    warnings: List[str] = []
    charge_section = parm7_sections.get("CHARGE")
    charge_tokens = charge_section.tokens if charge_section else None

    charge_missing = any(atom.charge is None for atom in atoms)
    mass_missing = any(atom.mass is None for atom in atoms)
    type_missing = any(atom.type is None for atom in atoms)
    if charge_missing:
        warning_messages.append("Atom charges not available in topology")
    if mass_missing:
        warning_messages.append("Atom masses not available in topology")
    if type_missing:
        warning_messages.append("Atom types not available in topology")
    if warning_messages:
        logger.debug("Topology warnings: %s", warning_messages)
        warnings.extend(warning_messages)

    if _is_resname_all(resname):
        all_bonds = list(parm.bonds) if hasattr(parm, "bonds") else []
        depiction, coords_by_serial, rdkit_time = _build_rdkit_depiction_from_atoms(
            atoms, all_bonds, RESNAME_ALL.upper(), 0,
        )
    else:
        normalized_resname = (resname or DEFAULT_RESNAME).strip() or DEFAULT_RESNAME
        target_residue = None
        if residues:
            target_residue = next(
                (res for res in residues if res.name == normalized_resname), None
            )
        if target_residue is None and residues:
            lowered = normalized_resname.lower()
            target_residue = next(
                (res for res in residues if (res.name or "").lower() == lowered), None
            )
        if target_residue is None:
            raise ModelError(
                "not_found",
                f"Residue {normalized_resname} not found in topology",
            )
        if len([res for res in residues if res.name == target_residue.name]) > 1:
            warnings.append(
                f"Multiple residues named {target_residue.name}; using the first match"
            )

        depiction, coords_by_serial, rdkit_time = _build_rdkit_depiction(
            target_residue,
            target_residue.name or normalized_resname,
        )

    meta_list: List[AtomMeta] = []
    meta_by_serial: Dict[int, AtomMeta] = {}
    residue_keys_by_resid: Dict[int, List[str]] = {}
    residue_index_map: Dict[str, List[int]] = {}

    attrs_start = time.perf_counter()
    names_list = [atom.name for atom in atoms]
    resids_list = [
        int(atom.residue.number)
        if atom.residue.number is not None
        else atom.residue.idx + 1
        for atom in atoms
    ]
    resnames_list = [atom.residue.name for atom in atoms]
    resindices_list = [atom.residue.idx for atom in atoms]
    charges_list = [atom.charge for atom in atoms]
    masses_list = [atom.mass for atom in atoms]
    types_list = [atom.type for atom in atoms]
    elements_list = [getattr(atom, "element", None) for atom in atoms]
    meta_attrs_time = time.perf_counter() - attrs_start

    build_start = time.perf_counter()
    guess_element = _guess_element
    element_cache: Dict[str, Optional[str]] = {}
    cache_missing = object()
    atom_type_indices_local = atom_type_indices
    lj_by_type_local = lj_by_type
    ResidueMetaCls = ResidueMeta
    AtomMetaCls = AtomMeta
    meta_list_append = meta_list.append
    meta_by_serial_set = meta_by_serial.__setitem__
    residue_index_map_setdefault = residue_index_map.setdefault
    residue_keys_by_resid_setdefault = residue_keys_by_resid.setdefault

    for idx, atom in enumerate(atoms):
        serial = idx + 1
        resid = int(resids_list[idx])
        resname_val = str(resnames_list[idx]).strip()
        residue_serial_index = int(resindices_list[idx]) + 1
        segid = None
        residue_meta = ResidueMetaCls(
            resid=resid, resname=resname_val, segid=segid, chain=None
        )

        name_str = str(names_list[idx]).strip()
        element = elements_list[idx]
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

        coords = coords_by_serial.get(serial, (0.0, 0.0, 0.0))
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

        residue_key = f"{segid or ''}:{resid}:{resname_val}"
        residue_index_map_setdefault(residue_key, []).append(serial)
        residue_keys_by_resid_setdefault(resid, []).append(residue_key)

    meta_build_time = time.perf_counter() - build_start
    total_time = time.perf_counter() - total_start
    logger.debug(
        "System loaded (2D): atoms=%d residues=%d", len(meta_list), len(residues)
    )

    timings = {
        "parm7": parm7_time,
        "lj": lj_time,
        "meta_attrs": meta_attrs_time,
        "meta_build": meta_build_time,
        "rdkit": rdkit_time,
        "total": total_time,
    }

    return SystemLoadResult(
        view_mode="2d",
        meta_list=meta_list,
        meta_by_serial=meta_by_serial,
        residue_index=residue_index_map,
        residue_keys_by_resid=residue_keys_by_resid,
        parm7_text_b64=parm7_text_b64,
        parm7_sections=parm7_sections,
        pdb_b64=None,
        depiction=depiction,
        natoms=len(meta_list),
        nresidues=len(residues),
        warnings=warnings,
        nmr_restraints=[],
        nmr_summary=summarize_nmr_restraints([]),
        timings=timings,
    )


def load_system_data(
    parm7_path: str,
    rst7_path: Optional[str] = None,
    resname: Optional[str] = None,
    nmr_path: Optional[str] = None,
    cpu_submit: Optional[Callable[..., object]] = None,
) -> SystemLoadResult:
    """Load topology and optional coordinates into in-memory metadata.

    Parameters
    ----------
    parm7_path
        Path to the parm7/prmtop file.
    rst7_path
        Optional path to the rst7/inpcrd file.
    resname
        Residue name for parm7-only 2D depictions.
    cpu_submit
        Optional executor submission function for CPU-heavy work.
    """

    if rst7_path:
        return load_system_data_3d(
            parm7_path,
            rst7_path,
            nmr_path=nmr_path,
            cpu_submit=cpu_submit,
        )
    return load_system_data_2d(
        parm7_path,
        resname=resname,
        nmr_path=nmr_path,
    )
