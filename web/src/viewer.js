import {
  HIGHLIGHT_ATOM_OPACITY,
  HIGHLIGHT_COLOR,
  HIGHLIGHT_LINE_OPACITY,
  STYLE_PRESETS,
} from "./constants.js";
import { state } from "./state.js";
import { decodeBase64, formatNumber, midpoint, centroid } from "./utils.js";
import { setStatus } from "./ui.js";

/**
 * Schedule a single viewer render on the next animation frame.
 */
export function requestRender() {
  if (!state.viewer || state.renderScheduled) {
    return;
  }
  state.renderScheduled = true;
  window.requestAnimationFrame(() => {
    state.renderScheduled = false;
    if (state.viewer) {
      state.viewer.render();
    }
  });
}

function getViewerBackgroundColor() {
  const root = document.body || document.documentElement;
  const value = getComputedStyle(root)
    .getPropertyValue("--viewer-bg")
    .trim();
  return value || "#ffffff";
}

function getLabelStyle() {
  const root = document.body || document.documentElement;
  const styles = getComputedStyle(root);
  const backgroundColor = styles.getPropertyValue("--label-bg").trim() || "#fef3c7";
  const fontColor = styles.getPropertyValue("--label-text").trim() || "#111827";
  return { backgroundColor, fontColor };
}

function parseCssSize(value, fallback) {
  const raw = (value || "").trim();
  if (!raw) {
    return fallback;
  }
  const num = parseFloat(raw);
  if (Number.isNaN(num) || num <= 0) {
    return fallback;
  }
  if (raw.endsWith("pt")) {
    return num * (4 / 3);
  }
  return num;
}

function getLabelFontSize() {
  const root = document.body || document.documentElement;
  const styles = getComputedStyle(root);
  return parseCssSize(styles.getPropertyValue("--viewer-label-font-size"), 13);
}

/**
 * Apply light/dark theme to viewer and DOM.
 * @param {boolean} isDark
 */
export function applyTheme(isDark) {
  state.darkMode = Boolean(isDark);
  document.body.classList.toggle("dark-mode", state.darkMode);
  const themeBtn = document.getElementById("theme-btn");
  if (themeBtn) {
    themeBtn.textContent = state.darkMode ? "Light mode" : "Dark mode";
  }
  if (state.viewer && typeof state.viewer.setBackgroundColor === "function") {
    state.viewer.setBackgroundColor(getViewerBackgroundColor());
    requestRender();
  }
}

function getHighlightAtomRadius() {
  if (state.currentStyleKey === "spheres") {
    return 0.9;
  }
  if (state.currentStyleKey === "ballstick") {
    return 0.7;
  }
  return 0.55;
}

function getHighlightBondRadius() {
  if (state.currentStyleKey === "lines") {
    return 0.2;
  }
  if (state.currentStyleKey === "spheres") {
    return 0.3;
  }
  return 0.32;
}

function addHighlightSphere(center, radius) {
  if (!state.viewer || !center) {
    return;
  }
  if (typeof state.viewer.addSphere === "function") {
    state.viewer.addSphere({
      center: center,
      radius: radius,
      color: HIGHLIGHT_COLOR,
      opacity: HIGHLIGHT_ATOM_OPACITY,
    });
    return;
  }
  if (typeof state.viewer.addShape === "function") {
    const shape = state.viewer.addShape({
      color: HIGHLIGHT_COLOR,
      opacity: HIGHLIGHT_ATOM_OPACITY,
    });
    if (shape && typeof shape.addSphere === "function") {
      shape.addSphere({ center: center, radius: radius });
    }
  }
}

function addHighlightCylinder(start, end, radius) {
  if (!state.viewer || !start || !end) {
    return;
  }
  if (typeof state.viewer.addCylinder === "function") {
    state.viewer.addCylinder({
      start: start,
      end: end,
      radius: radius,
      color: HIGHLIGHT_COLOR,
      opacity: HIGHLIGHT_LINE_OPACITY,
    });
    return;
  }
  if (typeof state.viewer.addShape === "function") {
    const shape = state.viewer.addShape({
      color: HIGHLIGHT_COLOR,
      opacity: HIGHLIGHT_LINE_OPACITY,
    });
    if (shape && typeof shape.addCylinder === "function") {
      shape.addCylinder({ start: start, end: end, radius: radius });
    }
  }
}

function atomPosition(atom) {
  if (!atom) {
    return null;
  }
  return { x: atom.x, y: atom.y, z: atom.z };
}

