"""Logging configuration helpers."""

from __future__ import annotations

import logging
import sys
from typing import Optional


def configure_logging(log_file: Optional[str]) -> None:
    """Configure application logging.

    Parameters
    ----------
    log_file
        Optional path to a log file. When omitted, logs to stdout.

    Returns
    -------
    None
        This function does not return a value.
    """

    handler_error = None
    handlers = []
    if log_file:
        try:
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except OSError as exc:
            handler_error = exc
    if not handlers:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=handlers,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if handler_error is not None:
        logging.getLogger(__name__).warning(
            "Failed to open log file '%s': %s", log_file, handler_error
        )
