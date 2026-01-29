import {
  DEFAULT_SELECTION_MODE,
  MAX_ATOM_CACHE,
} from "./constants.js";
import { getAtomBundle, getAtomInfo } from "./bridge.js";
import { state } from "./state.js";
import {
  bondDistance,
  areBonded,
  findBondPath,
  highlightSerials,
  renderInteractionLabels,
  resizeViewer,
  clearViewerHighlights,
} from "./viewer.js";
import {
  applyParm7SelectionHighlights,
  fetchParm7Highlights,
  renderParm7File,
} from "./parm7.js";
import { updateSystemInfoHighlight } from "./system_info.js";
import {
  renderSelectionSummary,
  setSelectionMode,
  setStatus,
  reportError,
  updateAboutPanel,
} from "./ui.js";

const SOURCE_VIEWER = "viewer";
const SOURCE_SYSTEM_INFO = "system_info";

function renderSelectionSummaryAndResize() {
  renderSelectionSummary();
  resizeViewer(false);
}

function normalizeSerials(serials) {
  const list = Array.isArray(serials)
    ? serials
    : serials
      ? [serials]
      : [];
  return list.map((value) => Number(value)).filter(Number.isFinite);
}

function isImproperSelection(serials) {
  if (!Array.isArray(serials) || serials.length !== 4) {
    return false;
  }
  const [central, ...others] = serials;
  if (!central || new Set(serials).size !== 4) {
    return false;
  }
  return others.every((serial) => areBonded(central, serial));
}

function bumpSelectionNonce() {
  state.selectionNonce = (state.selectionNonce || 0) + 1;
  return state.selectionNonce;
}

function isSelectionCurrent(nonce) {
  return nonce === state.selectionNonce;
}

function beginSelection(serials, mode, source) {
  const cleanSerials = normalizeSerials(serials);
  if (!cleanSerials.length) {
    return null;
  }
  const nonce = bumpSelectionNonce();
  state.selectionSource = source || SOURCE_VIEWER;
  state.selectionSerials = cleanSerials;
  setSelectionMode(mode || DEFAULT_SELECTION_MODE);
  state.currentAtomInfo = null;
  state.currentInteraction = null;
  renderSelectionSummaryAndResize();
  updateAboutPanel(null);
  highlightSerials(cleanSerials);
  updateSystemInfoHighlight(state.selectionMode, null, null);
  return nonce;
}

function applyAtomDetails(nonce, atom, highlights) {
  if (!isSelectionCurrent(nonce) || !atom) {
    return;
  }
  state.currentAtomInfo = atom;
  renderSelectionSummaryAndResize();
  updateAboutPanel(atom);
  const selection = state.selectionSerials.length ? state.selectionSerials : [atom.serial];
  highlightSerials(selection);
  updateSystemInfoHighlight(state.selectionMode, null, atom);
  if (selection.length === 1 && highlights && highlights.length) {
    applyParm7SelectionHighlights(state.selectionMode, highlights);
    return;
  }
  fetchParm7Highlights(selection, state.selectionMode)
    .then((result) => {
      if (!isSelectionCurrent(nonce) || !result) {
        return;
      }
      applyParm7SelectionHighlights(state.selectionMode, result.highlights || []);
      renderSelectionSummaryAndResize();
    })
    .catch((err) => {
      reportError(String(err));
    });
}

function applyInteractionDetails(nonce, mode, serials) {
  window.setTimeout(() => {
    if (!isSelectionCurrent(nonce)) {
      return;
    }
    fetchParm7Highlights(serials, mode)
      .then((result) => {
        if (!isSelectionCurrent(nonce) || !result) {
          return;
        }
        applyParm7SelectionHighlights(mode, result.highlights || []);
        state.currentInteraction = result.interaction || null;
        updateSystemInfoHighlight(mode, state.currentInteraction, null);
        renderSelectionSummaryAndResize();
        if (state.currentInteraction) {
          renderInteractionLabels(state.currentInteraction);
        }
      })
      .catch((err) => {
        reportError(String(err));
      });
  }, 0);
}

function computeViewerSelection(serial) {
  if (!serial) {
    return null;
  }
  const prevSerials = state.selectionSerials.slice();
  const prevSource = state.selectionSource || SOURCE_VIEWER;
  if (prevSource !== SOURCE_VIEWER) {
    return { serials: [serial], mode: DEFAULT_SELECTION_MODE };
  }
  if (!prevSerials.length || prevSerials.includes(serial)) {
    return { serials: [serial], mode: DEFAULT_SELECTION_MODE };
  }

  let nextSelection = prevSerials.concat(serial);
  if (nextSelection.length > 4) {
    nextSelection = nextSelection.slice(-4);
  }

  if (nextSelection.length === 4) {
    if (isImproperSelection(nextSelection)) {
      return { serials: nextSelection, mode: "Improper" };
    }
    const path = findBondPath(nextSelection);
    if (path) {
      return { serials: path, mode: "Dihedral" };
    }
  }

  if (nextSelection.length === 3) {
    const path = findBondPath(nextSelection);
    if (path) {
      return { serials: path, mode: "Angle" };
    }
  }

  if (nextSelection.length >= 2) {
    const lastTwo = nextSelection.slice(-2);
    if (areBonded(lastTwo[0], lastTwo[1])) {
      return { serials: lastTwo, mode: "Bond" };
    }
    const distance = bondDistance(lastTwo[0], lastTwo[1], 3);
    if (distance === 3) {
      return { serials: lastTwo, mode: "1-4 Nonbonded" };
    }
    if (distance === 2) {
      return null;
    }
    return { serials: lastTwo, mode: "Non-bonded" };
  }

  return { serials: [serial], mode: DEFAULT_SELECTION_MODE };
}

