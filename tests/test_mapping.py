from topview.model import AtomMeta, ResidueMeta
from topview.services.loader import _extract_bond_pairs
from topview.services.pdb_writer import write_pdb


def test_pdb_writer_serials_order():
    residue = ResidueMeta(resid=1, resname="LIG")
    metas = [
        AtomMeta(
            serial=1,
            atom_name="C1",
            element="C",
            residue=residue,
            residue_index=1,
            coords=(0.0, 0.0, 0.0),
            parm7={},
        ),
        AtomMeta(
            serial=2,
            atom_name="N2",
            element="N",
            residue=residue,
            residue_index=1,
            coords=(1.0, 0.0, 0.0),
            parm7={},
        ),
        AtomMeta(
            serial=3,
            atom_name="O3",
            element="O",
            residue=residue,
            residue_index=1,
            coords=(2.0, 0.0, 0.0),
            parm7={},
        ),
    ]

    pdb = write_pdb(metas)
    lines = [line for line in pdb.splitlines() if line.startswith("ATOM")]

    assert len(lines) == 3
    assert lines[0][6:11].strip() == "1"
    assert lines[1][6:11].strip() == "2"
    assert lines[2][6:11].strip() == "3"


def test_pdb_writer_no_conect_when_no_bonds():
    residue = ResidueMeta(resid=1, resname="LIG")
    metas = [
        AtomMeta(
            serial=1, atom_name="C1", element="C", residue=residue,
            residue_index=1, coords=(0.0, 0.0, 0.0), parm7={},
        ),
    ]
    pdb = write_pdb(metas)
    assert "CONECT" not in pdb


def test_pdb_writer_conect_records():
    residue = ResidueMeta(resid=1, resname="LIG")
    metas = [
        AtomMeta(
            serial=1, atom_name="C1", element="C", residue=residue,
            residue_index=1, coords=(0.0, 0.0, 0.0), parm7={},
        ),
        AtomMeta(
            serial=2, atom_name="O1", element="O", residue=residue,
            residue_index=1, coords=(1.2, 0.0, 0.0), parm7={},
        ),
        AtomMeta(
            serial=3, atom_name="N1", element="N", residue=ResidueMeta(resid=2, resname="NME"),
            residue_index=2, coords=(2.5, 0.0, 0.0), parm7={},
        ),
    ]
    bonds = [(1, 2), (2, 3)]
    pdb = write_pdb(metas, bonds=bonds)
    conect_lines = [l for l in pdb.splitlines() if l.startswith("CONECT")]
    assert len(conect_lines) == 3
    assert "CONECT    1    2" in pdb
    assert "CONECT    2    1    3" in pdb
    assert "CONECT    3    2" in pdb


def test_extract_bond_pairs_from_parm7():
    from topview.model.state import Parm7Token, Parm7Section

    def _make_section(name, values):
        tokens = [Parm7Token(value=str(v), line=1, start=0, end=0) for v in values]
        return Parm7Section(
            name=name, count=0, width=0, flag_line=0, end_line=0, tokens=tokens,
        )

    sections = {
        "BONDS_WITHOUT_HYDROGEN": _make_section(
            "BONDS_WITHOUT_HYDROGEN",
            [0, 3, 1, 3, 6, 2, 42, 48, 2],
        ),
    }
    bonds = _extract_bond_pairs(sections)
    assert (1, 2) in bonds
    assert (2, 3) in bonds
    assert (15, 17) in bonds
