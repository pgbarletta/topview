import { getSystemInfo, getSystemInfoSelection, saveSystemInfoCsv } from "./bridge.js";
import { DEFAULT_SELECTION_MODE, INFO_FONT_MAX, INFO_FONT_MIN } from "./constants.js";
import { applySelectionFromSystemInfo } from "./selection.js";
import { state } from "./state.js";
import { escapeHtml, formatNumber } from "./utils.js";
import { reportError, setStatus } from "./ui.js";

const INFO_TABS = [
  { id: "Atom", label: "Atom", key: "atom_types" },
  { id: "Bond", label: "Bond", key: "bond_types" },
  { id: "Angle", label: "Angle", key: "angle_types" },
  { id: "Dihedral", label: "Dihedral", key: "dihedral_types" },
  { id: "Improper", label: "Improper", key: "improper_types" },
  { id: "1-4 Nonbonded", label: "1-4 Nonbonded", key: "one_four_nonbonded" },
  { id: "Non-bonded", label: "Non-bonded", key: "nonbonded_pairs" },
];
const HIGHLIGHT_COLORS = {
  Atom: "var(--mode-atom-bg)",
  Bond: "var(--mode-bond-bg)",
  Angle: "var(--mode-angle-bg)",
  Dihedral: "var(--mode-dihedral-bg)",
  Improper: "var(--mode-dihedral-bg)",
  "1-4 Nonbonded": "var(--mode-14-bg)",
  "Non-bonded": "var(--mode-nonbonded-bg)",
};
const SORTABLE_COLUMNS = {
  atom_types: [
    "type_index",
    "atom_count",
    "pair_index",
    "acoef",
    "bcoef",
    "rmin",
    "epsilon",
  ],
  bond_types: [
    "type_a",
    "type_b",
    "param_index",
    "force_constant",
    "equil_value",
    "count",
  ],
  angle_types: [
    "type_i",
    "type_j",
    "type_k",
    "param_index",
    "force_constant",
    "equil_value",
    "count",
  ],
  dihedral_types: [
    "ID",
    "idx",
    "ijkl indices",
    "rotatable",
    "k",
    "pdcty",
    "phase",
    "scee",
    "scnb",
  ],
  improper_types: [
    "ID",
    "idx",
    "ijkl indices",
    "force_constant",
    "periodicity",
    "phase",
    "scee",
    "scnb",
  ],
  one_four_nonbonded: [
    "type_a",
    "type_b",
    "param_index",
    "scee",
    "scnb",
    "pair_index",
    "acoef",
    "bcoef",
    "rmin",
    "epsilon",
    "count",
  ],
  nonbonded_pairs: [
    "type_a",
    "type_b",
    "pair_index",
    "acoef",
    "bcoef",
    "rmin",
    "epsilon",
  ],
};

/**
 * Initialize the system info tabs.
 */
export function attachSystemInfoTabs() {
  const tabs = document.getElementById("system-info-tabs");
  if (!tabs) {
    return;
  }
  tabs.innerHTML = "";
  INFO_TABS.forEach((tab) => {
    const button = document.createElement("button");
    button.className = "system-info-tab";
    button.type = "button";
    button.dataset.tab = tab.id;
    button.textContent = tab.label;
    button.addEventListener("click", () => {
      state.systemInfoTab = tab.id;
      renderSystemInfo();
    });
    tabs.appendChild(button);
  });
  updateTabState();
}

/**
 * Initialize the system info export button.
 */
export function attachSystemInfoExport() {
  const button = document.getElementById("system-info-export");
  if (!button) {
    return;
  }
  if (button.dataset.bound === "true") {
    return;
  }
  button.dataset.bound = "true";
  button.addEventListener("click", () => {
    exportSystemInfoCsv();
  });
}

/**
 * Initialize delegated click handling for system info row selection.
 */
export function attachSystemInfoRowActions() {
  const content = document.getElementById("system-info-content");
  if (!content) {
    return;
  }
  if (content.dataset.bound === "true") {
    return;
  }
  content.dataset.bound = "true";
  content.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const sortButton = target.closest(".system-info-sort");
    if (sortButton && sortButton instanceof HTMLButtonElement) {
      const tableKey = sortButton.dataset.table;
      const column = sortButton.dataset.col;
      if (tableKey && column) {
        toggleSort(tableKey, column);
      }
      return;
    }
    const button = target.closest(".system-info-select");
    if (!button || !(button instanceof HTMLButtonElement)) {
      return;
    }
    const tableKey = button.dataset.table;
    const rowIndex = Number(button.dataset.rowIndex);
    if (!tableKey || !Number.isFinite(rowIndex) || rowIndex < 0) {
      return;
    }
    handleSystemInfoSelection(button, tableKey, rowIndex);
  });
}

