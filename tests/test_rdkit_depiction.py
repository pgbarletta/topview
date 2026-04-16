from __future__ import annotations

from pathlib import Path
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from topview.model import Model
from topview.services.loader import (
    _build_rdkit_depiction,
    _infer_bond_order_from_atom_types,
    _infer_bond_order_from_req,
    load_system_data,
)
from topview.services.parm7 import parse_parm7


def _first_resname(parm7_path: Path) -> str | None:
    _, sections = parse_parm7(str(parm7_path))
    section = sections.get("RESIDUE_LABEL")
    if not section or not section.tokens:
        return None
    for token in section.tokens:
        name = token.value.strip()
        if name:
            return name
    return None


def _submit_immediately(fn, *args, **kwargs):
    future: Future = Future()
    try:
        future.set_result(fn(*args, **kwargs))
    except Exception as exc:  # pragma: no cover - exercised through future.result()
        future.set_exception(exc)
    return future


def test_parm7_only_loads_2d_depiction() -> None:
    pytest.importorskip("rdkit")
    parm7_path = Path(__file__).resolve().parents[1] / "tests" / "data" / "wcn.parm7"
    assert parm7_path.exists()
    resname = _first_resname(parm7_path)
    if not resname:
        pytest.skip("No residue labels available in sample parm7")
    result = load_system_data(str(parm7_path), rst7_path=None, resname=resname)
    assert result.view_mode == "2d"
    assert result.depiction
    assert result.depiction.get("svg")
    assert result.depiction.get("atom_serials")


def test_parm7_only_loads_system_info_with_cpu_submit() -> None:
    parm7_path = Path(__file__).resolve().parents[1] / "tests" / "data" / "wcn.parm7"
    assert parm7_path.exists()
    resname = _first_resname(parm7_path)
    if not resname:
        pytest.skip("No residue labels available in sample parm7")

    model = Model(cpu_submit=_submit_immediately)
    result = model.load_system(str(parm7_path), None, resname=resname)
    assert result["ok"]

    info = model.get_system_info()
    assert info["ok"]
    assert info["tables"]["atom_types"]["rows"]


def test_rdkit_depiction_does_not_invent_implicit_hydrogens() -> None:
    pytest.importorskip("rdkit")

    residue = SimpleNamespace(number=1, idx=0, name="LIG")
    atom_c = SimpleNamespace(
        idx=0,
        name="C1",
        atomic_number=6,
        element="C",
        residue=residue,
    )
    atom_o = SimpleNamespace(
        idx=1,
        name="O1",
        atomic_number=8,
        element="O",
        residue=residue,
    )
    bond = SimpleNamespace(atom1=atom_c, atom2=atom_o, order=1)
    residue.atoms = [atom_c, atom_o]
    residue.bonds = [bond]

    depiction, _, _ = _build_rdkit_depiction(residue, "LIG")
    svg = depiction["svg"]
    assert "OH" not in svg
    assert "HO" not in svg


def test_bond_order_inference_from_amber_types() -> None:
    assert _infer_bond_order_from_atom_types("ce", "o") == 2
    assert _infer_bond_order_from_atom_types("o", "ce") == 2
    assert _infer_bond_order_from_atom_types("ca", "ca") == 4
    assert _infer_bond_order_from_atom_types("ca", "cp") == 4
    assert _infer_bond_order_from_atom_types("cd", "nc") == 2
    assert _infer_bond_order_from_atom_types("c3", "os") == 1
    assert _infer_bond_order_from_atom_types("unk", "unk2") is None
    assert _infer_bond_order_from_atom_types(None, "o") is None
    assert _infer_bond_order_from_atom_types("", "o") is None


def test_bond_order_inference_from_req() -> None:
    assert _infer_bond_order_from_req("C", "O", 1.20) == 2
    assert _infer_bond_order_from_req("O", "C", 1.20) == 2
    assert _infer_bond_order_from_req("C", "N", 1.30) == 2
    assert _infer_bond_order_from_req("C", "O", 1.30) is None
    assert _infer_bond_order_from_req("C", "O", None) is None
    assert _infer_bond_order_from_req(None, "O", 1.20) is None


def test_double_bond_drawn_from_amber_types() -> None:
    pytest.importorskip("rdkit")
    from rdkit import Chem

    residue = SimpleNamespace(number=1, idx=0, name="LIG")
    atom_c = SimpleNamespace(
        idx=0,
        name="C1",
        atomic_number=6,
        element="C",
        type="ce",
        residue=residue,
    )
    atom_o = SimpleNamespace(
        idx=1,
        name="O1",
        atomic_number=8,
        element="O",
        type="o",
        residue=residue,
    )
    bond = SimpleNamespace(atom1=atom_c, atom2=atom_o, order=1)
    residue.atoms = [atom_c, atom_o]
    residue.bonds = [bond]

    depiction, _, _ = _build_rdkit_depiction(residue, "LIG")
    assert len(depiction["bond_pairs"]) == 1
    svg = depiction["svg"]
    assert "OH" not in svg
    assert "HO" not in svg


def test_aromatic_bond_drawn_from_amber_types() -> None:
    pytest.importorskip("rdkit")

    residue = SimpleNamespace(number=1, idx=0, name="LIG")
    atom_c1 = SimpleNamespace(
        idx=0,
        name="C1",
        atomic_number=6,
        element="C",
        type="ca",
        residue=residue,
    )
    atom_c2 = SimpleNamespace(
        idx=1,
        name="C2",
        atomic_number=6,
        element="C",
        type="ca",
        residue=residue,
    )
    bond = SimpleNamespace(atom1=atom_c1, atom2=atom_c2, order=1)
    residue.atoms = [atom_c1, atom_c2]
    residue.bonds = [bond]

    depiction, _, _ = _build_rdkit_depiction(residue, "LIG")
    assert len(depiction["bond_pairs"]) == 1


def test_double_bond_fallback_to_req() -> None:
    pytest.importorskip("rdkit")

    class FakeBondType:
        req = 1.20
        k = 600.0

    residue = SimpleNamespace(number=1, idx=0, name="LIG")
    atom_c = SimpleNamespace(
        idx=0,
        name="C1",
        atomic_number=6,
        element="C",
        type="unk",
        residue=residue,
    )
    atom_o = SimpleNamespace(
        idx=1,
        name="O1",
        atomic_number=8,
        element="O",
        type="unk2",
        residue=residue,
    )
    bond = SimpleNamespace(
        atom1=atom_c,
        atom2=atom_o,
        order=1,
        type=FakeBondType(),
    )
    residue.atoms = [atom_c, atom_o]
    residue.bonds = [bond]

    depiction, _, _ = _build_rdkit_depiction(residue, "LIG")
    svg = depiction["svg"]
    assert "OH" not in svg