function addViewerLabel(text, position) {
  if (!state.viewer || !text || !position) {
    return;
  }
  const style = getLabelStyle();
  const fontSize = getLabelFontSize();
  state.viewer.addLabel(text, { position: position, fontSize, ...style });
}

function addViewerLabelLines(lines, position) {
  if (!state.viewer || !lines || !lines.length || !position) {
    return;
  }
  const fontSize = getLabelFontSize();
  const lineHeight = Math.max(18, Math.round(fontSize * 1.5 + 6));
  const style = { ...getLabelStyle(), fontSize };
  const offsetBase = -((lines.length - 1) * lineHeight) / 2;
  lines.forEach((line, idx) => {
    if (!line) {
      return;
    }
    const offsetY = offsetBase + idx * lineHeight;
    state.viewer.addLabel(line, {
      position: position,
      screenOffset: { x: 0, y: offsetY },
      ...style,
    });
  });
}

/**
 * Build lookup tables for the active model.
 */
export function buildAtomIndex() {
  state.atomBySerial = new Map();
  state.atomIndexBySerial = new Map();
  state.atomByIndex = new Map();
  state.modelAtoms = [];
  if (!state.model) {
    return;
  }
  const atoms = state.model.selectedAtoms({});
  state.modelAtoms = atoms || [];
  state.modelAtoms.forEach((atom, idx) => {
    if (!atom || !atom.serial) {
      return;
    }
    state.atomBySerial.set(atom.serial, atom);
    const atomIndex = atom.index !== undefined ? atom.index : idx;
    state.atomIndexBySerial.set(atom.serial, atomIndex);
    state.atomByIndex.set(atomIndex, atom);
  });
}

/**
 * Check whether two atoms are bonded.
 * @param {number} serialA
 * @param {number} serialB
 * @returns {boolean}
 */
export function areBonded(serialA, serialB) {
  if (!serialA || !serialB) {
    return false;
  }
  const atomA = state.atomBySerial.get(serialA);
  const indexB = state.atomIndexBySerial.get(serialB);
  if (!atomA || indexB === undefined || !atomA.bonds) {
    return false;
  }
  return atomA.bonds.includes(indexB);
}

/**
 * Find a bonded path ordering for serials.
 * @param {Array<number>} serials
 * @returns {Array<number>|null}
 */
export function findBondPath(serials) {
  if (!serials || serials.length < 2) {
    return null;
  }
  const unique = Array.from(new Set(serials));
  if (unique.length !== serials.length) {
    return null;
  }
  const adj = buildAdjacency(unique);
  const degree = new Map();
  unique.forEach((serial) => {
    degree.set(serial, (adj.get(serial) || []).length);
  });
  let startCandidates = unique.filter((serial) => degree.get(serial) === 1);
  if (!startCandidates.length) {
    startCandidates = unique.slice();
  }

  const visited = new Set();
  const dfs = (current, path) => {
    if (path.length === unique.length) {
      return path;
    }
    const neighbors = adj.get(current) || [];
    for (const next of neighbors) {
      if (visited.has(next)) {
        continue;
      }
      visited.add(next);
      path.push(next);
      const result = dfs(next, path);
      if (result) {
        return result;
      }
      path.pop();
      visited.delete(next);
    }
    return null;
  };

  for (const start of startCandidates) {
    visited.clear();
    visited.add(start);
    const result = dfs(start, [start]);
    if (result) {
      return result;
    }
  }
  return null;
}

/**
 * Compute bond distance up to a maximum number of hops.
 * @param {number} serialA
 * @param {number} serialB
 * @param {number=} maxDepth
 * @returns {number|null}
 */
export function bondDistance(serialA, serialB, maxDepth = 3) {
  if (!serialA || !serialB) {
    return null;
  }
  const startIdx = state.atomIndexBySerial.get(serialA);
  const targetIdx = state.atomIndexBySerial.get(serialB);
  if (startIdx === undefined || targetIdx === undefined) {
    return null;
  }
  if (startIdx === targetIdx) {
    return 0;
  }
  const visited = new Set([startIdx]);
  const queue = [{ idx: startIdx, depth: 0 }];
  while (queue.length) {
    const current = queue.shift();
    if (!current) {
      continue;
    }
    const { idx, depth } = current;
    if (depth >= maxDepth) {
      continue;
    }
    const atom = state.atomByIndex.get(idx);
    if (!atom || !atom.bonds) {
      continue;
    }
    for (const neighborIdx of atom.bonds) {
      if (neighborIdx === targetIdx) {
        return depth + 1;
      }
      if (!visited.has(neighborIdx)) {
        visited.add(neighborIdx);
        queue.push({ idx: neighborIdx, depth: depth + 1 });
      }
    }
  }
  return null;
}

