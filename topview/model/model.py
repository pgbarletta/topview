"""Model layer for Topview."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional, Sequence

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
