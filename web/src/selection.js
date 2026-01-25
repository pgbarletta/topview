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
  renderParm7File,
  autoSelectParm7Section,
  updateParm7Highlights,
} from "./parm7.js";
import { updateSystemInfoHighlight } from "./system_info.js";
import {
  renderSelectionSummary,
  setSelectionMode,
  setStatus,
  reportError,
  updateAboutPanel,
} from "./ui.js";

function renderSelectionSummaryAndResize() {
  renderSelectionSummary();
  resizeViewer(false);
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
 * Update selection state based on the clicked serial.
 * @param {number} serial
 */
export function updateSelectionState(serial) {
  if (!serial) {
    return false;
  }
  const prevSelection = state.selectionSerials.slice();
  const prevMode = state.selectionMode;
  const prevInteraction = state.currentInteraction;
  state.currentInteraction = null;
  if (!state.selectionSerials.length || state.selectionSerials.includes(serial)) {
    state.selectionSerials = [serial];
    setSelectionMode(DEFAULT_SELECTION_MODE);
    return true;
  }

  let nextSelection = state.selectionSerials.concat(serial);
  if (nextSelection.length > 4) {
    nextSelection = nextSelection.slice(-4);
  }

  if (nextSelection.length === 4) {
    const path = findBondPath(nextSelection);
    if (path) {
      state.selectionSerials = path;
      setSelectionMode("Dihedral");
      return true;
    }
  }

  if (nextSelection.length === 3) {
    const path = findBondPath(nextSelection);
    if (path) {
      state.selectionSerials = path;
      setSelectionMode("Angle");
      return true;
    }
  }

  if (nextSelection.length >= 2) {
    const lastTwo = nextSelection.slice(-2);
    state.selectionSerials = lastTwo;
    if (areBonded(lastTwo[0], lastTwo[1])) {
      setSelectionMode("Bond");
    } else {
      const distance = bondDistance(lastTwo[0], lastTwo[1], 3);
      if (distance === 2) {
        state.selectionSerials = prevSelection;
        setSelectionMode(prevMode);
        state.currentInteraction = prevInteraction;
        return false;
      }
      if (distance === 3) {
        setSelectionMode("1-4 Nonbonded");
      } else {
        setSelectionMode("Non-bonded");
      }
    }
    return true;
  }

  state.selectionSerials = [serial];
  setSelectionMode(DEFAULT_SELECTION_MODE);
  return true;
}

/**
 * Reset selection state and summary UI.
 */
export function resetSelectionState() {
  state.selectionSerials = [];
  setSelectionMode(DEFAULT_SELECTION_MODE);
  updateSystemInfoHighlight(state.selectionMode, null, null);
  renderSelectionSummaryAndResize();
}

/**
 * Clear selection, viewer highlights, and parm7 highlights.
 */
export function clearSelection() {
  clearViewerHighlights();
  state.currentAtomInfo = null;
  state.currentInteraction = null;
  state.selectionSerials = [];
  setSelectionMode(DEFAULT_SELECTION_MODE);
  updateSystemInfoHighlight(state.selectionMode, null, null);
  renderSelectionSummaryAndResize();
  updateAboutPanel(state.currentAtomInfo);
  renderParm7File([]);
}

function applyAtomSelection(atom, highlights) {
  if (!atom) {
    return;
  }
  state.currentAtomInfo = atom;
  renderSelectionSummaryAndResize();
  updateAboutPanel(atom);
  const selection = state.selectionSerials.length ? state.selectionSerials : [atom.serial];
  highlightSerials(selection);
  updateSystemInfoHighlight(state.selectionMode, null, atom);
  if (selection.length === 1 && highlights) {
    autoSelectParm7Section(state.selectionMode, highlights);
    renderParm7File(highlights);
    return;
  }
  updateParm7Highlights(selection, state.selectionMode)
    .then((interaction) => {
      state.currentInteraction = interaction || null;
      updateSystemInfoHighlight(
        state.selectionMode,
        state.currentInteraction,
        state.currentAtomInfo
      );
      renderSelectionSummaryAndResize();
      if (state.currentInteraction) {
        renderInteractionLabels(state.currentInteraction);
      }
    })
    .catch((err) => {
      reportError(String(err));
    });
}

/**
 * Select an atom by serial and update UI.
 * @param {number} serial
 */
export function selectAtom(serial) {
  if (state.loading) {
    return;
  }
  state.lastAtomClick = true;
  const selectionUpdated = updateSelectionState(serial);
  if (!selectionUpdated) {
    return;
  }
  renderSelectionSummaryAndResize();
  const selection = state.selectionSerials.length ? state.selectionSerials : [serial];
  highlightSerials(selection);
  const cached = state.atomCache.get(serial);
  if (cached) {
    applyAtomSelection(cached.atom, cached.highlights);
    setStatus("success", `Selected atom ${serial} (cached)`);
    return;
  }
  setStatus("loading", `Loading atom ${serial}...`);
  const selectStart = performance.now();
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
      applyAtomSelection(result.atom, result.highlights || []);
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
          applyAtomSelection(fallback.atom, null);
          setStatus("success", `Selected atom ${serial}`);
        })
        .catch((err) => {
          reportError(String(err));
        });
    });
}