function runAtomSelection(serial, nonce) {
  if (!serial) {
    return;
  }
  const cached = state.atomCache.get(serial);
  if (cached) {
    applyAtomDetails(nonce, cached.atom, cached.highlights);
    if (isSelectionCurrent(nonce)) {
      setStatus("success", `Selected atom ${serial} (cached)`);
    }
    return;
  }
  setStatus("loading", `Loading atom ${serial}...`);
  const selectStart = performance.now();
  window.setTimeout(() => {
    if (!isSelectionCurrent(nonce)) {
      return;
    }
    getAtomBundle(serial)
      .then((result) => {
        if (!result || !result.ok) {
          const msg = result && result.error ? result.error.message : "Unknown error";
          reportError(msg);
          return;
        }
        console.debug(
          `get_atom_bundle completed in ${(performance.now() - selectStart).toFixed(1)}ms`
        );
        cacheAtom(serial, { atom: result.atom, highlights: result.highlights || [] });
        if (!isSelectionCurrent(nonce)) {
          return;
        }
        applyAtomDetails(nonce, result.atom, result.highlights || []);
        setStatus("success", `Selected atom ${serial}`);
      })
      .catch(() => {
        getAtomInfo(serial)
          .then((fallback) => {
            if (!fallback || !fallback.ok) {
              const msg =
                fallback && fallback.error ? fallback.error.message : "Unknown error";
              reportError(msg);
              return;
            }
            console.debug(
              `get_atom_info completed in ${(performance.now() - selectStart).toFixed(1)}ms`
            );
            cacheAtom(serial, { atom: fallback.atom, highlights: null });
            if (!isSelectionCurrent(nonce)) {
              return;
            }
            applyAtomDetails(nonce, fallback.atom, null);
            setStatus("success", `Selected atom ${serial}`);
          })
          .catch((err) => {
            reportError(String(err));
          });
      });
  }, 0);
}

/**
 * Cache atom bundle payloads (LRU).
 * @param {number} serial
 * @param {object} payload
 */
export function cacheAtom(serial, payload) {
  if (!serial) {
    return;
  }
  if (state.atomCache.has(serial)) {
    state.atomCache.delete(serial);
  }
  state.atomCache.set(serial, payload);
  if (state.atomCache.size > MAX_ATOM_CACHE) {
    const firstKey = state.atomCache.keys().next().value;
    if (firstKey !== undefined) {
      state.atomCache.delete(firstKey);
    }
  }
}

/**
 * Reset selection state and summary UI.
 */
export function resetSelectionState() {
  bumpSelectionNonce();
  state.selectionSource = SOURCE_VIEWER;
  state.selectionSerials = [];
  state.currentAtomInfo = null;
  state.currentInteraction = null;
  setSelectionMode(DEFAULT_SELECTION_MODE);
  updateSystemInfoHighlight(state.selectionMode, null, null);
  renderSelectionSummaryAndResize();
  updateAboutPanel(null);
}

/**
 * Clear selection, viewer highlights, and parm7 highlights.
 */
export function clearSelection() {
  bumpSelectionNonce();
  clearViewerHighlights();
  state.selectionSource = SOURCE_VIEWER;
  state.currentAtomInfo = null;
  state.currentInteraction = null;
  state.selectionSerials = [];
  setSelectionMode(DEFAULT_SELECTION_MODE);
  updateSystemInfoHighlight(state.selectionMode, null, null);
  renderSelectionSummaryAndResize();
  updateAboutPanel(null);
  renderParm7File([]);
}

/**
 * Select an atom by serial and update UI.
 * @param {number} serial
 */
export function selectAtom(serial) {
  if (state.loading) {
    return;
  }
  const next = computeViewerSelection(serial);
  if (!next) {
    return;
  }
  state.lastAtomClick = true;
  const nonce = beginSelection(next.serials, next.mode, SOURCE_VIEWER);
  if (!nonce) {
    return;
  }
  if (next.mode === "Atom") {
    runAtomSelection(next.serials[0], nonce);
    return;
  }
  applyInteractionDetails(nonce, next.mode, next.serials);
}

/**
 * Apply selection returned from the system info tables.
 * @param {string} mode
 * @param {Array<number>} serials
 */
export function applySelectionFromSystemInfo(mode, serials) {
  if (state.loading) {
    return;
  }
  const cleanSerials = normalizeSerials(serials);
  if (!cleanSerials.length) {
    return;
  }
  state.lastAtomClick = false;
  const nonce = beginSelection(cleanSerials, mode, SOURCE_SYSTEM_INFO);
  if (!nonce) {
    return;
  }
  if (mode === "Atom") {
    runAtomSelection(cleanSerials[0], nonce);
    return;
  }
  applyInteractionDetails(nonce, mode, cleanSerials);
}