/**
 * Update the info font size.
 * @param {number|string} value
 */
export function updateInfoFontSize(value) {
  const size = Number(value);
  if (!size || Number.isNaN(size)) {
    return;
  }
  const clamped = Math.min(INFO_FONT_MAX, Math.max(INFO_FONT_MIN, Math.round(size)));
  document.documentElement.style.setProperty("--info-pop-font-size", `${clamped}pt`);
  const input = document.getElementById("info-font-size");
  if (input && input.value !== String(clamped)) {
    input.value = String(clamped);
  }
}

/**
 * Reset cached system info state.
 */
export function resetSystemInfoState() {
  state.systemInfo = null;
  state.systemInfoVisible = true;
  state.systemInfoTab = DEFAULT_SELECTION_MODE;
  state.systemInfoRowCursor = new Map();
  state.systemInfoSortByTable = new Map();
  const panel = document.getElementById("system-info-panel");
  if (panel) {
    panel.classList.remove("hidden");
  }
  const content = document.getElementById("system-info-content");
  if (content) {
    content.textContent = "No system info loaded.";
  }
  updateTabState();
}

/**
 * Load system info tables and render them.
 */
export async function loadSystemInfo() {
  const panel = document.getElementById("system-info-panel");
  if (!panel) {
    return;
  }
  state.systemInfoVisible = true;
  panel.classList.remove("hidden");
  const loaded = await ensureSystemInfoLoaded();
  if (loaded) {
    renderSystemInfo();
  }
}

async function ensureSystemInfoLoaded() {
  if (state.systemInfo) {
    return true;
  }
  const content = state.systemInfoVisible
    ? document.getElementById("system-info-content")
    : null;
  if (content) {
    content.textContent = "Loading system info...";
  }
  try {
    const result = await getSystemInfo();
    if (!result || !result.ok) {
      const msg = result && result.error ? result.error.message : "Failed to load system info";
      reportError(msg);
      if (content) {
        content.textContent = "Failed to load system info.";
      }
      return false;
    }
    state.systemInfo = result.tables || {};
    if (state.systemInfoVisible) {
      renderSystemInfo();
    }
    return true;
  } catch (err) {
    reportError(String(err));
    if (content) {
      content.textContent = "Failed to load system info.";
    }
    return false;
  }
}

function updateTabState() {
  const tabs = document.querySelectorAll(".system-info-tab");
  tabs.forEach((tab) => {
    if (tab.dataset.tab === state.systemInfoTab) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });
}

function getActiveTab() {
  return INFO_TABS.find((item) => item.id === state.systemInfoTab) || INFO_TABS[0];
}

function getActiveTable() {
  const tab = getActiveTab();
  const tables = state.systemInfo || {};
  return tables[tab.key] || null;
}

function renderSystemInfo() {
  updateTabState();
  const content = document.getElementById("system-info-content");
  if (!content) {
    return;
  }
  const tab = getActiveTab();
  const tables = state.systemInfo || {};
  const table = tables[tab.key] || null;
  if (!table || !table.columns) {
    content.textContent = "No system info loaded.";
    return;
  }
  const highlight = getActiveHighlight(table.columns);
  const rows = table.rows || [];
  const rowsWithIndex = rows.map((row, index) => ({ row, index }));
  const sorted = applySort(tab.key, table.columns, rowsWithIndex);
  content.innerHTML = buildTableHtml(tab.key, table.columns, sorted, highlight);
  requestAnimationFrame(() => {
    scrollHighlightedRow();
  });
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  if (typeof value === "number") {
    if (Number.isInteger(value)) {
      return String(value);
    }
    const formatted = formatNumber(value);
    return formatted === null ? String(value) : formatted;
  }
  return String(value);
}

function getActiveHighlight(columns) {
  const highlight = state.systemInfoHighlight;
  if (!highlight || highlight.tab !== state.systemInfoTab) {
    return null;
  }
  if (highlight.match && typeof highlight.match === "object") {
    const entries = Object.entries(highlight.match).filter(([col]) =>
      columns.includes(col)
    );
    if (!entries.length) {
      return null;
    }
    return { matchEntries: entries };
  }
  if (!highlight.column || highlight.value === undefined || highlight.value === null) {
    return null;
  }
  if (!Array.isArray(columns) || columns.indexOf(highlight.column) === -1) {
    return null;
  }
  return { matchEntries: [[highlight.column, highlight.value]] };
}

function isSortableColumn(tableKey, column) {
  const allowed = SORTABLE_COLUMNS[tableKey] || [];
  return allowed.includes(column);
}

