from topview.model.state import Parm7Section, Parm7Token
from topview.services.parm7 import POINTER_NAMES
from topview.services.system_info_selection import build_system_info_selection_index


def make_section(name, values):
    tokens = [
        Parm7Token(value=str(value), line=0, start=0, end=len(str(value)))
        for value in values
    ]
    return Parm7Section(
        name=name,
        count=1,
        width=1,
        flag_line=0,
        end_line=0,
        tokens=tokens,
    )


def test_improper_selection_index():
    pointers = [0 for _ in POINTER_NAMES]
    index = {name: idx for idx, name in enumerate(POINTER_NAMES)}
    pointers[index["NATOM"]] = 4
    pointers[index["NTYPES"]] = 1
    pointers[index["NBONH"]] = 0
    pointers[index["MBONA"]] = 3
    pointers[index["NTHETH"]] = 0
    pointers[index["MTHETA"]] = 0
    pointers[index["NPHIH"]] = 1
    pointers[index["MPHIA"]] = 0

    sections = {
        "POINTERS": make_section("POINTERS", pointers),
        "ATOM_TYPE_INDEX": make_section("ATOM_TYPE_INDEX", [1, 1, 1, 1]),
        "BONDS_WITHOUT_HYDROGEN": make_section(
            "BONDS_WITHOUT_HYDROGEN",
            [0, 3, 1, 3, 6, 1, 3, 9, 1],
        ),
        "DIHEDRALS_INC_HYDROGEN": make_section(
            "DIHEDRALS_INC_HYDROGEN", [0, 3, 6, -9, 1]
        ),
    }

    selection_index = build_system_info_selection_index(sections)

    assert selection_index.dihedrals_by_idx[1] == (1, 2, 3, 4)
    assert selection_index.impropers_by_idx[1] == (1, 2, 3, 4)
