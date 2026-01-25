from __future__ import annotations

from pathlib import Path

import pytest

from topview.services.loader import load_system_data
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


def test_parm7_only_loads_2d_depiction() -> None:
    pytest.importorskip("rdkit")
    parm7_path = Path(__file__).resolve().parents[1] / "daux" / "binder_IDC-5270.parm7"
    assert parm7_path.exists()
    resname = _first_resname(parm7_path)
    if not resname:
        pytest.skip("No residue labels available in sample parm7")
    result = load_system_data(str(parm7_path), rst7_path=None, resname=resname)
    assert result.view_mode == "2d"
    assert result.depiction
    assert result.depiction.get("svg")
    assert result.depiction.get("atom_serials")