function getTableSort(tableKey) {
  if (!tableKey) {
    return null;
  }
  const store = state.systemInfoSortByTable;
  if (!store) {
    return null;
  }
  return store.get(tableKey) || null;
}

function getSortState(tableKey, column) {
  const sort = getTableSort(tableKey);
  if (!sort || sort.column !== column) {
    return null;
  }
  return sort.direction || null;
}

function toggleSort(tableKey, column) {
  if (!isSortableColumn(tableKey, column)) {
    return;
  }
  const current = getTableSort(tableKey);
  let next = null;
  if (current && current.column === column) {
    if (current.direction === "asc") {
      next = { column, direction: "desc" };
    } else if (current.direction === "desc") {
      next = null;
    } else {
      next = { column, direction: "asc" };
    }
  } else {
    next = { column, direction: "asc" };
  }
  if (!state.systemInfoSortByTable) {
    state.systemInfoSortByTable = new Map();
  }
  if (next) {
    state.systemInfoSortByTable.set(tableKey, next);
  } else {
    state.systemInfoSortByTable.delete(tableKey);
  }
  renderSystemInfo();
}

function parseIJKL(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parts = String(value)
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((num) => Number.isFinite(num));
  if (parts.length < 4) {
    return null;
  }
  return parts.slice(0, 4);
}

