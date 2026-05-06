"""Topview application entrypoint."""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
from pathlib import Path
import sys
from typing import Optional, Sequence, Tuple

from topview import config
from topview.logging_config import configure_logging

logger = logging.getLogger(__name__)

_EXPORT_TABLE_SPECS = {
    "atom": {"table": "atom_types", "filename": "topview-atom.csv"},
    "bond": {"table": "bond_types", "filename": "topview-bond.csv"},
    "angle": {"table": "angle_types", "filename": "topview-angle.csv"},
    "dihedral": {
        "table": "dihedral_types",
        "filename": "topview-dihedral.csv",
    },
    "improper": {
        "table": "improper_types",
        "filename": "topview-improper.csv",
    },
    "14nonbonded": {
        "table": "one_four_nonbonded",
        "filename": "topview-14nonbonded.csv",
    },
    "nonbonded": {
        "table": "nonbonded_pairs",
        "filename": "topview-nonbonded.csv",
    },
}


def _parse_parm7(path: str):
    from topview.services.parm7 import parse_parm7

    return parse_parm7(path)


def _parse_pointers(section):
    from topview.services.parm7 import parse_pointers

    return parse_pointers(section)


def _parse_nmr_restraints(path: str, natom: int):
    from topview.services.nmr_restraints import parse_nmr_restraints

    return parse_nmr_restraints(path, natom=natom)


def _build_system_info_tables(sections):
    from topview.services.system_info import build_system_info_tables

    return build_system_info_tables(sections)


def _validate_nmr_startup_inputs(
    parm7_path: Optional[str],
    rst7_path: Optional[str],
    nmr_path: Optional[str],
) -> None:
    """Fail fast on invalid CLI-supplied NMR restraint inputs."""

    if not nmr_path:
        return
    if not parm7_path or not rst7_path:
        raise SystemExit("--nmr requires both parm7 and rst7 paths")
    try:
        _, sections = _parse_parm7(parm7_path)
    except Exception as exc:
        raise SystemExit(f"Failed to parse parm7 while validating --nmr: {exc}") from exc
    pointer_section = sections.get("POINTERS")
    if not pointer_section or not pointer_section.tokens:
        raise SystemExit("Failed to validate --nmr: POINTERS section missing")
    try:
        natom = int(_parse_pointers(pointer_section).get("NATOM", 0))
    except Exception as exc:
        raise SystemExit(f"Failed to parse POINTERS while validating --nmr: {exc}") from exc
    if natom <= 0:
        raise SystemExit("Failed to validate --nmr: invalid NATOM in parm7 POINTERS")
    try:
        _parse_nmr_restraints(nmr_path, natom=natom)
    except ValueError as exc:
        raise SystemExit(f"Failed to parse NMR restraints: {exc}") from exc


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{config.APP_NAME}")
    parser.add_argument("parm7_path", nargs="?", help="Path to parm7/prmtop file")
    parser.add_argument("rst7_path", nargs="?", help="Path to rst7/inpcrd file")
    parser.add_argument(
        "--export",
        dest="export",
        default=None,
        help=(
            "Comma-separated CSV exports: atom,bond,angle,dihedral,"
            "improper,14nonbonded,nonbonded"
        ),
    )
    parser.add_argument(
        "--nmr",
        dest="nmr_path",
        default=None,
        help="Path to an Amber NMR restraint file to display in 3D mode",
    )
    parser.add_argument(
        "--resname",
        dest="resname",
        default=config.DEFAULT_RESNAME,
        help="Residue name to depict when only parm7 is provided, or 'all' for all residues",
    )
    parser.add_argument(
        "--log-file",
        dest="log_file",
        default=None,
        help="Write debug logs to this file instead of stdout",
    )
    parser.add_argument(
        "--info-font-size",
        dest="info_font_size",
        type=float,
        default=config.DEFAULT_INFO_FONT_SIZE,
        help="Font size (pt) for section info popups",
    )
    return parser.parse_args(argv[1:])


