/**
 * Access the pywebview API bridge.
 * @returns {object|null}
 */
export function getApi() {
  if (!window.pywebview || !window.pywebview.api) {
    return null;
  }
  return window.pywebview.api;
}

/**
 * Check if a pywebview API method is available.
 * @param {string} name
 * @returns {boolean}
 */
export function hasApiMethod(name) {
  const api = getApi();
  return Boolean(api && typeof api[name] === "function");
}

/**
 * Call a pywebview API method.
 * @param {string} name
 * @param {object=} payload
 * @returns {Promise<any>}
 */
export function callApi(name, payload) {
  const api = getApi();
  if (!api || typeof api[name] !== "function") {
    return Promise.reject(new Error(`pywebview API '${name}' not available`));
  }
  return api[name](payload);
}

/** @returns {Promise<any>} */
export function getUiConfig() {
  return callApi("get_ui_config");
}

/** @returns {Promise<any>} */
export function getInitialPaths() {
  return callApi("get_initial_paths");
}

/**
 * @param {string} parm7Path
 * @param {string=} rst7Path
 * @param {string=} resname
 * @returns {Promise<any>}
 */
export function loadSystem(parm7Path, rst7Path, resname) {
  const payload = { parm7_path: parm7Path };
  if (rst7Path) {
    payload.rst7_path = rst7Path;
  }
  if (resname) {
    payload.resname = resname;
  }
  return callApi("load_system", payload);
}

/** @returns {Promise<any>} */
export function getParm7Text() {
  return callApi("get_parm7_text");
}

/** @returns {Promise<any>} */
export function getParm7Sections() {
  return callApi("get_parm7_sections");
}

/** @returns {Promise<any>} */
export function getSystemInfo() {
  return callApi("get_system_info");
}

/**
 * @param {string} table
 * @param {number} rowIndex
 * @param {number} cursor
 * @returns {Promise<any>}
 */
export function getSystemInfoSelection(table, rowIndex, cursor) {
  return callApi("get_system_info_selection", {
    table: table,
    row_index: rowIndex,
    cursor: cursor,
  });
}

/**
 * @param {string} csvText
 * @param {string} name
 * @returns {Promise<any>}
 */
export function saveSystemInfoCsv(csvText, name) {
  return callApi("save_system_info_csv", { csv_text: csvText, name: name });
}

/**
 * @param {number} serial
 * @returns {Promise<any>}
 */
export function getAtomBundle(serial) {
  return callApi("get_atom_bundle", { serial: serial });
}

/**
 * @param {number} serial
 * @returns {Promise<any>}
 */
export function getAtomInfo(serial) {
  return callApi("get_atom_info", { serial: serial });
}

/**
 * @param {Array<number>} serials
 * @param {string} mode
 * @returns {Promise<any>}
 */
export function getParm7Highlights(serials, mode) {
  return callApi("get_parm7_highlights", { serials: serials, mode: mode });
}

/**
 * @param {object} filters
 * @returns {Promise<any>}
 */
export function queryAtoms(filters) {
  return callApi("query_atoms", { filters: filters });
}

/** @returns {Promise<any>} */
export function selectFiles() {
  return callApi("select_files");
}

/**
 * @param {string} message
 * @returns {Promise<any>}
 */
export function logClientError(message) {
  return callApi("log_client_error", { message: message });
}
