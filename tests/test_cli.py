import pytest
from pathlib import Path

from topview import config
from topview.app import _parse_args
import topview.app as app_module


def test_parse_args_parm7_only_defaults_resname() -> None:
    args = _parse_args(["topview", "example.parm7"])
    assert args.parm7_path == "example.parm7"
    assert args.rst7_path is None
    assert args.resname == config.DEFAULT_RESNAME


def test_parse_args_resname_override() -> None:
    args = _parse_args(["topview", "example.parm7", "--resname", "ABC"])
    assert args.resname == "ABC"


def test_parse_args_resname_all() -> None:
    args = _parse_args(["topview", "example.parm7", "--resname", "all"])
    assert args.resname == "all"


def test_parse_args_nmr_override() -> None:
    args = _parse_args(["topview", "example.parm7", "example.rst7", "--nmr", "rest.in"])
    assert args.nmr_path == "rest.in"


def test_parse_args_export_override() -> None:
    args = _parse_args(["topview", "example.parm7", "--export", "atom,bond"])
    assert args.export == "atom,bond"


def test_parse_export_terms_rejects_unknown_term() -> None:
    with pytest.raises(SystemExit, match="Unsupported --export term 'bogus'"):
        app_module._parse_export_terms("atom,bogus")


def test_export_system_info_csvs_writes_requested_tables(tmp_path, monkeypatch) -> None:
    parm7_path = Path(__file__).resolve().parents[1] / "tests" / "data" / "wcn.parm7"
    assert parm7_path.exists()

    monkeypatch.chdir(tmp_path)
    exported = app_module._export_system_info_csvs(
        str(parm7_path),
        app_module._parse_export_terms("atom,14nonbonded,nonbonded"),
    )

    assert [path.name for path in exported] == [
        "topview-atom.csv",
        "topview-14nonbonded.csv",
        "topview-nonbonded.csv",
    ]
    atom_csv = (tmp_path / "topview-atom.csv").read_text(encoding="utf-8")
    one_four_csv = (tmp_path / "topview-14nonbonded.csv").read_text(encoding="utf-8")
    nonbonded_csv = (tmp_path / "topview-nonbonded.csv").read_text(encoding="utf-8")

    assert atom_csv.startswith("type_index,amber_type")
    assert one_four_csv.startswith(
        "type_a,type_a_name,type_b,type_b_name,param_index,scee,scnb"
    )
    assert nonbonded_csv.startswith(
        "type_a,type_a_name,type_b,type_b_name,pair_index,acoef,bcoef,rmin,epsilon"
    )


def test_validate_nmr_startup_inputs_exits_on_parse_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "_parse_parm7",
        lambda _path: ("", {"POINTERS": type("Section", (), {"tokens": [object()]})()}),
    )
    monkeypatch.setattr(app_module, "_parse_pointers", lambda _section: {"NATOM": 10})
    monkeypatch.setattr(
        app_module,
        "_parse_nmr_restraints",
        lambda _path, natom: (_ for _ in ()).throw(ValueError("bad restraint")),
    )

    with pytest.raises(SystemExit, match="Failed to parse NMR restraints: bad restraint"):
        app_module._validate_nmr_startup_inputs("example.parm7", "example.rst7", "rest.in")
