import logging

import webview

from model import Model, ModelError
from worker import Worker

logger = logging.getLogger(__name__)


def _error(code: str, message: str, details=None):
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


class Api:
    def __init__(
        self, model: Model, worker: Worker, initial_paths=None, ui_config=None
    ) -> None:
        self._model = model
        self._worker = worker
        self._window = None
        self._initial_paths = initial_paths
        self._ui_config = ui_config or {}

    def set_window(self, window) -> None:
        self._window = window

    def get_initial_paths(self, payload=None):
        if not self._initial_paths:
            return {"ok": True, "parm7_path": None, "rst7_path": None}
        parm7_path, rst7_path = self._initial_paths
        self._initial_paths = None
        logger.debug("get_initial_paths returned paths")
        return {"ok": True, "parm7_path": parm7_path, "rst7_path": rst7_path}

    def get_ui_config(self, payload=None):
        return {"ok": True, "config": self._ui_config}

    def load_system(self, payload):
        if not isinstance(payload, dict):
            return _error("invalid_input", "payload must be an object")
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
            return _error("unexpected", "Unexpected error", str(exc))

    def get_atom_info(self, payload):
        if not isinstance(payload, dict):
            return _error("invalid_input", "payload must be an object")
        serial = payload.get("serial")
        if serial is None:
            return _error("invalid_input", "serial is required")
        try:
            logger.debug("get_atom_info serial=%s", serial)
            return self._model.get_atom_info(serial)
        except ModelError as exc:
            logger.exception("get_atom_info failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_atom_info unexpected error")
            return _error("unexpected", "Unexpected error", str(exc))

    def get_atom_bundle(self, payload):
        if not isinstance(payload, dict):
            return _error("invalid_input", "payload must be an object")
        serial = payload.get("serial")
        if serial is None:
            return _error("invalid_input", "serial is required")
        try:
            logger.debug("get_atom_bundle serial=%s", serial)
            return self._model.get_atom_bundle(serial)
        except ModelError as exc:
            logger.exception("get_atom_bundle failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_atom_bundle unexpected error")
            return _error("unexpected", "Unexpected error", str(exc))

    def query_atoms(self, payload):
        if not isinstance(payload, dict):
            return _error("invalid_input", "payload must be an object")
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
            return _error("unexpected", "Unexpected error", str(exc))

    def get_residue_info(self, payload):
        if not isinstance(payload, dict):
            return _error("invalid_input", "payload must be an object")
        resid = payload.get("resid")
        if resid is None:
            return _error("invalid_input", "resid is required")
        try:
            logger.debug("get_residue_info resid=%s", resid)
            return self._model.get_residue_info(resid)
        except ModelError as exc:
            logger.exception("get_residue_info failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_residue_info unexpected error")
            return _error("unexpected", "Unexpected error", str(exc))

    def get_parm7_text(self, payload=None):
        try:
            logger.debug("get_parm7_text requested")
            return self._model.get_parm7_text()
        except ModelError as exc:
            logger.exception("get_parm7_text failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_parm7_text unexpected error")
            return _error("unexpected", "Unexpected error", str(exc))

    def get_parm7_sections(self, payload=None):
        try:
            logger.debug("get_parm7_sections requested")
            return self._model.get_parm7_sections()
        except ModelError as exc:
            logger.exception("get_parm7_sections failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_parm7_sections unexpected error")
            return _error("unexpected", "Unexpected error", str(exc))

    def get_parm7_highlights(self, payload):
        if not isinstance(payload, dict):
            return _error("invalid_input", "payload must be an object")
        serials = payload.get("serials")
        serial = payload.get("serial")
        mode = payload.get("mode")
        if serials is None:
            if serial is None:
                return _error("invalid_input", "serial or serials is required")
            serials = [serial]
        if not isinstance(serials, (list, tuple)):
            return _error("invalid_input", "serials must be a list")
        try:
            logger.debug("get_parm7_highlights serials=%s mode=%s", serials, mode)
            return self._model.get_parm7_highlights(serials, mode=mode)
        except ModelError as exc:
            logger.exception("get_parm7_highlights failed")
            return exc.to_result()
        except Exception as exc:
            logger.exception("get_parm7_highlights unexpected error")
            return _error("unexpected", "Unexpected error", str(exc))

    def select_files(self, payload=None):
        if not self._window:
            return _error("no_window", "Window is not available")
        try:
            logger.debug("select_files dialog opened")
            parm7 = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Parm7 (*.parm7 *.prmtop)", "All files (*.*)"),
            )
            if not parm7:
                logger.debug("select_files cancelled at parm7")
                return _error("cancelled", "No parm7 file selected")
            rst7 = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Rst7 (*.rst7 *.rst *.inpcrd)", "All files (*.*)"),
            )
            if not rst7:
                logger.debug("select_files cancelled at rst7")
                return _error("cancelled", "No rst7 file selected")
            return {
                "ok": True,
                "parm7_path": parm7[0],
                "rst7_path": rst7[0],
            }
        except Exception as exc:
            logger.exception("select_files failed")
            return _error("dialog_failed", "File dialog failed", str(exc))

    def log_client_error(self, payload):
        if not isinstance(payload, dict):
            return _error("invalid_input", "payload must be an object")
        message = payload.get("message")
        if not message:
            return _error("invalid_input", "message is required")
        logger.error("Client error: %s", message)
        return {"ok": True}