function buildAdjacency(serials) {
  const adj = new Map();
  serials.forEach((serial) => {
    adj.set(serial, []);
  });
  for (let i = 0; i < serials.length; i += 1) {
    for (let j = i + 1; j < serials.length; j += 1) {
      const a = serials[i];
      const b = serials[j];
      if (areBonded(a, b)) {
        adj.get(a).push(b);
        adj.get(b).push(a);
      }
    }
  }
  return adj;
}

/**
 * Load the 3Dmol viewer script (local vendor bundle).
 * @returns {Promise<boolean>}
 */
export function load3Dmol() {
  if (window.$3Dmol) {
    return Promise.resolve(true);
  }
  if (state.threeDmolPromise) {
    return state.threeDmolPromise;
  }
  state.threeDmolPromise = new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "vendor/3Dmol-min.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });
  return state.threeDmolPromise;
}

/**
 * Ensure the 3D viewer exists.
 * @returns {Promise<any|null>}
 */
export async function ensureViewer() {
  const ok = await load3Dmol();
  if (!ok || !window.$3Dmol) {
    setStatus("error", "3Dmol.js not loaded.", "Copy web/vendor/3Dmol-min.js.");
    return null;
  }
  if (!state.viewer) {
    state.viewer = $3Dmol.createViewer(document.getElementById("viewer"), {
      backgroundColor: getViewerBackgroundColor(),
    });
    resizeViewer();
  }
  attachZoomHandler();
  return state.viewer;
}

function attachZoomHandler() {
  if (state.zoomHandlerAttached || !state.viewer) {
    return;
  }
  const container = document.getElementById("viewer");
  if (!container) {
    return;
  }
  container.addEventListener(
    "wheel",
    (event) => {
      if (!state.viewer) {
        return;
      }
      const delta = event.deltaY || -event.wheelDelta || 0;
      if (!delta) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const zoomStep = 1.1;
      const zoomIn = delta < 0;
      const factor = zoomIn ? zoomStep : 1 / zoomStep;
      state.viewer.zoom(factor);
      requestRender();
    },
    { passive: false, capture: true }
  );
  state.zoomHandlerAttached = true;
}

/**
 * Resize the viewer on layout changes.
 * @param {boolean=} renderNow
 */
export function resizeViewer(renderNow = true) {
  if (state.viewer && typeof state.viewer.resize === "function") {
    state.viewer.resize();
    if (renderNow) {
      requestRender();
    }
  }
}

/**
 * Apply base style to the viewer.
 */
export function applyBaseStyle() {
  if (!state.viewer) {
    return;
  }
  if (state.currentStyleKey === "cartoon_ligand") {
    state.viewer.setStyle({ protein: true }, STYLE_PRESETS.cartoon_ligand.protein);
    state.viewer.setStyle({ not: { protein: true } }, STYLE_PRESETS.cartoon_ligand.other);
    return;
  }
  if (!state.baseStyle) {
    state.baseStyle = STYLE_PRESETS.sticks;
  }
  state.viewer.setStyle({}, state.baseStyle);
}

/**
 * Apply a style preset key.
 * @param {string} key
 * @param {boolean=} renderNow
 */
export function applyStylePreset(key, renderNow = true) {
  if (!state.viewer) {
    return;
  }
  state.currentStyleKey = key;
  if (key === "cartoon_ligand") {
    state.viewer.setStyle({ protein: true }, STYLE_PRESETS.cartoon_ligand.protein);
    state.viewer.setStyle({ not: { protein: true } }, STYLE_PRESETS.cartoon_ligand.other);
  } else {
    state.baseStyle = STYLE_PRESETS[key] || STYLE_PRESETS.sticks;
    state.viewer.setStyle({}, state.baseStyle);
  }
  if (renderNow) {
    requestRender();
  }
}

/**
 * Clear viewer labels and shapes.
 */
export function clearViewerHighlights() {
  if (!state.viewer) {
    return;
  }
  state.viewer.removeAllLabels();
  if (typeof state.viewer.removeAllShapes === "function") {
    state.viewer.removeAllShapes();
  }
  requestRender();
  state.currentSelection = [];
}

/**
 * Highlight selected serials in the viewer.
 * @param {Array<number>} serials
 */
