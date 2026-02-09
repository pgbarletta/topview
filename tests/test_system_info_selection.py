from pathlib import Path

from topview.model import Model
from topview.model.state import Parm7Section, Parm7Token
from topview.services.parm7 import OPTIONAL_PRMTOP_SECTIONS, POINTER_NAMES
from topview.services.system_info_selection import (
    build_system_info_selection_index,
    nonbonded_pair_for_cursor,
    nonbonded_pair_total,
)


def _make_section(name: str, values: list[int]) -> Parm7Section:
    tokens = [
        Parm7Token(value=str(value), line=0, start=0, end=len(str(value)))
        for value in values
    ]
    return Parm7Section(
        name=name,
        count=0,
        width=0,
        flag_line=0,
        end_line=0,
        tokens=tokens,
    )


def _make_pointer_section(overrides: dict[str, int]) -> Parm7Section:
    values = [0] * len(POINTER_NAMES)
    for idx, name in enumerate(POINTER_NAMES):
        values[idx] = overrides.get(name, 0)
    return _make_section("POINTERS", values)


def test_selection_index_basic_mapping() -> None:
    sections = {
        "POINTERS": _make_pointer_section(
            {
                "NATOM": 4,
                "NTYPES": 2,
                "NBONH": 1,
                "MBONA": 0,
                "NTHETH": 1,
                "MTHETA": 0,
                "NPHIH": 1,
                "MPHIA": 0,
            }
        ),
        "ATOM_TYPE_INDEX": _make_section("ATOM_TYPE_INDEX", [1, 2, 1, 2]),
        "BONDS_INC_HYDROGEN": _make_section("BONDS_INC_HYDROGEN", [0, 3, 1]),
        "ANGLES_INC_HYDROGEN": _make_section(
            "ANGLES_INC_HYDROGEN", [0, 3, 6, 1]
        ),
        "DIHEDRALS_INC_HYDROGEN": _make_section(
            "DIHEDRALS_INC_HYDROGEN", [0, 3, 6, 9, 1]
        ),
    }
    index = build_system_info_selection_index(sections)

    assert index.atom_serials_by_type[1] == [1, 3]
    assert index.atom_serials_by_type[2] == [2, 4]

    assert index.bonds_by_key[(1, 2, 1)] == [(1, 2)]
    assert index.angles_by_key[(1, 2, 1, 1)] == [(1, 2, 3)]
    assert index.dihedrals_by_idx[1] == (1, 2, 3, 4)
    assert index.one_four_by_key[(1, 2, 1)] == [(1, 4)]


def test_nonbonded_pair_indexing_cross_type() -> None:
    serials_a = [1, 3]
    serials_b = [2, 4, 5]
    assert nonbonded_pair_total(serials_a, serials_b, False) == 6
    assert nonbonded_pair_for_cursor(serials_a, serials_b, 0, False) == (1, 2)
    assert nonbonded_pair_for_cursor(serials_a, serials_b, 1, False) == (1, 4)
    assert nonbonded_pair_for_cursor(serials_a, serials_b, 2, False) == (1, 5)
    assert nonbonded_pair_for_cursor(serials_a, serials_b, 3, False) == (3, 2)


def test_nonbonded_pair_indexing_same_type() -> None:
    serials = [1, 3, 5, 7]
    assert nonbonded_pair_total(serials, serials, True) == 6
    assert nonbonded_pair_for_cursor(serials, serials, 0, True) == (1, 3)
    assert nonbonded_pair_for_cursor(serials, serials, 1, True) == (1, 5)
    assert nonbonded_pair_for_cursor(serials, serials, 2, True) == (1, 7)
    assert nonbonded_pair_for_cursor(serials, serials, 3, True) == (3, 5)


def test_system_info_selection_integration() -> None:
    root = Path(__file__).resolve().parents[1]
    parm7_path = root / "tests" / "data" / "wcn.parm7"
    rst7_path = root / "tests" / "data" / "wcnref.rst7"
    assert parm7_path.exists()
    assert rst7_path.exists()

    model = Model()
    result = model.load_system(str(parm7_path), str(rst7_path))
    assert result["ok"]

    info = model.get_system_info()
    table = info["tables"]["atom_types"]
    columns = table["columns"]
    rows = table["rows"]
    assert rows
    count_idx = columns.index("atom_count")
    row_index = None
    type_index = None
    for idx, row in enumerate(rows):
        count = row[count_idx]
        if count and int(count) > 0:
            row_index = idx
            type_index = int(row[type_index_idx])
            break
    assert row_index is not None
    selection = model.get_system_info_selection("atom_types", row_index, 0)
    assert selection["ok"]
    serial = selection["serials"][0]
    atom_info = model.get_atom_info(serial)
    assert atom_info["ok"]
    assert atom_info["atom"]["parm7"]["atom_type_index"] == type_index


def test_system_info_selection_integration_without_optional_sections() -> None:
    root = Path(__file__).resolve().parents[1]
    parm7_path = root / "tests" / "data" / "wcn.parm7"
    rst7_path = root / "tests" / "data" / "wcnref.rst7"
    assert parm7_path.exists()
    assert rst7_path.exists()

    model = Model()
    result = model.load_system(str(parm7_path), str(rst7_path))
    assert result["ok"]

    with model._lock:
        sections = dict(model._state.parm7_sections)
        for name in OPTIONAL_PRMTOP_SECTIONS:
            sections.pop(name, None)
        model._state.parm7_sections = sections
        model._state.system_info = None
        model._state.system_info_future = None
        model._state.system_info_selection_index = None
        model._state.system_info_selection_future = None
        natom = len(model._state.meta_list)

    info = model.get_system_info()
    assert info["ok"]

    table = info["tables"]["atom_types"]
    columns = table["columns"]
    rows = table["rows"]
    assert rows
    type_index_idx = columns.index("type_index")
    count_idx = columns.index("atom_count")
    row_index = None
    for idx, row in enumerate(rows):
        count = row[count_idx]
        if count and int(count) > 0:
            row_index = idx
            break
    assert row_index is not None

    selection = model.get_system_info_selection("atom_types", row_index, 0)
    assert selection["ok"]
    serial = int(selection["serials"][0])
    assert 1 <= serial <= natom
    atom_info = model.get_atom_info(serial)
    assert atom_info["ok"]

    dihedral_table = info["tables"]["dihedral_types"]
    if dihedral_table["rows"]:
        dihedral_selection = model.get_system_info_selection("dihedral_types", 0, 0)
        assert dihedral_selection["ok"]
        highlight = model.get_parm7_highlights(dihedral_selection["serials"], "Dihedral")
        assert highlight["ok"]
        interaction = highlight.get("interaction") or {}
        dihedrals = interaction.get("dihedrals") or []
        if dihedrals:
            assert all(entry.get("scee") is None for entry in dihedrals)
            assert all(entry.get("scnb") is None for entry in dihedrals)
