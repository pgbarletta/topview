"""Topview application entrypoint."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional, Tuple

import webview

from topview import config
from topview.bridge import Api
from topview.logging_config import configure_logging
from topview.model import Model
from topview.worker import Worker

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{config.APP_NAME}")
    parser.add_argument("parm7_path", nargs="?", help="Path to parm7/prmtop file")
    parser.add_argument("rst7_path", nargs="?", help="Path to rst7/inpcrd file")
    parser.add_argument(
        "--resname",
        dest="resname",
        default=config.DEFAULT_RESNAME,
        help="Residue name to depict when only parm7 is provided",
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


def create_app(
    initial_paths: Optional[Tuple[str, Optional[str]]] = None,
    info_font_size: float = config.DEFAULT_INFO_FONT_SIZE,
    initial_resname: str = config.DEFAULT_RESNAME,
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

    worker = Worker(max_workers=1, max_processes=1)
    model = Model(cpu_submit=worker.submit_cpu)
    api = Api(
        model=model,
        worker=worker,
        initial_paths=initial_paths,
        initial_resname=initial_resname,
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
    )
    gui = os.environ.get("PYWEBVIEW_GUI") or None
    if gui:
        logger.debug("Using pywebview GUI backend: %s", gui)
    else:
        logger.debug("Using pywebview GUI backend: auto")
    webview.start(debug=False, gui=gui)


if __name__ == "__main__":
    main()