export function highlightSerials(serials) {
  if (!state.viewer) {
    return;
  }
  state.viewer.removeAllLabels();
  if (typeof state.viewer.removeAllShapes === "function") {
    state.viewer.removeAllShapes();
  }
  const selection = serials || [];
  const smallSelection = selection.length > 0 && selection.length <= 4;
  if (smallSelection) {
    if (state.selectionMode === "Atom") {
      const labelStyle = getLabelStyle();
      selection.forEach((serial) => {
        const atoms = state.model ? state.model.selectedAtoms({ serial: serial }) : [];
        if (atoms && atoms.length) {
          state.viewer.addLabel(atomLabelText(serial, atoms[0]), {
            position: atoms[0],
            backgroundColor: labelStyle.backgroundColor,
            fontColor: labelStyle.fontColor,
          });
        }
      });
    }
    const radius = getHighlightAtomRadius();
    const bondRadius = getHighlightBondRadius();
    selection.forEach((serial) => {
      const atom = state.atomBySerial.get(serial);
      const center = atomPosition(atom);
      if (center) {
        addHighlightSphere(center, radius);
      }
    });
    const drawLines =
      state.selectionMode === "Bond" ||
      state.selectionMode === "Angle" ||
      state.selectionMode === "Dihedral";
    if (drawLines) {
      for (let idx = 0; idx < selection.length - 1; idx += 1) {
        const serialA = selection[idx];
        const serialB = selection[idx + 1];
        if (!areBonded(serialA, serialB)) {
          continue;
        }
        const atomA = state.atomBySerial.get(serialA);
        const atomB = state.atomBySerial.get(serialB);
        const start = atomPosition(atomA);
        const end = atomPosition(atomB);
        if (start && end) {
          addHighlightCylinder(start, end, bondRadius);
        }
      }
    }
  }
  requestRender();
  state.currentSelection = selection;
}

function atomLabelText(serial, atomRecord) {
  const base = atomRecord ? `#${serial} ${atomRecord.atom}` : `#${serial}`;
  return base;
}

function buildBondLabels(bonds) {
  const labels = [];
  (bonds || []).forEach((bond) => {
    const serials = bond.serials || [];
    if (serials.length < 2) {
      return;
    }
    const posA = atomPosition(state.atomBySerial.get(serials[0]));
    const posB = atomPosition(state.atomBySerial.get(serials[1]));
    const position = midpoint(posA, posB);
    const k = formatNumber(bond.force_constant);
    const req = formatNumber(bond.equil_value);
    const parts = [];
    if (k !== null) parts.push(`k=${k}`);
    if (req !== null) parts.push(`r0=${req}`);
    if (!parts.length) {
      return;
    }
    labels.push({ text: parts.join(", "), position });
  });
  return labels;
}

function buildAngleLabels(angles) {
  const labels = [];
  (angles || []).forEach((angle) => {
    const serials = angle.serials || [];
    if (serials.length < 3) {
      return;
    }
    const center = atomPosition(state.atomBySerial.get(serials[1]));
    const position = center || centroid(serials.map((s) => atomPosition(state.atomBySerial.get(s))));
    const k = formatNumber(angle.force_constant);
    const theta = formatNumber(angle.equil_value);
    const parts = [];
    if (k !== null) parts.push(`k=${k}`);
    if (theta !== null) parts.push(`theta0=${theta}`);
    if (!parts.length) {
      return;
    }
    labels.push({ text: parts.join(", "), position });
  });
  return labels;
}

function buildDihedralIndexLabel(serials) {
  if (!serials || serials.length < 4) {
    return null;
  }
  const posB = atomPosition(state.atomBySerial.get(serials[1]));
  const posC = atomPosition(state.atomBySerial.get(serials[2]));
  const position =
    midpoint(posB, posC) || centroid(serials.map((s) => atomPosition(state.atomBySerial.get(s))));
  const text = `Dihedral ${serials.join("-")}`;
  return { text, position };
}

function getDihedralLabelSerials(interaction) {
  if (interaction && Array.isArray(interaction.dihedrals) && interaction.dihedrals.length) {
    const serials = interaction.dihedrals[0].serials || [];
    if (serials.length >= 4) {
      return serials.slice(0, 4);
    }
  }
  return state.selectionSerials;
}

