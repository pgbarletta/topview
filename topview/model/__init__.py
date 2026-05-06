"""Model package exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from topview.model.state import AtomMeta, Parm7Section, Parm7Token, ResidueMeta

if TYPE_CHECKING:
    from topview.model.model import Model

__all__ = ["AtomMeta", "Model", "Parm7Section", "Parm7Token", "ResidueMeta"]


def __getattr__(name: str):
    if name == "Model":
        from topview.model.model import Model

        return Model
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
