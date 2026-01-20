"""Python bridge for the JS frontend."""

from __future__ import annotations

import logging
from typing import Dict, Optional

import webview

from topview.errors import ModelError, error_result
from topview.model import Model
from topview.worker import Worker

logger = logging.getLogger(__name__)


class Api:
    """Pywebview API surface for the frontend.

    Attributes
    ----------
    _model
        Model instance handling domain logic.
    _worker
        Worker for background execution.
    _window
        Pywebview window instance for dialogs.
    _initial_paths
        Initial file paths passed via CLI.
    _ui_config
        UI configuration payload for the frontend.
    """

    def __init__(
        self,
        model: Model,
        worker: Worker,
        initial_paths: Optional[tuple[str, str]] = None,
        ui_config: Optional[Dict[str, object]] = None,
    ) -> None:
        """Initialize the bridge API.

        Parameters
        ----------
        model
            Model instance.
        worker
            Worker instance for background tasks.
        initial_paths
            Optional tuple of initial parm7/rst7 paths.
        ui_config
            Optional UI configuration payload.

        Returns
        -------
        None
            This method does not return a value.
        """

        self._model = model
        self._worker = worker
        self._window = None
        self._initial_paths = initial_paths
        self._ui_config = ui_config or {}

    def set_window(self, window) -> None:
        """Bind the pywebview window for dialog usage.

        Parameters
        ----------
        window
            Pywebview window instance.

        Returns
        -------
        None
            This method does not return a value.
        """

        self._window = window

    def get_initial_paths(self, payload: Optional[Dict[str, object]] = None):
        """Return CLI-provided paths once.

        Parameters
        ----------
        payload
            Unused payload placeholder.

        Returns
        -------
        dict
            Payload with initial parm7/rst7 paths.
        """

        if not self._initial_paths:
            return {"ok": True, "parm7_path": None, "rst7_path": None}
        parm7_path, rst7_path = self._initial_paths
        self._initial_paths = None
        logger.debug("get_initial_paths returned paths")
        return {"ok": True, "parm7_path": parm7_path, "rst7_path": rst7_path}

    def get_ui_config(self, payload: Optional[Dict[str, object]] = None):
        """Return UI configuration for the frontend.

        Parameters
        ----------
        payload
            Unused payload placeholder.

        Returns
        -------
        dict
            Payload with UI configuration.
        """

        return {"ok": True, "config": self._ui_config}

    def load_system(self, payload: Dict[str, object]):
        """Load a parm7/rst7 pair.

        Parameters
        ----------
        payload
            Payload containing parm7_path and rst7_path.

        Returns
        -------
        dict
            Load response payload.
        """

        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        parm7_path = payload.get("parm7_path")
        rst7_path = payload.get("rst7_path")
        try:
            logger.debug("load_system requested parm7=%s rst7=%s", parm7_path, rst7_path)
            future = self._worker.submit(self._model.load_system, parm7_path, rst7_path)
            return future.result()
        except ModelError as exc:
            logger.exception("load_system failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("load_system unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def get_atom_info(self, payload: Dict[str, object]):
        """Return atom metadata for a serial.

        Parameters
        ----------
        payload
            Payload containing atom serial.

        Returns
        -------
        dict
            Atom metadata payload.
        """

        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        serial = payload.get("serial")
        if serial is None:
            return error_result("invalid_input", "serial is required")
        try:
            logger.debug("get_atom_info serial=%s", serial)
            return self._model.get_atom_info(serial)
        except ModelError as exc:
            logger.exception("get_atom_info failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_atom_info unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def get_atom_bundle(self, payload: Dict[str, object]):
        """Return atom metadata plus parm7 highlights.

        Parameters
        ----------
        payload
            Payload containing atom serial.

        Returns
        -------
        dict
            Atom bundle payload.
        """

        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        serial = payload.get("serial")
        if serial is None:
            return error_result("invalid_input", "serial is required")
        try:
            logger.debug("get_atom_bundle serial=%s", serial)
            return self._model.get_atom_bundle(serial)
        except ModelError as exc:
            logger.exception("get_atom_bundle failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_atom_bundle unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def query_atoms(self, payload: Dict[str, object]):
        """Query atoms by filter criteria.

        Parameters
        ----------
        payload
            Payload containing query filters.

        Returns
        -------
        dict
            Query response payload.
        """

        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        filters = payload.get("filters", {})
        try:
            logger.debug("query_atoms filters=%s", filters)
            future = self._worker.submit(self._model.query_atoms, filters)
            return future.result()
        except ModelError as exc:
            logger.exception("query_atoms failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("query_atoms unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def get_residue_info(self, payload: Dict[str, object]):
        """Return residue metadata for a residue id.

        Parameters
        ----------
        payload
            Payload containing residue id.

        Returns
        -------
        dict
            Residue metadata payload.
        """

        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        resid = payload.get("resid")
        if resid is None:
            return error_result("invalid_input", "resid is required")
        try:
            logger.debug("get_residue_info resid=%s", resid)
            return self._model.get_residue_info(resid)
        except ModelError as exc:
            logger.exception("get_residue_info failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_residue_info unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def get_parm7_text(self, payload: Optional[Dict[str, object]] = None):
        """Return base64-encoded parm7 text.

        Parameters
        ----------
        payload
            Unused payload placeholder.

        Returns
        -------
        dict
            Payload containing parm7 text.
        """

        try:
            logger.debug("get_parm7_text requested")
            return self._model.get_parm7_text()
        except ModelError as exc:
            logger.exception("get_parm7_text failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_parm7_text unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def get_parm7_sections(self, payload: Optional[Dict[str, object]] = None):
        """Return parm7 section metadata.

        Parameters
        ----------
        payload
            Unused payload placeholder.

        Returns
        -------
        dict
            Payload containing parm7 sections.
        """

        try:
            logger.debug("get_parm7_sections requested")
            return self._model.get_parm7_sections()
        except ModelError as exc:
            logger.exception("get_parm7_sections failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_parm7_sections unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def get_system_info(self, payload: Optional[Dict[str, object]] = None):
        """Return system info tables for the Info panel.

        Parameters
        ----------
        payload
            Unused payload placeholder.

        Returns
        -------
        dict
            Payload containing system info tables.
        """

        try:
            logger.debug("get_system_info requested")
            return self._model.get_system_info()
        except ModelError as exc:
            logger.exception("get_system_info failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_system_info unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def save_system_info_csv(self, payload: Dict[str, object]):
        """Save a CSV payload to disk via a save dialog.

        Parameters
        ----------
        payload
            Payload containing csv_text and optional name.

        Returns
        -------
        dict
            Save response payload.
        """

        if not self._window:
            return error_result("no_window", "Window is not available")
        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        csv_text = payload.get("csv_text")
        name = payload.get("name") or "topview-system-info.csv"
        if csv_text is None:
            return error_result("invalid_input", "csv_text is required")
        if not isinstance(name, str):
            name = str(name)
        if not name.lower().endswith(".csv"):
            name = f"{name}.csv"
        try:
            logger.debug("save_system_info_csv requested")
            selection = self._window.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=name,
                file_types=("CSV (*.csv)", "All files (*.*)"),
            )
            if not selection:
                return error_result("cancelled", "Save cancelled")
            path = selection[0] if isinstance(selection, (list, tuple)) else selection
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(str(csv_text))
            return {"ok": True, "path": path}
        except Exception as exc:
            logger.exception("save_system_info_csv failed")
            return error_result("save_failed", "Failed to save CSV", str(exc))

    def get_parm7_highlights(self, payload: Dict[str, object]):
        """Return parm7 highlight spans.

        Parameters
        ----------
        payload
            Payload containing serials and mode.

        Returns
        -------
        dict
            Payload containing highlights and interactions.
        """

        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        serials = payload.get("serials")
        serial = payload.get("serial")
        mode = payload.get("mode")
        if serials is None:
            if serial is None:
                return error_result("invalid_input", "serial or serials is required")
            serials = [serial]
        if not isinstance(serials, (list, tuple)):
            return error_result("invalid_input", "serials must be a list")
        try:
            logger.debug("get_parm7_highlights serials=%s mode=%s", serials, mode)
            return self._model.get_parm7_highlights(serials, mode=mode)
        except ModelError as exc:
            logger.exception("get_parm7_highlights failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_parm7_highlights unexpected error")
            return error_result("unexpected", "Unexpected error", str(exc))

    def select_files(self, payload: Optional[Dict[str, object]] = None):
        """Open native file dialog for parm7/rst7 selection.

        Parameters
        ----------
        payload
            Unused payload placeholder.

        Returns
        -------
        dict
            Dialog response payload.
        """

        if not self._window:
            return error_result("no_window", "Window is not available")
        try:
            logger.debug("select_files dialog opened")
            parm7 = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Parm7 (*.parm7 *.prmtop)", "All files (*.*)"),
            )
            if not parm7:
                logger.debug("select_files cancelled at parm7")
                return error_result("cancelled", "No parm7 file selected")
            rst7 = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Rst7 (*.rst7 *.rst *.inpcrd)", "All files (*.*)"),
            )
            if not rst7:
                logger.debug("select_files cancelled at rst7")
                return error_result("cancelled", "No rst7 file selected")
            return {
                "ok": True,
                "parm7_path": parm7[0],
                "rst7_path": rst7[0],
            }
        except Exception as exc:
            logger.exception("select_files failed")
            return error_result("dialog_failed", "File dialog failed", str(exc))

    def log_client_error(self, payload: Dict[str, object]):
        """Log a frontend error into the Python logs.

        Parameters
        ----------
        payload
            Payload containing the error message.

        Returns
        -------
        dict
            Acknowledgement payload.
        """

        if not isinstance(payload, dict):
            return error_result("invalid_input", "payload must be an object")
        message = payload.get("message")
        if not message:
            return error_result("invalid_input", "message is required")
        logger.error("Client error: %s", message)
        return {"ok": True}
