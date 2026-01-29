import numpy as np

from topview.model.state import Parm7Section, Parm7Token
from topview.services.system_info import _build_dihedral_table, _build_rotatable_bonds


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


def ptr(serial):
    return (serial - 1) * 3


def test_rotatable_bond_simple_true():
    sections = {
        "BONDS_WITHOUT_HYDROGEN": make_section(
            "BONDS_WITHOUT_HYDROGEN", [ptr(2), ptr(3), 1]
        ),
        "DIHEDRALS_INC_HYDROGEN": make_section(
            "DIHEDRALS_INC_HYDROGEN", [ptr(1), ptr(2), ptr(3), ptr(4), 1]
        ),
    }
    masses = np.array([12.0, 12.0, 12.0, 12.0], dtype=float)

    rotatable = _build_rotatable_bonds(sections, 0, 1, 1, 0, masses)

    assert (2, 3) in rotatable


def test_rotatable_bond_overlap_false():
    sections = {
        "BONDS_WITHOUT_HYDROGEN": make_section(
            "BONDS_WITHOUT_HYDROGEN", [ptr(2), ptr(3), 1]
        ),
        "DIHEDRALS_INC_HYDROGEN": make_section(
            "DIHEDRALS_INC_HYDROGEN",
            [
                ptr(1), ptr(2), ptr(3), ptr(4), 1,
                ptr(2), ptr(5), ptr(6), ptr(7), 1,
                ptr(3), ptr(5), ptr(8), ptr(9), 1,
            ],
        ),
    }
    masses = np.array([12.0] * 9, dtype=float)

    rotatable = _build_rotatable_bonds(sections, 0, 1, 3, 0, masses)

    assert (2, 3) not in rotatable


def test_dihedral_table_has_rotatable_column():
    sections = {
        "BONDS_WITHOUT_HYDROGEN": make_section(
            "BONDS_WITHOUT_HYDROGEN", [ptr(2), ptr(3), 1]
        ),
        "DIHEDRALS_INC_HYDROGEN": make_section(
            "DIHEDRALS_INC_HYDROGEN", [ptr(1), ptr(2), ptr(3), ptr(4), 1]
        ),
    }
    atom_names = ["A1", "A2", "A3", "A4"]
    atom_types = ["C", "C", "C", "C"]
    masses = np.array([12.0, 12.0, 12.0, 12.0], dtype=float)
    dihedral_force = np.array([1.0], dtype=float)
    dihedral_periodicity = np.array([2.0], dtype=float)
    dihedral_phase = np.array([180.0], dtype=float)
    scee_scale = np.array([1.2], dtype=float)
    scnb_scale = np.array([2.0], dtype=float)

    table = _build_dihedral_table(
        sections,
        atom_names,
        atom_types,
        1,
        0,
        dihedral_force,
        dihedral_periodicity,
        dihedral_phase,
        scee_scale,
        scnb_scale,
        0,
        1,
        masses,
    )

    assert "amber_rotatable" in table.columns
    assert table.iloc[0]["amber_rotatable"] in ("T", "F")