function buildNonbondedLabels(nonbonded) {
  if (!nonbonded) {
    return [];
  }
  const serials = nonbonded.serials || [];
  if (serials.length < 2) {
    return [];
  }
  const posA = atomPosition(state.atomBySerial.get(serials[0]));
  const posB = atomPosition(state.atomBySerial.get(serials[1]));
  const position = midpoint(posA, posB);
  const lines = [];
  const rmin = formatNumber(nonbonded.rmin);
  const eps = formatNumber(nonbonded.epsilon);
  if (rmin !== null || eps !== null) {
    const parts = [];
    if (rmin !== null) parts.push(`Rmin=${rmin}`);
    if (eps !== null) parts.push(`eps=${eps}`);
    lines.push(parts.join(", "));
  }
  const acoef = formatNumber(nonbonded.acoef);
  const bcoef = formatNumber(nonbonded.bcoef);
  if (acoef !== null || bcoef !== null) {
    const parts = [];
    if (acoef !== null) parts.push(`A=${acoef}`);
    if (bcoef !== null) parts.push(`B=${bcoef}`);
    lines.push(parts.join(", "));
  }
  if (!lines.length) {
    return [];
  }
  return [{ lines: lines, position }];
}

function formatFixed(value, digits) {
  if (value === null || value === undefined) {
    return null;
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return null;
  }
  return num.toFixed(digits);
}

function buildOneFourNonbondedLabel(oneFour, nonbonded) {
  if ((!oneFour || !oneFour.length) && !nonbonded) {
    return [];
  }
  const serials =
    (oneFour && oneFour.length ? oneFour[0].serials : null) ||
    (nonbonded ? nonbonded.serials : null) ||
    [];
  let position = null;
  if (serials.length >= 2) {
    const posA = atomPosition(state.atomBySerial.get(serials[0]));
    const posB = atomPosition(state.atomBySerial.get(serials[1]));
    position = midpoint(posA, posB);
  }
  const lines = [];
  if (nonbonded) {
    const acoef = formatNumber(nonbonded.acoef);
    const bcoef = formatNumber(nonbonded.bcoef);
    const parts = [];
    if (acoef !== null) parts.push(`A=${acoef}`);
    if (bcoef !== null) parts.push(`B=${bcoef}`);
    if (parts.length) {
      lines.push(parts.join(", "));
    }
  }
  if (oneFour && oneFour.length) {
    const multi = oneFour.length > 1;
    oneFour.forEach((term, idx) => {
      const parts = [];
      if (multi) {
        parts.push(`term ${idx + 1}`);
      }
      const scee = formatFixed(term.scee, 1);
      const scnb = formatFixed(term.scnb, 1);
      if (scee !== null) parts.push(`SCEE=${scee}`);
      if (scnb !== null) parts.push(`SCNB=${scnb}`);
      if (parts.length) {
        lines.push(parts.join(" "));
      }
    });
  }
  if (!lines.length) {
    return [];
  }
  return [{ lines: lines, position }];
}

/**
 * Render interaction labels in the viewer.
 * @param {object} interaction
 */
export function renderInteractionLabels(interaction) {
  if (!interaction || !state.viewer) {
    return;
  }
  const labels = [];
  if (interaction.mode === "Bond") {
    labels.push(...buildBondLabels(interaction.bonds));
  } else if (interaction.mode === "Angle") {
    labels.push(...buildAngleLabels(interaction.angles));
  } else if (interaction.mode === "Dihedral") {
    const label = buildDihedralIndexLabel(getDihedralLabelSerials(interaction));
    if (label) {
      labels.push(label);
    }
  } else if (interaction.mode === "1-4 Nonbonded") {
    labels.push(...buildOneFourNonbondedLabel(interaction.one_four, interaction.nonbonded));
  } else if (interaction.mode === "Non-bonded") {
    labels.push(...buildNonbondedLabels(interaction.nonbonded));
  }
  labels.forEach((label) => {
    if (label.lines) {
      addViewerLabelLines(label.lines, label.position);
    } else if (label.text) {
      addViewerLabel(label.text, label.position);
    }
  });
  requestRender();
}

/**
 * Render the PDB model into the viewer.
 * @param {string} pdbB64
 * @param {(serial:number)=>void} onAtomClick
 */
export function renderModel(pdbB64, onAtomClick) {
  const pdb = decodeBase64(pdbB64);
  state.viewer.clear();
  state.model = state.viewer.addModel(pdb, "pdb");
  state.model.setClickable({}, true, function (atom) {
    if (!atom || !atom.serial) {
      return;
    }
    onAtomClick(atom.serial);
  });
  buildAtomIndex();
  attachEmptyClickHandler();
  state.viewer.zoomTo();
  resizeViewer(false);
  requestRender();
}

function attachEmptyClickHandler() {
  if (state.emptyClickArmed) {
    return;
  }
  const container = document.getElementById("viewer");
  if (!container) {
    return;
  }
  container.addEventListener(
    "click",
    () => {
      if (state.lastAtomClick) {
        state.lastAtomClick = false;
      }
    },
    true
  );
  state.emptyClickArmed = true;
}