function getSortValue(column, row, columns) {
  const idx = columns.indexOf(column);
  if (idx < 0) {
    return null;
  }
  const value = row[idx];
  if (column === "ijkl indices") {
    return parseIJKL(value);
  }
  if (column === "rotatable") {
    if (value === "T") {
      return 1;
    }
    if (value === "F") {
      return 0;
    }
    return null;
  }
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function compareIJKL(a, b) {
  if (!a && !b) {
    return 0;
  }
  if (!a) {
    return 1;
  }
  if (!b) {
    return -1;
  }
  for (let idx = 0; idx < 4; idx += 1) {
    if (a[idx] !== b[idx]) {
      return a[idx] - b[idx];
    }
  }
  return 0;
}

function applySort(tableKey, columns, rowsWithIndex) {
  const sort = getTableSort(tableKey);
  if (!sort || !sort.column || !sort.direction) {
    return rowsWithIndex;
  }
  if (!isSortableColumn(tableKey, sort.column)) {
    return rowsWithIndex;
  }
  const direction = sort.direction === "desc" ? -1 : 1;
  const sorted = rowsWithIndex.slice();
  sorted.sort((aEntry, bEntry) => {
    const aValue = getSortValue(sort.column, aEntry.row, columns);
    const bValue = getSortValue(sort.column, bEntry.row, columns);
    let cmp = 0;
    if (sort.column === "ijkl indices") {
      cmp = compareIJKL(aValue, bValue);
    } else {
      if (aValue === null && bValue === null) {
        cmp = 0;
      } else if (aValue === null) {
        cmp = 1;
      } else if (bValue === null) {
        cmp = -1;
      } else {
        cmp = aValue - bValue;
      }
    }
    if (cmp === 0) {
      cmp = aEntry.index - bEntry.index;
    }
    return cmp * direction;
  });
  return sorted;
}

function buildTableHtml(tableKey, columns, rows, highlight) {
  const hasRows = rows && rows.length;
  const headerHtml = columns
    .map((col) => {
      const sortable = isSortableColumn(tableKey, col);
      if (!sortable) {
        return `<th>${escapeHtml(String(col))}</th>`;
      }
      const state = getSortState(tableKey, col);
      const upClass = state === "asc" ? "sort-arrow active" : "sort-arrow";
      const downClass = state === "desc" ? "sort-arrow active" : "sort-arrow";
      return `<th><button class="system-info-sort" type="button" data-table="${escapeHtml(
        String(tableKey)
      )}" data-col="${escapeHtml(String(col))}"><span class="sort-label">${escapeHtml(
        String(col)
      )}</span><span class="sort-arrows"><span class="${upClass}">▲</span><span class="${downClass}">▼</span></span></button></th>`;
    })
    .join("");
  const matchEntries = highlight && highlight.matchEntries ? highlight.matchEntries : [];
  const matchIndices = matchEntries
    .map(([col, value]) => [columns.indexOf(col), String(value)])
    .filter(([idx]) => idx >= 0);
  const safeRows = hasRows ? rows : [{ row: columns.map(() => null), index: 0 }];
  const bodyHtml = safeRows
    .map((entry) => {
      const row = entry.row;
      const rowIndex = entry.index;
      let rowClass = "";
      if (matchIndices.length && row) {
        const matches = matchIndices.every(([idx, expected]) => {
          const rawValue = row[idx];
          const displayValue = formatCell(rawValue);
          return displayValue === expected;
        });
        if (matches) {
          rowClass = ' class="system-info-row-highlight"';
        }
      }
      const cells = columns
        .map((_, idx) => {
          const value = row && row[idx] !== undefined ? row[idx] : null;
          return `<td>${escapeHtml(formatCell(value))}</td>`;
        })
        .join("");
      const disabled = hasRows ? "" : " disabled";
      const button = `<button class="system-info-select" type="button" data-table="${escapeHtml(
        String(tableKey)
      )}" data-row-index="${rowIndex}"${disabled}>Select</button>`;
      return `<tr${rowClass}><td class="system-info-select-cell">${button}</td>${cells}</tr>`;
    })
    .join("");
  return `<table class="system-info-table"><thead><tr><th>Select</th>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`;
}

function scrollHighlightedRow() {
  const content = document.getElementById("system-info-content");
  if (!content) {
    return;
  }
  const row = content.querySelector("tr.system-info-row-highlight");
  if (!row) {
    return;
  }
  const rowRect = row.getBoundingClientRect();
  const contentRect = content.getBoundingClientRect();
  if (!rowRect.height || !contentRect.height) {
    return;
  }
  const rowTop = rowRect.top - contentRect.top + content.scrollTop;
  const target = rowTop - content.clientHeight / 2 + rowRect.height / 2;
  const maxScroll = Math.max(0, content.scrollHeight - content.clientHeight);
  content.scrollTop = Math.min(maxScroll, Math.max(0, target));
}

/**
 * Update the system info highlight based on selection.
 * @param {string} mode
 * @param {object|null} interaction
 * @param {object|null} atomInfo
 */
export function updateSystemInfoHighlight(mode, interaction, atomInfo = null) {
  state.systemInfoHighlight = null;
  const content = document.getElementById("system-info-content");
  if (content) {
    content.style.removeProperty("--system-info-highlight");
  }
  const tabMatch = INFO_TABS.find((item) => item.id === mode);
  if (tabMatch) {
    state.systemInfoTab = tabMatch.id;
  }
  const setHighlight = (tab, match, colorMode) => {
    state.systemInfoHighlight = { tab, match };
    if (content && colorMode && HIGHLIGHT_COLORS[colorMode]) {
      content.style.setProperty("--system-info-highlight", HIGHLIGHT_COLORS[colorMode]);
    }
  };
  if (mode === "Atom" && atomInfo && atomInfo.parm7 && atomInfo.parm7.atom_type_index) {
    setHighlight("Atom", { type_index: atomInfo.parm7.atom_type_index }, "Atom");
  } else if (mode === "Bond" && interaction && Array.isArray(interaction.bonds)) {
    const bond = interaction.bonds[0];
    const types = bond && bond.type_indices;
    if (bond && types && types.length === 2) {
      const typeA = Number(types[0]);
      const typeB = Number(types[1]);
      if (Number.isFinite(typeA) && Number.isFinite(typeB)) {
        const typeMin = Math.min(typeA, typeB);
        const typeMax = Math.max(typeA, typeB);
        setHighlight(
          "Bond",
          { type_a: typeMin, type_b: typeMax, param_index: bond.param_index },
          "Bond"
        );
      }
    }
  } else if (mode === "Angle" && interaction && Array.isArray(interaction.angles)) {
    const angle = interaction.angles[0];
    const types = angle && angle.type_indices;
    if (angle && types && types.length === 3) {
      let typeI = Number(types[0]);
      const typeJ = Number(types[1]);
      let typeK = Number(types[2]);
      if (Number.isFinite(typeI) && Number.isFinite(typeJ) && Number.isFinite(typeK)) {
        if (typeI > typeK) {
          const tmp = typeI;
          typeI = typeK;
          typeK = tmp;
        }
        setHighlight(
          "Angle",
          {
            type_i: typeI,
            type_j: typeJ,
            type_k: typeK,
            param_index: angle.param_index,
          },
          "Angle"
        );
      }
    }
  } else if (
    mode === "Dihedral" &&
    interaction &&
    Array.isArray(interaction.dihedrals) &&
    interaction.dihedrals.length
  ) {
    const serials = interaction.dihedrals[0].serials || [];
    if (serials.length >= 4) {
      const ijkl = serials.slice(0, 4).map((value) => Number(value)).filter(Number.isFinite);
      if (ijkl.length === 4) {
        setHighlight("Dihedral", { "ijkl indices": ijkl.join(", ") }, "Dihedral");
      }
    }
  } else if (
    mode === "Improper" &&
    interaction &&
    Array.isArray(interaction.dihedrals) &&
    interaction.dihedrals.length
  ) {
    const serials = interaction.dihedrals[0].serials || [];
    if (serials.length >= 4) {
      const ijkl = serials.slice(0, 4).map((value) => Number(value)).filter(Number.isFinite);
      if (ijkl.length === 4) {
        setHighlight("Improper", { "ijkl indices": ijkl.join(", ") }, "Improper");
      }
    }
  } else if (
    mode === "1-4 Nonbonded" &&
    interaction &&
    Array.isArray(interaction.one_four) &&
    interaction.one_four.length
  ) {
    const term = interaction.one_four[0];
    const types = term && term.type_indices;
    if (term && types && types.length === 2) {
      const typeA = Number(types[0]);
      const typeB = Number(types[1]);
      if (Number.isFinite(typeA) && Number.isFinite(typeB)) {
        const typeMin = Math.min(typeA, typeB);
        const typeMax = Math.max(typeA, typeB);
        setHighlight(
          "1-4 Nonbonded",
          { type_a: typeMin, type_b: typeMax, param_index: term.param_index },
          "1-4 Nonbonded"
        );
      }
    }
  } else if (mode === "Non-bonded" && interaction && interaction.nonbonded) {
    const nb = interaction.nonbonded;
    const types = nb.type_indices;
    if (types && types.length === 2) {
      const typeA = Number(types[0]);
      const typeB = Number(types[1]);
      if (Number.isFinite(typeA) && Number.isFinite(typeB)) {
        const typeMin = Math.min(typeA, typeB);
        const typeMax = Math.max(typeA, typeB);
        setHighlight(
          "Non-bonded",
          { type_a: typeMin, type_b: typeMax, pair_index: nb.nb_index },
          "Non-bonded"
        );
      }
    }
  }
  if (state.systemInfo) {
    renderSystemInfo();
  }
}

async function handleSystemInfoSelection(button, tableKey, rowIndex) {
  const cursorKey = `${tableKey}:${rowIndex}`;
  const cursor = state.systemInfoRowCursor.get(cursorKey) || 0;
  button.disabled = true;
  try {
    const result = await getSystemInfoSelection(tableKey, rowIndex, cursor);
    if (!result || !result.ok) {
      const err = result && result.error ? result.error : null;
      if (err && err.code === "not_found") {
        setStatus("error", "No matches for that row");
      } else {
        const msg = err ? err.message : "Selection failed";
        reportError(msg);
      }
      return;
    }
    const serials = Array.isArray(result.serials) ? result.serials : [];
    const total = Number(result.total) || 0;
    const index = Number(result.index) || 0;
    const cleanSerials = serials
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value));
    if (!cleanSerials.length) {
      reportError("No serials returned for selection.");
      return;
    }
    state.systemInfoRowCursor.set(cursorKey, total ? (index + 1) % total : 0);
    applySelectionFromSystemInfo(result.mode, cleanSerials);
    const countLabel = total ? ` (${index + 1}/${total})` : "";
    setStatus("success", `Selected ${result.mode}${countLabel}`);
  } catch (err) {
    reportError(String(err));
  } finally {
    button.disabled = false;
  }
}

