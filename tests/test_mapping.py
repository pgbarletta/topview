from topview.model import AtomMeta, ResidueMeta
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