def _parse_export_terms(value: Optional[str]) -> list[str]:
    if value is None:
        return []
    terms: list[str] = []
    seen = set()
    for raw_term in value.split(","):
        term = raw_term.strip().lower()
        if not term:
            raise SystemExit("--export requires a comma-separated list of terms")
        if term not in _EXPORT_TABLE_SPECS:
            supported = ", ".join(_EXPORT_TABLE_SPECS)
            raise SystemExit(
                f"Unsupported --export term '{term}'. Expected one of: {supported}"
            )
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _build_csv_text(columns: Sequence[object], rows: Sequence[Sequence[object]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(
            [
                row[idx] if row is not None and idx < len(row) else ""
                for idx in range(len(columns))
            ]
        )
    return buffer.getvalue()


def _export_system_info_csvs(
    parm7_path: str,
    export_terms: Sequence[str],
    output_dir: Optional[Path] = None,
) -> list[Path]:
    _, sections = _parse_parm7(parm7_path)
    tables = _build_system_info_tables(sections)
    base_dir = Path.cwd() if output_dir is None else Path(output_dir)
    exported_paths: list[Path] = []
    for term in export_terms:
        spec = _EXPORT_TABLE_SPECS[term]
        table = tables.get(spec["table"])
        if not table:
            raise ValueError(f"System info table '{spec['table']}' is not available")
        csv_text = _build_csv_text(table.get("columns") or [], table.get("rows") or [])
        output_path = base_dir / spec["filename"]
        with open(output_path, "w", encoding="utf-8", newline="") as handle:
            handle.write(csv_text)
        exported_paths.append(output_path)
    return exported_paths


def create_app(
    initial_paths: Optional[Tuple[str, Optional[str]]] = None,
    info_font_size: float = config.DEFAULT_INFO_FONT_SIZE,
    initial_resname: str = config.DEFAULT_RESNAME,
    initial_nmr_path: Optional[str] = None,
):
    """Create the pywebview window and API bridge.

    Parameters
    ----------
    initial_paths
        Optional tuple of parm7 and rst7 paths (rst7 can be None).
    info_font_size
        Font size for section info popups.
    initial_resname
        Residue name to depict when only parm7 is provided.

    Returns
    -------
    webview.Window
        Configured pywebview window.
    """

    import webview
    from topview.bridge import Api
    from topview.model import Model
    from topview.worker import Worker

    worker = Worker(max_workers=1, max_processes=1)
    model = Model(cpu_submit=worker.submit_cpu)
    api = Api(
        model=model,
        worker=worker,
        initial_paths=initial_paths,
        initial_resname=initial_resname,
        initial_nmr_path=initial_nmr_path,
        ui_config={"info_font_size": info_font_size},
    )

    window = webview.create_window(
        config.WINDOW_TITLE,
        url=str(config.INDEX_PATH),
        width=config.DEFAULT_WINDOW_WIDTH,
        height=config.DEFAULT_WINDOW_HEIGHT,
        resizable=True,
        js_api=api,
        text_select=True,
    )
    api.set_window(window)
    return window


def main() -> None:
    """Run the Topview application.

    Returns
    -------
    None
        This function does not return a value.
    """

    args = _parse_args(sys.argv)

    configure_logging(args.log_file)
    logger.debug("Starting application")
    export_terms = _parse_export_terms(args.export)
    if export_terms:
        if not args.parm7_path:
            raise SystemExit("--export requires a parm7 path")
        try:
            exported_paths = _export_system_info_csvs(args.parm7_path, export_terms)
        except Exception as exc:
            raise SystemExit(f"Failed to export CSVs: {exc}") from exc
        for output_path in exported_paths:
            print(output_path)
        return

    _validate_nmr_startup_inputs(args.parm7_path, args.rst7_path, args.nmr_path)
    import webview

    initial_paths = None
    if args.parm7_path:
        initial_paths = (args.parm7_path, args.rst7_path)
        logger.debug("Launching with initial files")
    else:
        logger.debug("Launching without initial files")
    create_app(
        initial_paths=initial_paths,
        info_font_size=args.info_font_size,
        initial_resname=args.resname,
        initial_nmr_path=args.nmr_path,
    )
    gui = os.environ.get("PYWEBVIEW_GUI") or None
    if gui:
        logger.debug("Using pywebview GUI backend: %s", gui)
    else:
        logger.debug("Using pywebview GUI backend: auto")
    webview.start(debug=False, gui=gui)


if __name__ == "__main__":
    main()
