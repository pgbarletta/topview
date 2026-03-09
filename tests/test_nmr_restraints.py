from pathlib import Path

import pytest

from topview.services.nmr_restraints import parse_nmr_restraints, summarize_nmr_restraints


EXAMPLE_RESTRAINTS = """&rst iat=839, 16
 r1=0.00000, r2=4.44080, r3=4.44080, r4=999.000, rk2=7.86, rk3=7.86 /
&rst iat=1996, 839, 16
 r1=-180.00000, r2=38.10545, r3=38.10545, r4=180.000, rk2=146.27, rk3=146.27 /
&rst iat=839, 16, 19
 r1=-180.00000, r2=89.75174, r3=89.75174, r4=180.000, rk2=62.58, rk3=62.58 /
&rst iat=2414, 1996, 839, 16
 r1=-180.00000, r2=-70.31557, r3=-70.31557, r4=180.000, rk2=199.27, rk3=199.27 /
&rst iat=1996, 839, 16, 19
 r1=-180.00000, r2=75.27049, r3=75.27049, r4=180.000, rk2=110.38, rk3=110.38 /
&rst iat=839, 16, 19, 23
 r1=-180.00000, r2=-53.92422, r3=-53.92422, r4=180.000, rk2=102.39, rk3=102.39 /
"""


def test_parse_nmr_restraints_example(tmp_path: Path) -> None:
    path = tmp_path / "rest.in"
    path.write_text(EXAMPLE_RESTRAINTS, encoding="utf-8")

    restraints = parse_nmr_restraints(str(path), natom=2414)
    summary = summarize_nmr_restraints(restraints)

    assert [restraint.kind for restraint in restraints] == [
        "distance",
        "angle",
        "angle",
        "dihedral",
        "dihedral",
        "dihedral",
    ]
    assert restraints[0].serials == [839, 16]
    assert restraints[0].r2 == pytest.approx(4.44080)
    assert restraints[0].equilibrium_value == pytest.approx(4.44080)
    assert restraints[3].serials == [2414, 1996, 839, 16]
    assert restraints[3].rk3 == pytest.approx(199.27)
    assert summary == {"distance": 1, "angle": 2, "dihedral": 3, "total": 6}


def test_parse_nmr_restraints_discards_trailing_zero_before_classification(
    tmp_path: Path,
) -> None:
    path = tmp_path / "zero_tail_rest.in"
    path.write_text(
        """&rst iat=10, 20, 0
 r1=0.0, r2=3.5, r3=3.5, r4=999.0, rk2=5.0, rk3=5.0 /
&rst iat=10, 20, 30, 0
 r1=-180.0, r2=89.0, r3=89.0, r4=180.0, rk2=5.0, rk3=5.0 /
&rst iat=10, 20, 30, 40, 0
 r1=-180.0, r2=119.0, r3=119.0, r4=180.0, rk2=5.0, rk3=5.0 /
""",
        encoding="utf-8",
    )

    restraints = parse_nmr_restraints(str(path), natom=40)
    summary = summarize_nmr_restraints(restraints)

    assert [restraint.kind for restraint in restraints] == ["distance", "angle", "dihedral"]
    assert restraints[0].serials == [10, 20]
    assert restraints[1].serials == [10, 20, 30]
    assert restraints[2].serials == [10, 20, 30, 40]
    assert summary == {"distance": 1, "angle": 1, "dihedral": 1, "total": 3}


def test_parse_nmr_restraints_rejects_non_trailing_zero(tmp_path: Path) -> None:
    path = tmp_path / "bad_zero_rest.in"
    path.write_text(
        "&rst iat=10, 0, 20\n r1=0.0, r2=2.0, r3=2.0, r4=999.0, rk2=5.0, rk3=5.0 /\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported group or zero-based restraint atom index 0"):
        parse_nmr_restraints(str(path), natom=20)


def test_nmr_restraint_to_dict_includes_equilibrium_value(tmp_path: Path) -> None:
    path = tmp_path / "equilibrium_rest.in"
    path.write_text(
        "&rst iat=1, 2\n r1=0.0, r2=4.4408, r3=4.4408, r4=999.0, rk2=7.86, rk3=7.86 /\n",
        encoding="utf-8",
    )

    restraint = parse_nmr_restraints(str(path), natom=2)[0]

    assert restraint.to_dict()["equilibrium_value"] == pytest.approx(4.4408)


def test_parse_nmr_restraints_rejects_out_of_range_indices(tmp_path: Path) -> None:
    path = tmp_path / "bad_rest.in"
    path.write_text(
        "&rst iat=1, 999\n r1=0.0, r2=2.0, r3=2.0, r4=999.0, rk2=5.0, rk3=5.0 /\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exceeds topology atom count"):
        parse_nmr_restraints(str(path), natom=10)


def test_parse_nmr_restraints_rejects_non_restraint_file(tmp_path: Path) -> None:
    path = tmp_path / "frame.rst7"
    path.write_text("default restart contents\n1.0 2.0 3.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No Amber '&rst' restraint blocks found"):
        parse_nmr_restraints(str(path), natom=10)
