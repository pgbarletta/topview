import pytest

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


def test_parse_args_nmr_override() -> None:
    args = _parse_args(["topview", "example.parm7", "example.rst7", "--nmr", "rest.in"])
    assert args.nmr_path == "rest.in"


def test_validate_nmr_startup_inputs_exits_on_parse_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "parse_parm7",
        lambda _path: ("", {"POINTERS": type("Section", (), {"tokens": [object()]})()}),
    )
    monkeypatch.setattr(app_module, "parse_pointers", lambda _section: {"NATOM": 10})
    monkeypatch.setattr(
        app_module,
        "parse_nmr_restraints",
        lambda _path, natom: (_ for _ in ()).throw(ValueError("bad restraint")),
    )

    with pytest.raises(SystemExit, match="Failed to parse NMR restraints: bad restraint"):
        app_module._validate_nmr_startup_inputs("example.parm7", "example.rst7", "rest.in")
