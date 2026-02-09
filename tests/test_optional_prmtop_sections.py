from pathlib import Path

import pytest

from topview.model.state import Parm7Section
from topview.services.parm7 import OPTIONAL_PRMTOP_SECTIONS, parse_parm7
from topview.services.system_info import build_system_info_tables


def _load_fixture_sections() -> dict[str, Parm7Section]:
    root = Path(__file__).resolve().parents[1]
    parm7_path = root / "tests" / "data" / "wcn.parm7"
    assert parm7_path.exists()
    _, sections = parse_parm7(str(parm7_path))
    assert sections
    return dict(sections)


def test_system_info_build_succeeds_without_scee_and_scnb() -> None:
    sections = _load_fixture_sections()
    sections.pop("SCEE_SCALE_FACTOR", None)
    sections.pop("SCNB_SCALE_FACTOR", None)

    tables = build_system_info_tables(sections)

    dihedral = tables["dihedral_types"]
    assert dihedral["rows"]
    scee_idx = dihedral["columns"].index("scee")
    scnb_idx = dihedral["columns"].index("scnb")
    assert all(row[scee_idx] is None for row in dihedral["rows"])
    assert all(row[scnb_idx] is None for row in dihedral["rows"])

    for table_name in ("improper_types", "one_four_nonbonded"):
        table = tables[table_name]
        if not table["rows"]:
            continue
        scee_idx = table["columns"].index("scee")
        scnb_idx = table["columns"].index("scnb")
        assert all(row[scee_idx] is None for row in table["rows"])
        assert all(row[scnb_idx] is None for row in table["rows"])


def test_system_info_build_succeeds_without_unconsumed_optional_sections() -> None:
    sections = _load_fixture_sections()
    for name in OPTIONAL_PRMTOP_SECTIONS - {"SCEE_SCALE_FACTOR", "SCNB_SCALE_FACTOR"}:
        sections.pop(name, None)

    tables = build_system_info_tables(sections)
    assert tables["atom_types"]["rows"]
    assert "nonbonded_pairs" in tables
    assert "dihedral_types" in tables


def test_malformed_optional_section_still_errors_when_present() -> None:
    sections = _load_fixture_sections()
    section = sections["SCEE_SCALE_FACTOR"]
    assert section.tokens
    sections["SCEE_SCALE_FACTOR"] = Parm7Section(
        name=section.name,
        count=section.count,
        width=section.width,
        flag_line=section.flag_line,
        end_line=section.end_line,
        tokens=section.tokens[:-1],
    )

    with pytest.raises(ValueError, match="SCEE_SCALE_FACTOR"):
        build_system_info_tables(sections)
