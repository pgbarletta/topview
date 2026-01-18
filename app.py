import argparse
import logging
import os
import sys
from typing import Optional

import webview

from api import Api
from model import Model
from worker import Worker

logger = logging.getLogger(__name__)


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="Parm7 Viewer")
    parser.add_argument("parm7_path", nargs="?", help="Path to parm7/prmtop file")
    parser.add_argument("rst7_path", nargs="?", help="Path to rst7/inpcrd file")
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
        default=13.0,
        help="Font size (pt) for section info popups",
    )
    args = parser.parse_args(argv[1:])
    if (args.parm7_path and not args.rst7_path) or (args.rst7_path and not args.parm7_path):
        parser.print_usage(sys.stderr)
        args.parm7_path = None
        args.rst7_path = None
    return args


def _configure_logging(log_file: Optional[str]) -> None:
    handler = None
    if log_file:
        try:
            handler = logging.FileHandler(log_file, encoding="utf-8")
        except OSError as exc:
            print(f"Failed to open log file '{log_file}': {exc}", file=sys.stderr)
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[handler],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app(initial_paths=None, info_font_size: float = 13.0):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_dir, "web", "index.html")

    worker = Worker(max_workers=1, max_processes=1)
    model = Model(cpu_submit=worker.submit_cpu)
    api = Api(
        model=model,
        worker=worker,
        initial_paths=initial_paths,
        ui_config={"info_font_size": info_font_size},
    )

    window = webview.create_window(
        "Parm7 Viewer",
        url=index_path,
        width=1200,
        height=800,
        resizable=True,
        js_api=api,
        text_select=True,
    )
    api.set_window(window)
    return window


def main():
    args = _parse_args(sys.argv)
    _configure_logging(args.log_file)
    logger.debug("Starting application")
    initial_paths = None
    if args.parm7_path and args.rst7_path:
        initial_paths = (args.parm7_path, args.rst7_path)
        logger.debug("Launching with initial files")
    else:
        logger.debug("Launching without initial files")
    create_app(initial_paths=initial_paths, info_font_size=args.info_font_size)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
