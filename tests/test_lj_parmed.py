from pathlib import Path

import pytest
from parmed.amber import AmberParm

from topview.services.lj import compute_lj_tables
from topview.services.parm7 import parse_parm7, parse_pointers


def _compute_topview_lj(parm7_path: Path) -> tuple[dict[int, dict[str, float]], int]:
    text, sections = parse_parm7(str(parm7_path))
    assert text
    pointer_section = sections.get("POINTERS")
    assert pointer_section is not None
    pointers = parse_pointers(pointer_section)
    natom = pointers["NATOM"]
    ntypes = pointers["NTYPES"]

    def token_values(name: str) -> list[str]:
        section = sections.get(name)
        assert section is not None
        assert section.tokens
        return [token.value for token in section.tokens]

    result = compute_lj_tables(
        token_values("ATOM_TYPE_INDEX"),
        token_values("NONBONDED_PARM_INDEX"),
        token_values("LENNARD_JONES_ACOEF"),
        token_values("LENNARD_JONES_BCOEF"),
        natom=natom,
        ntypes=ntypes,
    )
    return result["lj_by_type"], ntypes


def test_lj_matches_parmed() -> None:
    parm7_path = Path(__file__).resolve().parents[1] / "daux" / "binder_IDC-5270.parm7"
    assert parm7_path.exists()
    parmed_parm = AmberParm(str(parm7_path))
    lj_by_type, ntypes = _compute_topview_lj(parm7_path)

    assert len(parmed_parm.LJ_radius) == ntypes
    assert len(parmed_parm.LJ_depth) == ntypes

    for type_index in range(1, ntypes + 1):
        ours = lj_by_type.get(type_index)
        assert ours is not None
        assert ours["rmin"] == pytest.approx(
            parmed_parm.LJ_radius[type_index - 1], rel=1e-6, abs=1e-8
        )
        assert ours["epsilon"] == pytest.approx(
            parmed_parm.LJ_depth[type_index - 1], rel=1e-6, abs=1e-8
        )
