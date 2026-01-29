import {
  HIGHLIGHT_ATOM_OPACITY,
  HIGHLIGHT_COLOR,
  HIGHLIGHT_LINE_OPACITY,
  STYLE_PRESETS,
} from "./constants.js";
import { state } from "./state.js";
import { decodeBase64, formatNumber, midpoint, centroid } from "./utils.js";
import { setStatus } from "./ui.js";

const ATOM_HIGHLIGHT_CLASS = "tv-atom-highlight";
const BOND_HIGHLIGHT_CLASS = "tv-bond-highlight";
const ATOM_HIT_CLASS = "tv-atom-hit";
const SVG_NS = "http://www.w3.org/2000/svg";
const EMPTY_CLICK_MOVE_PX = 6;
const EMPTY_CLICK_MOVE_PX_SQ = EMPTY_CLICK_MOVE_PX * EMPTY_CLICK_MOVE_PX;
const EMPTY_CLICK_HOLD_MS = 200;

/**
 * Schedule a single viewer render on the next animation frame.
 */
export function requestRender() {
  if (state.viewMode !== "3d" || !state.viewer || state.renderScheduled) {
    if (state.viewMode === "3d" && state.viewer && state.renderScheduled) {
      state.renderPending = true;
    }
    return;
  }
  state.renderScheduled = true;
  window.requestAnimationFrame(() => {
    state.renderScheduled = false;
    if (state.viewer) {
      state.viewer.render();
    }
    if (state.renderPending) {
      state.renderPending = false;
      requestRender();
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
  if (state.viewMode === "3d" && state.viewer && typeof state.viewer.setBackgroundColor === "function") {
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

function get2dOverlay() {
  return state.rdkitOverlayNode || document.getElementById("viewer-2d-overlay");
}

function clear2dLabels() {
  const overlay = get2dOverlay();
  if (!overlay) {
    return;
  }
  overlay.innerHTML = "";
  state.viewerLabelNodes = [];
}

function toOverlayCoords(position) {
  const svg = state.rdkitSvgNode;
  const overlay = get2dOverlay();
  if (!svg || !overlay || !position) {
    return null;
  }
  const ctm = svg.getScreenCTM();
  if (!ctm || typeof svg.createSVGPoint !== "function") {
    return null;
  }
  const point = svg.createSVGPoint();
  point.x = position.x;
  point.y = position.y;
  const screen = point.matrixTransform(ctm);
  const rect = overlay.getBoundingClientRect();
  return { x: screen.x - rect.left, y: screen.y - rect.top };
}

function add2dLabel(text, position) {
  const overlay = get2dOverlay();
  if (!overlay || !text || !position) {
    return;
  }
  const coords = toOverlayCoords(position);
  if (!coords) {
    return;
  }
  const label = document.createElement("div");
  label.className = "viewer-2d-label";
  label.textContent = text;
  label.style.left = `${coords.x}px`;
  label.style.top = `${coords.y}px`;
  overlay.appendChild(label);
  state.viewerLabelNodes.push(label);
}

function add2dLabelLines(lines, position) {
  const overlay = get2dOverlay();
  if (!overlay || !lines || !lines.length || !position) {
    return;
  }
  const coords = toOverlayCoords(position);
  if (!coords) {
    return;
  }
  const label = document.createElement("div");
  label.className = "viewer-2d-label multiline";
  label.textContent = lines.join("\n");
  label.style.left = `${coords.x}px`;
  label.style.top = `${coords.y}px`;
  overlay.appendChild(label);
  state.viewerLabelNodes.push(label);
}

function addViewerLabel(text, position) {
  if (!text || !position) {
    return;
  }
  if (state.viewMode === "2d") {
    add2dLabel(text, position);
    return;
  }
  if (!state.viewer) {
    return;
  }
  const style = getLabelStyle();
  const fontSize = getLabelFontSize();
  state.viewer.addLabel(text, { position: position, fontSize, ...style });
}

function addViewerLabelLines(lines, position) {
  if (!lines || !lines.length || !position) {
    return;
  }
  if (state.viewMode === "2d") {
    add2dLabelLines(lines, position);
    return;
  }
  if (!state.viewer) {
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
  if (state.viewMode === "2d") {
    const atoms = state.modelAtoms || [];
    state.modelAtoms = atoms;
  } else {
    state.modelAtoms = [];
    if (!state.model) {
      return;
    }
    const atoms = state.model.selectedAtoms({});
    state.modelAtoms = atoms || [];
  }
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
    state.viewer = $3Dmol.createViewer(document.getElementById("viewer-3d"), {
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
  const container = document.getElementById("viewer-3d");
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
  if (state.viewMode === "2d") {
    refresh2dLabels();
    return;
  }
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
  if (state.viewMode !== "3d" || !state.viewer) {
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
  state.currentStyleKey = key;
  if (state.viewMode !== "3d" || !state.viewer) {
    return;
  }
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

function setViewMode(mode) {
  state.viewMode = mode;
  const container = document.getElementById("viewer");
  if (container) {
    container.classList.toggle("viewer-2d", mode === "2d");
  }
}

function reset2dState() {
  if (state.rdkitSvgNode && state.rdkitClickHandler) {
    state.rdkitSvgNode.removeEventListener("click", state.rdkitClickHandler);
  }
  state.rdkitSvgNode = null;
  state.rdkitOverlayNode = null;
  state.rdkitAtomSerials = [];
  state.rdkitAtomIndexBySerial = new Map();
  state.rdkitAtomCoords = [];
  state.rdkitAtomNames = [];
  state.rdkitBondPairs = [];
  state.rdkitBondIndexByPair = new Map();
  state.rdkitClickHandler = null;
  clear2dLabels();
  state.modelAtoms = [];
  const svgContainer = document.getElementById("viewer-2d-svg");
  if (svgContainer) {
    svgContainer.innerHTML = "";
  }
}

function getBondKey(serialA, serialB) {
  const a = Number(serialA);
  const b = Number(serialB);
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    return "";
  }
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

function getRdkitAtomIndex(serial) {
  return state.rdkitAtomIndexBySerial.get(Number(serial));
}

function apply2dAtomHighlight(serial) {
  const atomIdx = getRdkitAtomIndex(serial);
  const svg = state.rdkitSvgNode;
  if (atomIdx === undefined || atomIdx === null || !svg) {
    return;
  }
  svg.querySelectorAll(`.atom-${atomIdx}`).forEach((node) => {
    if (node.classList && node.classList.contains(ATOM_HIT_CLASS)) {
      return;
    }
    node.classList.add(ATOM_HIGHLIGHT_CLASS);
  });
}

function apply2dBondHighlight(serialA, serialB) {
  const svg = state.rdkitSvgNode;
  if (!svg) {
    return;
  }
  const key = getBondKey(serialA, serialB);
  const bondIndex = state.rdkitBondIndexByPair.get(key);
  if (bondIndex === undefined) {
    return;
  }
  svg.querySelectorAll(`.bond-${bondIndex}`).forEach((node) => {
    node.classList.add(BOND_HIGHLIGHT_CLASS);
  });
}

function clear2dHighlights() {
  const svg = state.rdkitSvgNode;
  if (svg) {
    svg.querySelectorAll(`.${ATOM_HIGHLIGHT_CLASS}`).forEach((node) => {
      node.classList.remove(ATOM_HIGHLIGHT_CLASS);
    });
    svg.querySelectorAll(`.${BOND_HIGHLIGHT_CLASS}`).forEach((node) => {
      node.classList.remove(BOND_HIGHLIGHT_CLASS);
    });
  }
  clear2dLabels();
  state.currentSelection = [];
}

function highlightSerials2d(serials) {
  const selection = serials || [];
  clear2dHighlights();
  const smallSelection = selection.length > 0 && selection.length <= 4;
  if (smallSelection) {
    if (state.selectionMode === "Atom") {
      selection.forEach((serial) => {
        const atom = state.atomBySerial.get(serial);
        if (atom) {
          add2dLabel(atomLabelText(serial, atom), atomPosition(atom));
        }
      });
    }
    selection.forEach((serial) => {
      apply2dAtomHighlight(serial);
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
        apply2dBondHighlight(serialA, serialB);
      }
    }
  }
  state.currentSelection = selection;
}

function refresh2dLabels() {
  clear2dLabels();
  const selection = state.selectionSerials || [];
  if (!selection.length) {
    return;
  }
  if (state.selectionMode === "Atom") {
    selection.forEach((serial) => {
      const atom = state.atomBySerial.get(serial);
      if (atom) {
        add2dLabel(atomLabelText(serial, atom), atomPosition(atom));
      }
    });
    return;
  }
  if (state.currentInteraction) {
    renderInteractionLabels(state.currentInteraction);
  }
}

/**
 * Clear viewer labels and shapes.
 */
export function clearViewerHighlights() {
  if (state.viewMode === "2d") {
    clear2dHighlights();
    return;
  }
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
  if (state.viewMode === "2d") {
    highlightSerials2d(serials);
    return;
  }
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
  if (!atomRecord) {
    return `#${serial}`;
  }
  const label = atomRecord.atom || atomRecord.atom_name || atomRecord.name || "";
  return label ? `#${serial} ${label}` : `#${serial}`;
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
  if (!interaction) {
    return;
  }
  if (state.viewMode === "3d" && !state.viewer) {
    return;
  }
  if (state.viewMode === "2d" && !state.rdkitSvgNode) {
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

function get2dHitRadius(depiction) {
  const width = Number(depiction && depiction.width);
  const height = Number(depiction && depiction.height);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return 12;
  }
  const base = Math.min(width, height);
  const scaled = Math.round(base * 0.025);
  return Math.max(12, Math.min(20, scaled));
}

function add2dHitTargets(svg, atomCoords, depiction) {
  if (!svg || !Array.isArray(atomCoords) || !atomCoords.length) {
    return;
  }
  const radius = get2dHitRadius(depiction);
  const hitLayer = document.createElementNS(SVG_NS, "g");
  hitLayer.setAttribute("class", "tv-atom-hit-layer");
  atomCoords.forEach((coord, idx) => {
    if (!coord || !Number.isFinite(coord.x) || !Number.isFinite(coord.y)) {
      return;
    }
    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("class", `atom-${idx} ${ATOM_HIT_CLASS}`);
    circle.setAttribute("cx", String(coord.x));
    circle.setAttribute("cy", String(coord.y));
    circle.setAttribute("r", String(radius));
    hitLayer.appendChild(circle);
  });
  svg.appendChild(hitLayer);
}

function getAtomIndexFromTarget(target) {
  let node = target;
  while (node && node !== state.rdkitSvgNode) {
    if (node.classList) {
      for (const cls of node.classList) {
        if (cls.startsWith("atom-")) {
          const idx = Number(cls.slice(5));
          if (!Number.isNaN(idx)) {
            return idx;
          }
        }
      }
    }
    node = node.parentNode;
  }
  return null;
}

function attach2dClickHandler(onAtomClick) {
  const svg = state.rdkitSvgNode;
  if (!svg || !onAtomClick) {
    return;
  }
  if (state.rdkitClickHandler) {
    svg.removeEventListener("click", state.rdkitClickHandler);
  }
  const handler = (event) => {
    const atomIdx = getAtomIndexFromTarget(event.target);
    if (atomIdx === null) {
      if (state.lastAtomClick) {
        state.lastAtomClick = false;
      }
      return;
    }
    const serial = state.rdkitAtomSerials[atomIdx];
    if (serial) {
      onAtomClick(serial);
    }
  };
  svg.addEventListener("click", handler);
  state.rdkitClickHandler = handler;
}

function attachEmptySelectionHandler(container, onEmptyClick, stateKey, is2d) {
  if (!container || typeof onEmptyClick !== "function") {
    return;
  }
  if (state[stateKey]) {
    return;
  }
  let press = null;

  const handlePointerDown = (event) => {
    if (event.button !== 0) {
      return;
    }
    state.lastAtomClick = false;
    const atomTarget = is2d ? getAtomIndexFromTarget(event.target) : null;
    press = {
      x: event.clientX,
      y: event.clientY,
      time: performance.now(),
      moved: false,
      atomTarget: atomTarget !== null,
    };
  };

  const handlePointerMove = (event) => {
    if (!press || press.moved) {
      return;
    }
    const dx = event.clientX - press.x;
    const dy = event.clientY - press.y;
    if (dx * dx + dy * dy > EMPTY_CLICK_MOVE_PX_SQ) {
      press.moved = true;
    }
  };

  const handlePointerUp = () => {
    if (!press) {
      return;
    }
    const { moved, time, atomTarget } = press;
    press = null;
    const elapsed = performance.now() - time;
    if (moved || elapsed >= EMPTY_CLICK_HOLD_MS) {
      return;
    }
    window.setTimeout(() => {
      if (atomTarget || state.lastAtomClick) {
        state.lastAtomClick = false;
        return;
      }
      onEmptyClick();
    }, 0);
  };

  const handlePointerCancel = () => {
    press = null;
  };

  container.addEventListener("pointerdown", handlePointerDown, true);
  container.addEventListener("pointermove", handlePointerMove, true);
  container.addEventListener("pointerup", handlePointerUp, true);
  container.addEventListener("pointercancel", handlePointerCancel, true);
  state[stateKey] = true;
}

/**
 * Render a 2D RDKit depiction into the viewer.
 * @param {object} depiction
 * @param {(serial:number)=>void} onAtomClick
 * @param {() => void} onEmptyClick
 */
export function render2dModel(depiction, onAtomClick, onEmptyClick) {
  if (!depiction || !depiction.svg) {
    setStatus("error", "2D depiction not available.", "RDKit depiction missing.");
    return false;
  }
  setViewMode("2d");
  reset2dState();
  if (state.viewer && typeof state.viewer.clear === "function") {
    state.viewer.clear();
  }
  state.model = null;
  const svgContainer = document.getElementById("viewer-2d-svg");
  const overlay = document.getElementById("viewer-2d-overlay");
  if (!svgContainer || !overlay) {
    setStatus("error", "Viewer unavailable.", "2D container missing.");
    return false;
  }
  svgContainer.innerHTML = depiction.svg;
  const svg = svgContainer.querySelector("svg");
  if (!svg) {
    setStatus("error", "2D depiction failed.", "SVG not found.");
    return false;
  }
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", "100%");
  state.rdkitSvgNode = svg;
  state.rdkitOverlayNode = overlay;

  const atomSerials = (depiction.atom_serials || []).map((value) => Number(value));
  const atomCoords = depiction.atom_coords || [];
  const atomNames = depiction.atom_names || [];
  state.rdkitAtomSerials = atomSerials;
  state.rdkitAtomCoords = atomCoords;
  state.rdkitAtomNames = atomNames;
  add2dHitTargets(svg, atomCoords, depiction);
  state.rdkitAtomIndexBySerial = new Map();
  state.modelAtoms = [];
  atomSerials.forEach((serial, idx) => {
    state.rdkitAtomIndexBySerial.set(serial, idx);
    const coord = atomCoords[idx] || { x: 0, y: 0 };
    const name = atomNames[idx] || "";
    state.modelAtoms.push({
      serial: serial,
      index: idx,
      x: coord.x,
      y: coord.y,
      z: 0,
      atom: name,
      bonds: [],
    });
  });

  state.rdkitBondPairs = depiction.bond_pairs || [];
  state.rdkitBondIndexByPair = new Map();
  state.rdkitBondPairs.forEach((bond) => {
    const atomA = state.modelAtoms[bond.a];
    const atomB = state.modelAtoms[bond.b];
    if (!atomA || !atomB) {
      return;
    }
    atomA.bonds.push(bond.b);
    atomB.bonds.push(bond.a);
    const key = getBondKey(atomA.serial, atomB.serial);
    if (key) {
      state.rdkitBondIndexByPair.set(key, bond.bond_index);
    }
  });

  buildAtomIndex();
  attach2dClickHandler(onAtomClick);
  attachEmptySelectionHandler(
    document.getElementById("viewer-2d"),
    onEmptyClick,
    "emptyClickArmed2d",
    true
  );
  resizeViewer(false);
  return true;
}

/**
 * Render the PDB model into the viewer.
 * @param {string} pdbB64
 * @param {(serial:number)=>void} onAtomClick
 * @param {() => void} onEmptyClick
 */
export function renderModel(pdbB64, onAtomClick, onEmptyClick) {
  setViewMode("3d");
  reset2dState();
  if (!state.viewer) {
    return;
  }
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
  attachEmptySelectionHandler(
    document.getElementById("viewer-3d"),
    onEmptyClick,
    "emptyClickArmed",
    false
  );
  state.viewer.zoomTo();
  resizeViewer(false);
  requestRender();
}
