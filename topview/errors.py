"""Error types and API error payload helpers."""

from __future__ import annotations

from typing import Dict, Optional


class TopviewError(Exception):
    """Base exception type for Topview.

    Attributes
    ----------
    code
        Stable error identifier.
    message
        Human-readable error message.
    details
        Optional detail payload for debugging.
    """

    def __init__(self, code: str, message: str, details: Optional[object] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_result(self) -> Dict[str, object]:
        """Return a JSON-ready error payload.

        Returns
        -------
        dict
            JSON-ready error payload.
        """
        return error_result(self.code, self.message, self.details)


class ModelError(TopviewError):
    """Errors raised by the model layer.

    Attributes
    ----------
    code
        Stable error identifier.
    message
        Human-readable error message.
    details
        Optional detail payload for debugging.
    """


class ApiError(TopviewError):
    """Errors raised by the API bridge layer.

    Attributes
    ----------
    code
        Stable error identifier.
    message
        Human-readable error message.
    details
        Optional detail payload for debugging.
    """


class PdbWriterError(TopviewError):
    """Errors raised when formatting PDB output.

    Attributes
    ----------
    code
        Stable error identifier.
    message
        Human-readable error message.
    details
        Optional detail payload for debugging.
    """


def error_result(code: str, message: str, details: Optional[object] = None) -> Dict[str, object]:
    """Build an API error payload.

    Parameters
    ----------
    code
        Stable error identifier.
    message
        Human-readable summary.
    details
        Optional detail payload for logging or debugging.

    Returns
    -------
    dict
        JSON-ready error payload.
    """

    return {"ok": False, "error": {"code": code, "message": message, "details": details}}
