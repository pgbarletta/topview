from topview import config
from topview.app import _parse_args


def test_parse_args_parm7_only_defaults_resname() -> None:
    args = _parse_args(["topview", "example.parm7"])
    assert args.parm7_path == "example.parm7"
    assert args.rst7_path is None
    assert args.resname == config.DEFAULT_RESNAME


def test_parse_args_resname_override() -> None:
    args = _parse_args(["topview", "example.parm7", "--resname", "ABC"])
    assert args.resname == "ABC"
