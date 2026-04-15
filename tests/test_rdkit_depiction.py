from __future__ import annotations

from pathlib import Path
from concurrent.futures import Future

import pytest

from topview.model import Model
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
