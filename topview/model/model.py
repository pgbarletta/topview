"""Model layer for Topview."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future
from typing import Callable, Dict, Optional, Sequence, Tuple

from topview.errors import ModelError
from topview.model.highlights import HighlightEngine
from topview.model.query import query_atoms
from topview.model.state import ModelState
from topview.services.loader import load_system_data
from topview.services.parm7 import (
    load_parm7_deprecated_flags,
    load_parm7_descriptions,
)
from topview.services.system_info import (
    build_system_info_tables,
    build_system_info_tables_with_timing,
)
from topview.services.system_info_selection import (
    build_system_info_selection_index,
    nonbonded_pair_for_cursor,
    nonbonded_pair_total,
)

logger = logging.getLogger(__name__)


class Model:
    """Core application model and state store.

    Attributes
    ----------
    _state
        Mutable model state.
    _cpu_submit
        Optional CPU executor submit function.
    """

    def __init__(self, cpu_submit: Optional[Callable[..., object]] = None) -> None:
        """Initialize the model.

        Parameters
        ----------
        cpu_submit
            Optional executor submission function for CPU-heavy work.

        Returns
        -------
        None
            This method does not return a value.
        """

        self._lock = threading.Lock()
        self._state = ModelState()
        self._cpu_submit = cpu_submit

    def get_parm7_text(self) -> Dict[str, object]:
        """Return base64-encoded parm7 text.

        Returns
        -------
        dict
            Payload containing the parm7 text.

        Raises
        ------
        ModelError
            If no parm7 text is loaded.
        """

        with self._lock:
            if not self._state.loaded or not self._state.parm7_text_b64:
                raise ModelError("not_loaded", "No parm7 text loaded")
            return {"ok": True, "parm7_text_b64": self._state.parm7_text_b64}

    def get_parm7_sections(self) -> Dict[str, object]:
        """Return parsed parm7 section metadata.

        Returns
        -------
        dict
            Payload containing parm7 sections.

        Raises
        ------
        ModelError
            If sections are not loaded.
        """

        with self._lock:
            if not self._state.loaded or not self._state.parm7_sections:
                raise ModelError("not_loaded", "No parm7 sections available")
            descriptions = load_parm7_descriptions()
            deprecated_flags = load_parm7_deprecated_flags()
            sections = [
                {
                    "name": section.name,
                    "line": section.flag_line,
                    "end_line": section.end_line,
                    "description": descriptions.get(section.name, ""),
                    "deprecated": section.name in deprecated_flags,
                }
                for section in self._state.parm7_sections.values()
            ]
        sections.sort(key=lambda item: item["line"])
        return {"ok": True, "sections": sections}

    def get_parm7_highlights(
        self, serials: Sequence[int], mode: Optional[str] = None
    ) -> Dict[str, object]:
        """Return parm7 highlights and interaction metadata.

        Parameters
        ----------
        serials
            Selected atom serials.
        mode
            Selection mode.

        Returns
        -------
        dict
            Payload containing highlights and interaction data.

        Raises
        ------
        ModelError
            If no system is loaded or serials are invalid.
        """

        with self._lock:
            if not self._state.loaded:
                raise ModelError("not_loaded", "No system loaded")
            if not self._state.parm7_sections:
                raise ModelError("not_loaded", "No parm7 sections available")
            engine = HighlightEngine(
                self._state.parm7_sections,
                self._state.meta_by_serial,
                self._state.int_section_cache,
                self._state.float_section_cache,
            )
            highlights, interaction = engine.get_highlights(serials, mode=mode)
        return {
            "ok": True,
            "highlights": highlights,
            "interaction": interaction,
        }

    def get_atom_bundle(self, serial: int) -> Dict[str, object]:
        """Return atom metadata plus base parm7 highlights.

        Parameters
        ----------
        serial
            Atom serial.

        Returns
        -------
        dict
            Payload containing atom metadata and highlights.

        Raises
        ------
        ModelError
            If no system is loaded or the serial is missing.
        """

        with self._lock:
            if not self._state.loaded:
                raise ModelError("not_loaded", "No system loaded")
            meta = self._state.meta_by_serial.get(int(serial))
            sections = dict(self._state.parm7_sections)
            int_cache = self._state.int_section_cache
            float_cache = self._state.float_section_cache
        if meta is None:
            raise ModelError("not_found", f"Atom serial {serial} not found")
        if not sections:
            raise ModelError("not_loaded", "No parm7 sections available")
        engine = HighlightEngine(sections, {meta.serial: meta}, int_cache, float_cache)
        highlights, _ = engine.get_highlights([meta.serial], mode="Atom")
        return {"ok": True, "atom": meta.to_dict(), "highlights": highlights}

    def load_system(
        self, parm7_path: str, rst7_path: Optional[str], resname: Optional[str] = None
    ) -> Dict[str, object]:
        """Load a parm7 system and populate model state.

        Parameters
        ----------
        parm7_path
            Path to the parm7 file.
        rst7_path
            Optional path to the rst7 file.
        resname
            Residue name to depict when only parm7 is provided.

        Returns
        -------
        dict
            Payload containing load metadata.

        Raises
        ------
        ModelError
            If loading fails or files are missing.
        """

        load_started_at = time.perf_counter()
        result = load_system_data(
            parm7_path,
            rst7_path,
            resname=resname,
            cpu_submit=self._cpu_submit,
        )
        info_future = None
        if self._cpu_submit:
            try:
                info_future = self._cpu_submit(
                    build_system_info_tables_with_timing, result.parm7_sections
                )
            except Exception:
                logger.exception("Failed to schedule system info build")
        with self._lock:
            self._state.meta_list = result.meta_list
            self._state.meta_by_serial = result.meta_by_serial
            self._state.residue_index = result.residue_index
            self._state.residue_keys_by_resid = result.residue_keys_by_resid
            self._state.parm7_text_b64 = result.parm7_text_b64
            self._state.parm7_sections = result.parm7_sections
            self._state.int_section_cache = {}
            self._state.float_section_cache = {}
            self._state.system_info = None
            self._state.system_info_future = info_future
            self._state.system_info_selection_index = None
            self._state.system_info_selection_future = None
            self._state.load_timings = result.timings
            self._state.load_started_at = load_started_at
            self._state.loaded = True
        payload = {
            "ok": True,
            "view_mode": result.view_mode,
            "natoms": result.natoms,
            "nresidues": result.nresidues,
            "warnings": result.warnings,
        }
        if result.view_mode == "3d":
            payload["pdb_b64"] = result.pdb_b64
        else:
            payload["depiction"] = result.depiction
        return payload

    def get_atom_info(self, serial: int) -> Dict[str, object]:
        """Return atom metadata for a single serial.

        Parameters
        ----------
        serial
            Atom serial.

        Returns
        -------
        dict
            Payload containing atom metadata.

        Raises
        ------
        ModelError
            If no system is loaded or the serial is missing.
        """

        with self._lock:
            if not self._state.loaded:
                raise ModelError("not_loaded", "No system loaded")
            meta = self._state.meta_by_serial.get(int(serial))
        if meta is None:
            raise ModelError("not_found", f"Atom serial {serial} not found")
        logger.debug("Atom info requested serial=%s", serial)
        return {"ok": True, "atom": meta.to_dict()}

    def query_atoms(
        self, filters: Dict[str, object], max_results: int = 50000
    ) -> Dict[str, object]:
        """Query atoms by filter criteria.

        Parameters
        ----------
        filters
            Filter payload from the UI.
        max_results
            Maximum number of results to return.

        Returns
        -------
        dict
            Query response payload.

        Raises
        ------
        ModelError
            If no system is loaded.
        """

        with self._lock:
            if not self._state.loaded:
                raise ModelError("not_loaded", "No system loaded")
            meta_list = list(self._state.meta_list)
        return query_atoms(meta_list, filters, max_results=max_results)

    def get_residue_info(self, resid: int) -> Dict[str, object]:
        """Return residue metadata and atom serials.

        Parameters
        ----------
        resid
            Residue id.

        Returns
        -------
        dict
            Payload containing residue metadata.

        Raises
        ------
        ModelError
            If the residue is missing or ambiguous.
        """

        with self._lock:
            if not self._state.loaded:
                raise ModelError("not_loaded", "No system loaded")
            keys = self._state.residue_keys_by_resid.get(int(resid), [])
            residue_index = dict(self._state.residue_index)
        if not keys:
            raise ModelError("not_found", f"Residue {resid} not found")
        if len(keys) > 1:
            raise ModelError("ambiguous", "Residue id is not unique", keys)
        key = keys[0]
        serials = residue_index.get(key, [])
        parts = key.split(":")
        segid = parts[0] or None
        resid_str = parts[1]
        resname = parts[2] if len(parts) > 2 else ""
        logger.debug("Residue info requested resid=%s", resid)
        return {
            "ok": True,
            "residue": {
                "segid": segid,
                "resid": int(resid_str),
                "resname": resname,
                "serials": serials,
            },
        }

    def get_system_info(self) -> Dict[str, object]:
        """Return cached or newly built system info tables.

        Returns
        -------
        dict
            Payload containing system info tables.

        Raises
        ------
        ModelError
            If no system is loaded or table generation fails.
        """

        with self._lock:
            if not self._state.loaded:
                raise ModelError("not_loaded", "No system loaded")
            cached = self._state.system_info
            future = self._state.system_info_future
            sections = None if future is not None else dict(self._state.parm7_sections)
            load_timings = dict(self._state.load_timings or {})
            load_started_at = self._state.load_started_at
        if cached is not None:
            return {"ok": True, "tables": cached}
        if future is not None:
            try:
                tables, elapsed = future.result()
            except ValueError as exc:
                with self._lock:
                    self._state.system_info_future = None
                raise ModelError(
                    "parm7_parse_failed", "Failed to build system info tables", str(exc)
                ) from exc
            except Exception as exc:
                with self._lock:
                    self._state.system_info_future = None
                raise ModelError(
                    "parm7_parse_failed",
                    "Failed to build system info tables",
                    str(exc),
                ) from exc
        else:
            try:
                tables, elapsed = build_system_info_tables_with_timing(sections or {})
            except ValueError as exc:
                raise ModelError(
                    "parm7_parse_failed", "Failed to build system info tables", str(exc)
                ) from exc
        if load_timings:
            cpu_time = (
                load_timings.get("universe", 0.0)
                + load_timings.get("parm7", 0.0)
                + load_timings.get("lj", 0.0)
                + load_timings.get("meta_attrs", 0.0)
                + load_timings.get("meta_build", 0.0)
                + load_timings.get("pdb", 0.0)
                + elapsed
            )
            wall_time = load_timings.get("total", 0.0) + elapsed
            if wall_time <= 0.0:
                wall_time = cpu_time
            logger.debug(
                "Timings: universe=%.3fs(load_pool) parm7=%.3fs(load_pool) lj=%.3fs(main) meta_attrs=%.3fs(main) meta_build=%.3fs(main) pdb=%.3fs(main) system_info=%.3fs(cpu_worker) cpu=%.3fs wall=%.3fs",
                load_timings.get("universe", 0.0),
                load_timings.get("parm7", 0.0),
                load_timings.get("lj", 0.0),
                load_timings.get("meta_attrs", 0.0),
                load_timings.get("meta_build", 0.0),
                load_timings.get("pdb", 0.0),
                elapsed,
                cpu_time,
                wall_time,
            )
        with self._lock:
            self._state.system_info = tables
            self._state.system_info_future = None
        return {"ok": True, "tables": tables}

    def get_system_info_selection(
        self, table: str, row_index: int, cursor: int = 0
    ) -> Dict[str, object]:
        """Return a selection for a system info table row.

        Parameters
        ----------
        table
            System info table key.
        row_index
            Row index in the table.
        cursor
            Cursor position for cycling selections.

        Returns
        -------
        dict
            Payload containing selection mode, serials, and total matches.

        Raises
        ------
        ModelError
            If the system is not loaded or the row is invalid.
        """

        if not isinstance(table, str) or not table:
            raise ModelError("invalid_input", "table is required")
        try:
            row_idx = int(row_index)
        except (TypeError, ValueError) as exc:
            raise ModelError("invalid_input", "row_index must be an integer") from exc
        try:
            cursor_idx = int(cursor)
        except (TypeError, ValueError) as exc:
            raise ModelError("invalid_input", "cursor must be an integer") from exc
        if row_idx < 0 or cursor_idx < 0:
            raise ModelError("invalid_input", "row_index and cursor must be >= 0")

        info = self.get_system_info()
        tables = info.get("tables", {}) if info else {}
        table_data = tables.get(table)
        if not table_data:
            raise ModelError("not_found", f"System info table '{table}' not available")
        columns = list(table_data.get("columns") or [])
        rows = list(table_data.get("rows") or [])
        if not rows or row_idx >= len(rows):
            raise ModelError("not_found", "Row index out of range")
        row = rows[row_idx] or []
        row_map = {columns[idx]: row[idx] for idx in range(min(len(columns), len(row)))}

        selection_index = self._get_system_info_selection_index()
        mode = _mode_for_table(table)

        if table == "atom_types":
            type_index = _coerce_int(row_map.get("type_index"))
            serials_for_type = (
                selection_index.atom_serials_by_type.get(type_index, [])
                if type_index
                else []
            )
            total = len(serials_for_type)
            if total == 0:
                raise ModelError("not_found", "No matches for row")
            index = cursor_idx % total
            serials = [int(serials_for_type[index])]
            return {
                "ok": True,
                "mode": mode,
                "serials": serials,
                "index": index,
                "total": total,
            }

        if table == "bond_types":
            key = _bond_key(row_map)
            selections = (
                selection_index.bonds_by_key.get(key, []) if key else []
            )
            return _selection_result(mode, selections, cursor_idx)

        if table == "angle_types":
            key = _angle_key(row_map)
            selections = (
                selection_index.angles_by_key.get(key, []) if key else []
            )
            return _selection_result(mode, selections, cursor_idx)

        if table == "dihedral_types":
            idx_value = _coerce_int(row_map.get("idx"))
            if not idx_value:
                raise ModelError("not_found", "No matches for row")
            serials = selection_index.dihedrals_by_idx.get(idx_value)
            if not serials:
                raise ModelError("not_found", "No matches for row")
            return {
                "ok": True,
                "mode": mode,
                "serials": list(serials),
                "index": 0,
                "total": 1,
            }

        if table == "one_four_nonbonded":
            key = _bond_key(row_map)
            selections = (
                selection_index.one_four_by_key.get(key, []) if key else []
            )
            return _selection_result(mode, selections, cursor_idx)

        if table == "nonbonded_pairs":
            type_a = _coerce_int(row_map.get("type_a"))
            type_b = _coerce_int(row_map.get("type_b"))
            if not type_a or not type_b:
                raise ModelError("not_found", "No matches for row")
            serials_a = selection_index.atom_serials_by_type.get(type_a, [])
            serials_b = selection_index.atom_serials_by_type.get(type_b, [])
            same_type = type_a == type_b
            total = nonbonded_pair_total(serials_a, serials_b, same_type)
            if total <= 0:
                raise ModelError("not_found", "No matches for row")
            pair = nonbonded_pair_for_cursor(
                serials_a, serials_b, cursor_idx, same_type
            )
            index = cursor_idx % total
            return {
                "ok": True,
                "mode": mode,
                "serials": [int(pair[0]), int(pair[1])],
                "index": index,
                "total": total,
            }

        raise ModelError("invalid_input", f"Unsupported table '{table}'")

    def _get_system_info_selection_index(self):
        with self._lock:
            if not self._state.loaded:
                raise ModelError("not_loaded", "No system loaded")
            cached = self._state.system_info_selection_index
            future = self._state.system_info_selection_future
            if cached is not None:
                return cached
            if future is None:
                future = Future()
                self._state.system_info_selection_future = future
                sections = dict(self._state.parm7_sections)
            else:
                sections = None

        if cached is not None:
            return cached

        if sections is not None:
            try:
                index = build_system_info_selection_index(sections)
            except ValueError as exc:
                future.set_exception(exc)
                with self._lock:
                    self._state.system_info_selection_future = None
                raise ModelError(
                    "parm7_parse_failed",
                    "Failed to build system info selections",
                    str(exc),
                ) from exc
            with self._lock:
                self._state.system_info_selection_index = index
                self._state.system_info_selection_future = None
            future.set_result(index)
            return index

        if future is None:
            raise ModelError(
                "parm7_parse_failed", "Failed to build system info selections"
            )
        try:
            return future.result()
        except Exception as exc:
            with self._lock:
                self._state.system_info_selection_future = None
            raise ModelError(
                "parm7_parse_failed",
                "Failed to build system info selections",
                str(exc),
            ) from exc


def _mode_for_table(table: str) -> str:
    mapping = {
        "atom_types": "Atom",
        "bond_types": "Bond",
        "angle_types": "Angle",
        "dihedral_types": "Dihedral",
        "one_four_nonbonded": "1-4 Nonbonded",
        "nonbonded_pairs": "Non-bonded",
    }
    return mapping.get(table, "Atom")


def _coerce_int(value: object) -> Optional[int]:
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        return None
    return int_value


def _bond_key(row_map: Dict[str, object]) -> Optional[Tuple[int, int, int]]:
    type_a = _coerce_int(row_map.get("type_a"))
    type_b = _coerce_int(row_map.get("type_b"))
    param_index = _coerce_int(row_map.get("param_index"))
    if not type_a or not type_b or param_index is None:
        return None
    if type_a <= type_b:
        return (type_a, type_b, param_index)
    return (type_b, type_a, param_index)


def _angle_key(row_map: Dict[str, object]) -> Optional[Tuple[int, int, int, int]]:
    type_i = _coerce_int(row_map.get("type_i"))
    type_j = _coerce_int(row_map.get("type_j"))
    type_k = _coerce_int(row_map.get("type_k"))
    param_index = _coerce_int(row_map.get("param_index"))
    if not type_i or not type_j or not type_k or param_index is None:
        return None
    if type_i > type_k:
        type_i, type_k = type_k, type_i
    return (type_i, type_j, type_k, param_index)


def _selection_result(
    mode: str, selections: Sequence[Sequence[int]], cursor_idx: int
) -> Dict[str, object]:
    total = len(selections)
    if total == 0:
        raise ModelError("not_found", "No matches for row")
    index = cursor_idx % total
    serials = list(selections[index])
    return {
        "ok": True,
        "mode": mode,
        "serials": serials,
        "index": index,
        "total": total,
    }