async function exportSystemInfoCsv() {
  const loaded = await ensureSystemInfoLoaded();
  if (!loaded) {
    return;
  }
  const tab = getActiveTab();
  const table = getActiveTable();
  if (!table || !table.columns) {
    reportError("No system info data available for export.");
    return;
  }
  const csvText = buildCsvText(table.columns, table.rows || []);
  const filename = `topview-${slugify(tab.id)}.csv`;
  try {
    const result = await saveSystemInfoCsv(csvText, filename);
    if (!result || !result.ok) {
      const msg = result && result.error ? result.error.message : "CSV export failed";
      reportError(msg);
    }
  } catch (err) {
    reportError(String(err));
  }
}

function buildCsvText(columns, rows) {
  const lines = [];
  lines.push(columns.map(csvEscape).join(","));
  if (rows && rows.length) {
    rows.forEach((row) => {
      const cells = columns.map((_, idx) => csvEscape(row ? row[idx] : ""));
      lines.push(cells.join(","));
    });
  }
  return lines.join("\n");
}

function csvEscape(value) {
  let text = value === null || value === undefined ? "" : String(value);
  if (text.includes("\"")) {
    text = text.replace(/\"/g, "\"\"");
  }
  if (/[\",\n]/.test(text)) {
    text = `"${text}"`;
  }
  return text;
}

function slugify(text) {
  return String(text)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
