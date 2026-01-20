"""Query helpers for atom metadata."""

from __future__ import annotations

import logging
from typing import Dict, List

from topview.model.state import AtomMeta

logger = logging.getLogger(__name__)


def query_atoms(
    meta_list: List[AtomMeta],
    filters: Dict[str, object],
    max_results: int = 50000,
) -> Dict[str, object]:
    """Filter atoms by simple string/range filters.

    Parameters
    ----------
    meta_list
        List of atom metadata to filter.
    filters
        Query filters (resname_contains, atomname_contains, atom_type_equals, charge range).
    max_results
        Cap on the number of results returned.

    Returns
    -------
    dict
        Query response payload with serial list and metadata.
    """

    if filters is None:
        filters = {}

    resname_contains = (
        str(filters.get("resname_contains", "") or "").strip().lower()
    )
    atomname_contains = (
        str(filters.get("atomname_contains", "") or "").strip().lower()
    )
    atom_type_equals = (
        str(filters.get("atom_type_equals", "") or "").strip().lower()
    )
    charge_min = filters.get("charge_min", None)
    charge_max = filters.get("charge_max", None)

    try:
        charge_min = (
            float(charge_min)
            if charge_min is not None and charge_min != ""
            else None
        )
    except (TypeError, ValueError):
        charge_min = None
    try:
        charge_max = (
            float(charge_max)
            if charge_max is not None and charge_max != ""
            else None
        )
    except (TypeError, ValueError):
        charge_max = None

    serials: List[int] = []
    for meta in meta_list:
        if (
            resname_contains
            and resname_contains not in meta.residue.resname.lower()
        ):
            continue
        if atomname_contains and atomname_contains not in meta.atom_name.lower():
            continue
        if atom_type_equals:
            atom_type = meta.parm7.get("atom_type")
            if atom_type is None or atom_type.lower() != atom_type_equals:
                continue
        charge = meta.parm7.get("charge")
        if charge_min is not None:
            if charge is None or charge < charge_min:
                continue
        if charge_max is not None:
            if charge is None or charge > charge_max:
                continue
        serials.append(meta.serial)
        if len(serials) >= max_results:
            logger.debug("Query truncated at %d results", len(serials))
            return {
                "ok": True,
                "serials": serials,
                "count": len(serials),
                "truncated": True,
            }

    logger.debug("Query returned %d results", len(serials))
    return {
        "ok": True,
        "serials": serials,
        "count": len(serials),
        "truncated": False,
    }
