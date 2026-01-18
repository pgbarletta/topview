let viewer = null;
let model = null;
let baseStyle = null;
let currentSelection = [];
let loading = false;
let currentStyleKey = "sticks";
window.__pywebview_ready = false;
window.__pendingLoad = null;
let threeDmolPromise = null;
let parm7Lines = [];
let parm7Sections = [];
let parm7LineNodes = new Map();
let parm7HighlightsByLine = new Map();
let parm7LinesContainer = null;
let parm7Spacer = null;
let parm7LineHeight = 16;
let parm7Window = { start: 0, end: 0 };
let parm7ScrollAttached = false;
let parm7ScrollScheduled = false;
let parm7ViewIndices = null;
let parm7ViewIndexMap = null;
let sectionTooltip = null;
let zoomHandlerAttached = false;
let currentAtomInfo = null;
let aboutVisible = false;
let darkMode = false;
let eventsAttached = false;
let currentInteraction = null;
const atomCache = new Map();
const MAX_ATOM_CACHE = 2000;
let renderScheduled = false;
let selectionSerials = [];
let selectionMode = "Atom";
let atomBySerial = new Map();
let atomIndexBySerial = new Map();
let atomByIndex = new Map();
let modelAtoms = [];
let emptyClickArmed = false;
let lastAtomClick = false;
const HIGHLIGHT_COLOR = "#111827";
const HIGHLIGHT_ATOM_OPACITY = 0.2;
const HIGHLIGHT_LINE_OPACITY = 0.65;
const SECTION_MODE_MAP = {
  ATOM_NAME: "Atom",
  CHARGE: "Atom",
  ATOMIC_NUMBER: "Atom",
  MASS: "Atom",
  ATOM_TYPE_INDEX: "Atom",
  AMBER_ATOM_TYPE: "Atom",
  BONDS_INC_HYDROGEN: "Bond",
  BONDS_WITHOUT_HYDROGEN: "Bond",
  BOND_FORCE_CONSTANT: "Bond",
  BOND_EQUIL_VALUE: "Bond",
  ANGLES_INC_HYDROGEN: "Angle",
  ANGLES_WITHOUT_HYDROGEN: "Angle",
  ANGLE_FORCE_CONSTANT: "Angle",
  ANGLE_EQUIL_VALUE: "Angle",
  DIHEDRALS_INC_HYDROGEN: "Dihedral",
  DIHEDRALS_WITHOUT_HYDROGEN: "Dihedral",
  DIHEDRAL_FORCE_CONSTANT: "Dihedral",
  DIHEDRAL_PERIODICITY: "Dihedral",
  DIHEDRAL_PHASE: "Dihedral",
  SCEE_SCALE_FACTOR: "1-4 Nonbonded",
  SCNB_SCALE_FACTOR: "1-4 Nonbonded",
  NONBONDED_PARM_INDEX: "Non-bonded",
  NUMBER_EXCLUDED_ATOMS: "Non-bonded",
  EXCLUDED_ATOMS_LIST: "Non-bonded",
  LENNARD_JONES_ACOEF: "Non-bonded",
  LENNARD_JONES_BCOEF: "Non-bonded",
};


const stylePresets = {
  sticks: { stick: { radius: 0.2 } },
  spheres: { sphere: { radius: 0.7 } },
  lines: { line: {} },
  ballstick: { stick: { radius: 0.2 }, sphere: { scale: 0.3 } },
  cartoon_ligand: {
    protein: { cartoon: { color: "spectrum" } },
    other: { stick: { radius: 0.2 } },
  },
};

function setStatus(level, message, detail) {
  const status = document.getElementById("status");
  const label = document.getElementById("status-label");
  const detailNode = document.getElementById("status-detail");
  if (!status || !label || !detailNode) {
    return;
  }
  label.textContent = message;
  detailNode.textContent = detail || "";
  status.className = "";
  if (level === "error") {
    status.classList.add("status-error");
  } else if (level === "success") {
    status.classList.add("status-success");
  } else if (level === "loading") {
    status.classList.add("status-loading");
  }
}

function reportError(message) {
  const detail = String(message);
  setStatus("error", "Error occurred.", "See log output for details.");
  console.error(detail);
  if (window.pywebview && window.pywebview.api && window.pywebview.api.log_client_error) {
    window.pywebview.api.log_client_error({ message: detail }).catch(() => {});
  }
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return null;
  }
  return num.toFixed(3);
}

function requestRender() {
  if (!viewer || renderScheduled) {
    return;
  }
  renderScheduled = true;
  window.requestAnimationFrame(() => {
    renderScheduled = false;
    if (viewer) {
      viewer.render();
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

function applyTheme(isDark) {
  darkMode = Boolean(isDark);
  document.body.classList.toggle("dark-mode", darkMode);
  const themeBtn = document.getElementById("theme-btn");
  if (themeBtn) {
    themeBtn.textContent = darkMode ? "Light mode" : "Dark mode";
  }
  if (viewer && typeof viewer.setBackgroundColor === "function") {
    viewer.setBackgroundColor(getViewerBackgroundColor());
    requestRender();
  }
}

function getHighlightAtomRadius() {
  if (currentStyleKey === "spheres") {
    return 0.9;
  }
  if (currentStyleKey === "ballstick") {
    return 0.7;
  }
  return 0.55;
}

function getHighlightBondRadius() {
  if (currentStyleKey === "lines") {
    return 0.2;
  }
  if (currentStyleKey === "spheres") {
    return 0.3;
  }
  return 0.32;
}

function addHighlightSphere(center, radius) {
  if (!viewer || !center) {
    return;
  }
  if (typeof viewer.addSphere === "function") {
    viewer.addSphere({
      center: center,
      radius: radius,
      color: HIGHLIGHT_COLOR,
      opacity: HIGHLIGHT_ATOM_OPACITY,
    });
    return;
  }
  if (typeof viewer.addShape === "function") {
    const shape = viewer.addShape({ color: HIGHLIGHT_COLOR, opacity: HIGHLIGHT_ATOM_OPACITY });
    if (shape && typeof shape.addSphere === "function") {
      shape.addSphere({ center: center, radius: radius });
    }
  }
}

function addHighlightCylinder(start, end, radius) {
  if (!viewer || !start || !end) {
    return;
  }
  if (typeof viewer.addCylinder === "function") {
    viewer.addCylinder({
      start: start,
      end: end,
      radius: radius,
      color: HIGHLIGHT_COLOR,
      opacity: HIGHLIGHT_LINE_OPACITY,
    });
    return;
  }
  if (typeof viewer.addShape === "function") {
    const shape = viewer.addShape({ color: HIGHLIGHT_COLOR, opacity: HIGHLIGHT_LINE_OPACITY });
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

function midpoint(posA, posB) {
  if (!posA || !posB) {
    return null;
  }
  return {
    x: (posA.x + posB.x) / 2,
    y: (posA.y + posB.y) / 2,
    z: (posA.z + posB.z) / 2,
  };
}

function centroid(positions) {
  if (!positions || !positions.length) {
    return null;
  }
  let x = 0;
  let y = 0;
  let z = 0;
  let count = 0;
  positions.forEach((pos) => {
    if (!pos) {
      return;
    }
    x += pos.x;
    y += pos.y;
    z += pos.z;
    count += 1;
  });
  if (!count) {
    return null;
  }
  return { x: x / count, y: y / count, z: z / count };
}

function addViewerLabel(text, position) {
  if (!viewer || !text || !position) {
    return;
  }
  const style = getLabelStyle();
  viewer.addLabel(text, { position: position, ...style });
}

function addViewerLabelLines(lines, position) {
  if (!viewer || !lines || !lines.length || !position) {
    return;
  }
  const root = document.body || document.documentElement;
  const styles = getComputedStyle(root);
  const fontSize = parseFloat(styles.getPropertyValue("--info-pop-font-size")) || 12;
  const lineHeight = Math.max(12, Math.round(fontSize * 1.2));
  const style = { ...getLabelStyle(), fontSize };
  const offsetBase = -((lines.length - 1) * lineHeight) / 2;
  lines.forEach((line, idx) => {
    if (!line) {
      return;
    }
    const offsetY = offsetBase + idx * lineHeight;
    viewer.addLabel(line, {
      position: position,
      screenOffset: { x: 0, y: offsetY },
      ...style,
    });
  });
}
function cacheAtom(serial, payload) {
  if (!serial) {
    return;
  }
  if (atomCache.has(serial)) {
    atomCache.delete(serial);
  }
  atomCache.set(serial, payload);
  if (atomCache.size > MAX_ATOM_CACHE) {
    const firstKey = atomCache.keys().next().value;
    if (firstKey !== undefined) {
      atomCache.delete(firstKey);
    }
  }
}

function setSelectionMode(mode) {
  selectionMode = mode;
  const title = document.getElementById("mode-title");
  if (title) {
    title.textContent = mode;
  }
  const tabs = document.querySelectorAll(".mode-tab");
  tabs.forEach((tab) => {
    if (tab.dataset.mode === mode) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });
}

function getSectionMode(name) {
  if (!name) {
    return null;
  }
  const key = String(name).trim().toUpperCase();
  return SECTION_MODE_MAP[key] || null;
}

function buildAtomIndex() {
  atomBySerial = new Map();
  atomIndexBySerial = new Map();
  atomByIndex = new Map();
  modelAtoms = [];
  if (!model) {
    return;
  }
  const atoms = model.selectedAtoms({});
  modelAtoms = atoms || [];
  modelAtoms.forEach((atom, idx) => {
    if (!atom || !atom.serial) {
      return;
    }
    atomBySerial.set(atom.serial, atom);
    const atomIndex = atom.index !== undefined ? atom.index : idx;
    atomIndexBySerial.set(atom.serial, atomIndex);
    atomByIndex.set(atomIndex, atom);
  });
}

function areBonded(serialA, serialB) {
  if (!serialA || !serialB) {
    return false;
  }
  const atomA = atomBySerial.get(serialA);
  const indexB = atomIndexBySerial.get(serialB);
  if (!atomA || indexB === undefined || !atomA.bonds) {
    return false;
  }
  return atomA.bonds.includes(indexB);
}

function isDihedralChain(serials) {
  if (!serials || serials.length !== 4) {
    return false;
  }
  return (
    areBonded(serials[0], serials[1]) &&
    areBonded(serials[1], serials[2]) &&
    areBonded(serials[2], serials[3])
  );
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

function findBondPath(serials) {
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

function bondDistance(serialA, serialB, maxDepth = 3) {
  if (!serialA || !serialB) {
    return null;
  }
  const startIdx = atomIndexBySerial.get(serialA);
  const targetIdx = atomIndexBySerial.get(serialB);
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
    const atom = atomByIndex.get(idx);
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

function selectionLabel(serial) {
  const cached = atomCache.get(serial);
  if (cached && cached.atom) {
    const atom = cached.atom;
    const residue = atom.residue || {};
    const resLabel = residue.resname
      ? `${residue.resname}${residue.resid !== undefined ? " " + residue.resid : ""}`
      : "";
    return `#${atom.serial} ${atom.atom_name || ""} ${resLabel}`.trim();
  }
  return `#${serial}`;
}

function renderInteractionTable(headers, rows) {
  if (!headers || !headers.length) {
    return "";
  }
  const headerHtml = headers
    .map((header) => `<th>${escapeHtml(String(header))}</th>`)
    .join("");
  const safeRows = rows && rows.length ? rows : [headers.map(() => null)];
  const bodyHtml = safeRows
    .map((row) => {
      const cells = headers
        .map((_, idx) => {
          const value =
            row && row[idx] !== undefined && row[idx] !== null && row[idx] !== ""
              ? row[idx]
              : "N/A";
          return `<td>${escapeHtml(String(value))}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<table class="interaction-table"><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`;
}

function formatInteractionDetails(mode, interaction) {
  if (!interaction || interaction.mode !== mode) {
    return "";
  }
  let headers = [];
  const rows = [];
  if (mode === "Bond") {
    headers = ["k", "r0"];
    (interaction.bonds || []).forEach((bond) => {
      rows.push([formatNumber(bond.force_constant), formatNumber(bond.equil_value)]);
    });
  } else if (mode === "Angle") {
    headers = ["k", "theta0"];
    (interaction.angles || []).forEach((angle) => {
      rows.push([formatNumber(angle.force_constant), formatNumber(angle.equil_value)]);
    });
  } else if (mode === "Dihedral") {
    headers = ["k", "n", "phase", "SCEE", "SCNB"];
    (interaction.dihedrals || []).forEach((term) => {
      rows.push([
        formatNumber(term.force_constant),
        formatNumber(term.periodicity),
        formatNumber(term.phase),
        formatNumber(term.scee),
        formatNumber(term.scnb),
      ]);
    });
  } else if (mode === "1-4 Nonbonded") {
    headers = ["SCEE", "SCNB", "Rmin", "eps", "A", "B"];
    const nb = interaction.nonbonded || null;
    const rmin = nb ? formatNumber(nb.rmin) : null;
    const eps = nb ? formatNumber(nb.epsilon) : null;
    const acoef = nb ? formatNumber(nb.acoef) : null;
    const bcoef = nb ? formatNumber(nb.bcoef) : null;
    const terms = (interaction.one_four || []).length ? interaction.one_four : [null];
    terms.forEach((term) => {
      rows.push([
        term ? formatNumber(term.scee) : null,
        term ? formatNumber(term.scnb) : null,
        rmin,
        eps,
        acoef,
        bcoef,
      ]);
    });
  } else if (mode === "Non-bonded") {
    headers = ["Rmin", "eps", "A", "B"];
    const nb = interaction.nonbonded || null;
    if (nb) {
      rows.push([
        formatNumber(nb.rmin),
        formatNumber(nb.epsilon),
        formatNumber(nb.acoef),
        formatNumber(nb.bcoef),
      ]);
    }
  }

  return renderInteractionTable(headers, rows);
}

function atomLabelText(serial, atomRecord) {
  const base = atomRecord ? `#${serial} ${atomRecord.atom}` : `#${serial}`;
  return base;
}

function renderSelectionSummary() {
  const details = document.getElementById("atom-details");
  if (!details) {
    return;
  }
  if (!selectionSerials.length) {
    details.textContent = "No atom selected.";
    return;
  }
  if (selectionMode === "Atom" && currentAtomInfo) {
    updateAtomDetails(currentAtomInfo);
    return;
  }
  let title = "";
  if (selectionMode === "Bond") {
    title = "Bonded atoms";
  } else if (selectionMode === "Angle") {
    title = "Angle atoms";
  } else if (selectionMode === "Dihedral") {
    title = "Dihedral atoms";
  } else if (selectionMode === "1-4 Nonbonded") {
    title = "1-4 nonbonded atoms";
  } else if (selectionMode === "Non-bonded") {
    title = "Non-bonded atoms";
  }
  const lines = selectionSerials.map((serial, idx) => {
    return `<div>Atom ${idx + 1}: <strong>${escapeHtml(selectionLabel(serial))}</strong></div>`;
  });
  const left = `<div class="selection-summary"><div>${escapeHtml(title)}</div>${lines.join(
    ""
  )}</div>`;
  const right = formatInteractionDetails(selectionMode, currentInteraction);
  if (right) {
    details.innerHTML = `<div class="selection-summary-grid">${left}<div class="selection-details">${right}</div></div>`;
  } else {
    details.innerHTML = left;
  }
}

function updateSelectionState(serial) {
  if (!serial) {
    return;
  }
  currentInteraction = null;
  if (!selectionSerials.length || selectionSerials.includes(serial)) {
    selectionSerials = [serial];
    setSelectionMode("Atom");
    return;
  }

  selectionSerials = selectionSerials.concat(serial);
  if (selectionSerials.length > 4) {
    selectionSerials = selectionSerials.slice(-4);
  }

  if (selectionSerials.length === 4) {
    const path = findBondPath(selectionSerials);
    if (path) {
      selectionSerials = path;
      setSelectionMode("Dihedral");
      return;
    }
  }

  if (selectionSerials.length === 3) {
    const path = findBondPath(selectionSerials);
    if (path) {
      selectionSerials = path;
      setSelectionMode("Angle");
      return;
    }
  }

  if (selectionSerials.length >= 2) {
    const lastTwo = selectionSerials.slice(-2);
    selectionSerials = lastTwo;
    if (areBonded(lastTwo[0], lastTwo[1])) {
      setSelectionMode("Bond");
    } else {
      const distance = bondDistance(lastTwo[0], lastTwo[1], 3);
      if (distance === 3) {
        setSelectionMode("1-4 Nonbonded");
      } else {
        setSelectionMode("Non-bonded");
      }
    }
    return;
  }

  selectionSerials = [serial];
  setSelectionMode("Atom");
}

function resetSelectionState() {
  selectionSerials = [];
  setSelectionMode("Atom");
  renderSelectionSummary();
}

function attachEmptyClickHandler() {
  if (emptyClickArmed) {
    return;
  }
  const container = document.getElementById("viewer");
  if (!container) {
    return;
  }
  container.addEventListener(
    "click",
    () => {
      if (lastAtomClick) {
        lastAtomClick = false;
      }
    },
    true
  );
  emptyClickArmed = true;
}

function getParm7ViewLineCount() {
  return parm7ViewIndices ? parm7ViewIndices.length : parm7Lines.length;
}

function getParm7LineIndex(viewIndex) {
  return parm7ViewIndices ? parm7ViewIndices[viewIndex] : viewIndex;
}

function getParm7ViewIndex(lineIndex) {
  if (!parm7ViewIndexMap) {
    return lineIndex;
  }
  return parm7ViewIndexMap.get(lineIndex);
}

function setParm7SectionView(section) {
  const view = document.getElementById("parm7-view");
  if (!view) {
    return;
  }
  if (!section) {
    parm7ViewIndices = null;
    parm7ViewIndexMap = null;
  } else {
    const startLine = Math.max(0, section.line || 0);
    const endLine = Math.min(
      parm7Lines.length - 1,
      section.end_line !== undefined ? section.end_line : section.line || 0
    );
    parm7ViewIndices = [];
    parm7ViewIndexMap = new Map();
    for (let line = startLine; line <= endLine; line += 1) {
      parm7ViewIndexMap.set(line, parm7ViewIndices.length);
      parm7ViewIndices.push(line);
    }
  }
  buildParm7View();
  view.scrollTop = 0;
  renderParm7Window();
}

function updateParm7FontSize(value) {
  const size = Number(value);
  if (!size || Number.isNaN(size)) {
    return;
  }
  const clamped = Math.min(32, Math.max(8, Math.round(size)));
  document.documentElement.style.setProperty("--parm7-font-size", `${clamped}pt`);
  const input = document.getElementById("parm7-font-size");
  if (input && input.value !== String(clamped)) {
    input.value = String(clamped);
  }
  if (parm7Lines.length) {
    buildParm7View();
  }
}

function applyUiConfig(config) {
  if (!config) {
    return;
  }
  const size = Number(config.info_font_size);
  if (!Number.isNaN(size) && size > 0) {
    document.documentElement.style.setProperty("--info-pop-font-size", `${size}pt`);
  }
}

function ensureSectionTooltip() {
  if (sectionTooltip) {
    return sectionTooltip;
  }
  sectionTooltip = document.createElement("div");
  sectionTooltip.id = "section-tooltip";
  document.body.appendChild(sectionTooltip);
  return sectionTooltip;
}

function showSectionTooltip(button, text) {
  if (!button || !text) {
    return;
  }
  const tooltip = ensureSectionTooltip();
  tooltip.textContent = text;
  tooltip.style.display = "block";
  tooltip.style.visibility = "hidden";
  const rect = button.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
  let top = rect.bottom + 8;
  const padding = 8;
  if (left < padding) {
    left = padding;
  }
  if (left + tooltipRect.width > window.innerWidth - padding) {
    left = window.innerWidth - tooltipRect.width - padding;
  }
  if (top + tooltipRect.height > window.innerHeight - padding) {
    top = rect.top - tooltipRect.height - 8;
  }
  tooltip.style.left = `${Math.max(padding, left)}px`;
  tooltip.style.top = `${Math.max(padding, top)}px`;
  tooltip.style.visibility = "visible";
}

function hideSectionTooltip() {
  if (sectionTooltip) {
    sectionTooltip.style.display = "none";
  }
}

function renderParm7File(highlights) {
  const view = document.getElementById("parm7-view");
  if (!view) {
    return;
  }
  if (!parm7Lines.length) {
    view.textContent = "No parm7 loaded.";
    return;
  }
  if (!parm7LinesContainer) {
    buildParm7View();
  }
  applyParm7Highlights(highlights || []);
}

function buildParm7View() {
  const view = document.getElementById("parm7-view");
  if (!view) {
    return;
  }
  view.innerHTML = "";
  parm7LineNodes = new Map();
  parm7LinesContainer = document.createElement("div");
  parm7LinesContainer.className = "parm7-lines";
  parm7Spacer = document.createElement("div");
  parm7Spacer.className = "parm7-spacer";
  view.appendChild(parm7Spacer);
  view.appendChild(parm7LinesContainer);

  const sample = document.createElement("div");
  sample.className = "parm7-line";
  sample.textContent = " ";
  parm7LinesContainer.appendChild(sample);
  parm7LineHeight = sample.getBoundingClientRect().height || 16;
  parm7LinesContainer.removeChild(sample);
  parm7Spacer.style.height = `${getParm7ViewLineCount() * parm7LineHeight}px`;
  parm7Window = { start: 0, end: 0 };
  renderParm7Window();

  if (!parm7ScrollAttached) {
    view.addEventListener("scroll", onParm7Scroll, { passive: true });
    parm7ScrollAttached = true;
  }
}

function renderParm7Line(viewIndex) {
  const lineIndex = getParm7LineIndex(viewIndex);
  const line = parm7Lines[lineIndex] || "";
  const ranges = parm7HighlightsByLine.get(lineIndex);
  if (!ranges || !ranges.length) {
    return { html: escapeHtml(line) || "&nbsp;", highlighted: false };
  }
  ranges.sort((a, b) => a.start - b.start);
  let out = "";
  let cursor = 0;
  ranges.forEach((range) => {
    const start = Math.max(range.start, cursor);
    const end = Math.max(start, range.end);
    if (start > cursor) {
      out += escapeHtml(line.slice(cursor, start));
    }
    if (end > start) {
      out += `<span class=\"parm7-highlight\">${escapeHtml(line.slice(start, end))}</span>`;
    }
    cursor = end;
  });
  if (cursor < line.length) {
    out += escapeHtml(line.slice(cursor));
  }
  return { html: out || "&nbsp;", highlighted: true };
}

function renderParm7Window() {
  const view = document.getElementById("parm7-view");
  if (!view || !parm7LinesContainer) {
    return;
  }
  const height = view.clientHeight || 0;
  const scrollTop = view.scrollTop || 0;
  const buffer = 40;
  const startIndex = Math.max(0, Math.floor(scrollTop / parm7LineHeight) - buffer);
  const totalLines = getParm7ViewLineCount();
  const endIndex = Math.min(
    totalLines,
    Math.ceil((scrollTop + height) / parm7LineHeight) + buffer
  );
  if (startIndex === parm7Window.start && endIndex === parm7Window.end) {
    return;
  }
  parm7Window = { start: startIndex, end: endIndex };
  parm7LineNodes.clear();
  parm7LinesContainer.innerHTML = "";
  const fragment = document.createDocumentFragment();
  for (let idx = startIndex; idx < endIndex; idx += 1) {
    const div = document.createElement("div");
    div.className = "parm7-line";
    div.dataset.line = String(getParm7LineIndex(idx));
    const rendered = renderParm7Line(idx);
    if (rendered.highlighted) {
      div.innerHTML = rendered.html;
    } else {
      div.textContent = parm7Lines[getParm7LineIndex(idx)] || " ";
    }
    fragment.appendChild(div);
    parm7LineNodes.set(idx, div);
  }
  parm7LinesContainer.style.transform = `translateY(${startIndex * parm7LineHeight}px)`;
  parm7LinesContainer.appendChild(fragment);
}

function onParm7Scroll() {
  if (parm7ScrollScheduled) {
    return;
  }
  parm7ScrollScheduled = true;
  window.requestAnimationFrame(() => {
    parm7ScrollScheduled = false;
    renderParm7Window();
  });
}

function applyParm7Highlights(highlights) {
  if (!parm7LinesContainer) {
    return;
  }
  parm7HighlightsByLine = new Map();
  let firstHighlightLine = null;
  highlights.forEach((hl) => {
    if (!parm7HighlightsByLine.has(hl.line)) {
      parm7HighlightsByLine.set(hl.line, []);
    }
    parm7HighlightsByLine.get(hl.line).push({ start: hl.start, end: hl.end });
    if (firstHighlightLine === null || hl.line < firstHighlightLine) {
      firstHighlightLine = hl.line;
    }
  });
  if (firstHighlightLine !== null) {
    const view = document.getElementById("parm7-view");
    if (view) {
      const viewIndex = getParm7ViewIndex(firstHighlightLine);
      if (viewIndex !== undefined) {
        view.scrollTop = viewIndex * parm7LineHeight;
      }
    }
  }
  renderParm7Window();
}

function renderParm7Sections(sections) {
  const container = document.getElementById("parm7-sections");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  const allButton = document.createElement("button");
  allButton.type = "button";
  allButton.textContent = "All";
  allButton.addEventListener("click", () => {
    setParm7SectionView(null);
  });
  container.appendChild(allButton);
  (sections || []).forEach((section) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = section.name;
    const mode = getSectionMode(section.name);
    if (mode) {
      button.dataset.mode = mode;
    }
    const description = section.description || "No description available.";
    if (section.deprecated) {
      button.dataset.deprecated = "true";
    } else if (description.toLowerCase().includes("deprecated")) {
      button.dataset.deprecated = "true";
    }
    button.addEventListener("click", () => {
      setParm7SectionView(section);
    });
    button.addEventListener("mouseenter", () => {
      showSectionTooltip(button, description);
    });
    button.addEventListener("mouseleave", () => {
      hideSectionTooltip();
    });
    button.addEventListener("focus", () => {
      showSectionTooltip(button, description);
    });
    button.addEventListener("blur", () => {
      hideSectionTooltip();
    });
    container.appendChild(button);
  });
}

function updateParm7Highlights(serials, mode) {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_parm7_highlights) {
    return;
  }
  if (!parm7Lines.length) {
    return;
  }
  const list = Array.isArray(serials) ? serials : serials ? [serials] : [];
  const cleanSerials = list
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (!cleanSerials.length) {
    renderParm7File([]);
    return;
  }
  window.pywebview.api
    .get_parm7_highlights({ serials: cleanSerials, mode: mode })
    .then((result) => {
      if (!result || !result.ok) {
        const msg = result && result.error ? result.error.message : "Failed to highlight parm7";
        reportError(msg);
        return;
      }
      renderParm7File(result.highlights || []);
      currentInteraction = result.interaction || null;
      renderSelectionSummary();
      if (currentInteraction) {
        renderInteractionLabels(currentInteraction);
      }
    })
    .catch((err) => {
      reportError(String(err));
    });
}

function setLoading(isLoading) {
  loading = isLoading;
  const disabled = isLoading ? true : false;
  const openBtn = document.getElementById("open-btn");
  const loadBtn = document.getElementById("load-btn");
  const styleSelect = document.getElementById("style-select");
  const filterBtn = document.getElementById("filter-btn");
  const clearBtn = document.getElementById("clear-btn");
  const fontInput = document.getElementById("parm7-font-size");
  if (openBtn) openBtn.disabled = disabled;
  if (loadBtn) loadBtn.disabled = disabled;
  if (styleSelect) styleSelect.disabled = disabled;
  if (filterBtn) filterBtn.disabled = disabled;
  if (clearBtn) clearBtn.disabled = disabled;
  if (fontInput) fontInput.disabled = disabled;
}

function load3Dmol() {
  if (window.$3Dmol) {
    return Promise.resolve(true);
  }
  if (threeDmolPromise) {
    return threeDmolPromise;
  }
  threeDmolPromise = new Promise((resolve) => {
    const script = document.createElement("script");
    script.src = "vendor/3Dmol-min.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.head.appendChild(script);
  });
  return threeDmolPromise;
}

async function ensureViewer() {
  const ok = await load3Dmol();
  if (!ok || !window.$3Dmol) {
    reportError("3Dmol.js not loaded. Copy web/vendor/3Dmol-min.js.");
    return null;
  }
  if (!viewer) {
    viewer = $3Dmol.createViewer(document.getElementById("viewer"), {
      backgroundColor: getViewerBackgroundColor(),
    });
    resizeViewer();
  }
  attachZoomHandler();
  return viewer;
}

function attachZoomHandler() {
  if (zoomHandlerAttached || !viewer) {
    return;
  }
  const container = document.getElementById("viewer");
  if (!container) {
    return;
  }
  container.addEventListener(
    "wheel",
    (event) => {
      if (!viewer) {
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
      viewer.zoom(factor);
      requestRender();
    },
    { passive: false, capture: true }
  );
  zoomHandlerAttached = true;
}

function resizeViewer(renderNow = true) {
  if (viewer && typeof viewer.resize === "function") {
    viewer.resize();
    if (renderNow) {
      requestRender();
    }
  }
}

function decodeBase64(b64) {
  const decoded = atob(b64);
  return decoded;
}

function applyBaseStyle() {
  if (!viewer) {
    return;
  }
  if (currentStyleKey === "cartoon_ligand") {
    viewer.setStyle({ protein: true }, stylePresets.cartoon_ligand.protein);
    viewer.setStyle({ not: { protein: true } }, stylePresets.cartoon_ligand.other);
    return;
  }
  if (!baseStyle) {
    baseStyle = stylePresets.sticks;
  }
  viewer.setStyle({}, baseStyle);
}

function applyStylePreset(key, renderNow = true) {
  if (!viewer) {
    return;
  }
  currentStyleKey = key;
  if (key === "cartoon_ligand") {
    viewer.setStyle({ protein: true }, stylePresets.cartoon_ligand.protein);
    viewer.setStyle({ not: { protein: true } }, stylePresets.cartoon_ligand.other);
  } else {
    baseStyle = stylePresets[key] || stylePresets.sticks;
    viewer.setStyle({}, baseStyle);
  }
  if (renderNow) {
    requestRender();
  }
}

function clearHighlights() {
  if (!viewer) {
    return;
  }
  viewer.removeAllLabels();
  if (typeof viewer.removeAllShapes === "function") {
    viewer.removeAllShapes();
  }
  requestRender();
  currentSelection = [];
  currentAtomInfo = null;
  currentInteraction = null;
  selectionSerials = [];
  setSelectionMode("Atom");
  renderSelectionSummary();
  updateAboutPanel(currentAtomInfo);
  renderParm7File([]);
}

function highlightSerials(serials) {
  if (!viewer) {
    return;
  }
  viewer.removeAllLabels();
  if (typeof viewer.removeAllShapes === "function") {
    viewer.removeAllShapes();
  }
  const selection = serials || [];
  const smallSelection = selection.length > 0 && selection.length <= 4;
  if (smallSelection) {
    if (selectionMode === "Atom") {
      const labelStyle = getLabelStyle();
      selection.forEach((serial) => {
        const atoms = model ? model.selectedAtoms({ serial: serial }) : [];
        if (atoms && atoms.length) {
          viewer.addLabel(atomLabelText(serial, atoms[0]), {
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
      const atom = atomBySerial.get(serial);
      const center = atomPosition(atom);
      if (center) {
        addHighlightSphere(center, radius);
      }
    });
    const drawLines =
      selectionMode === "Bond" || selectionMode === "Angle" || selectionMode === "Dihedral";
    if (drawLines) {
      for (let idx = 0; idx < selection.length - 1; idx += 1) {
        const serialA = selection[idx];
        const serialB = selection[idx + 1];
        if (!areBonded(serialA, serialB)) {
          continue;
        }
        const atomA = atomBySerial.get(serialA);
        const atomB = atomBySerial.get(serialB);
        const start = atomPosition(atomA);
        const end = atomPosition(atomB);
        if (start && end) {
          addHighlightCylinder(start, end, bondRadius);
        }
      }
    }
  }
  requestRender();
  currentSelection = selection;
}

function buildBondLabels(bonds) {
  const labels = [];
  (bonds || []).forEach((bond) => {
    const serials = bond.serials || [];
    if (serials.length < 2) {
      return;
    }
    const posA = atomPosition(atomBySerial.get(serials[0]));
    const posB = atomPosition(atomBySerial.get(serials[1]));
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
    const center = atomPosition(atomBySerial.get(serials[1]));
    const position = center || centroid(serials.map((s) => atomPosition(atomBySerial.get(s))));
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

function buildDihedralLabels(dihedrals) {
  const labels = [];
  if (!dihedrals || !dihedrals.length) {
    return labels;
  }
  const serials = dihedrals[0].serials || [];
  let position = null;
  if (serials.length >= 4) {
    const posB = atomPosition(atomBySerial.get(serials[1]));
    const posC = atomPosition(atomBySerial.get(serials[2]));
    position = midpoint(posB, posC);
  }
  if (!position) {
    position = centroid(serials.map((s) => atomPosition(atomBySerial.get(s))));
  }
  const lines = [];
  dihedrals.forEach((term, idx) => {
    const k = formatNumber(term.force_constant);
    const n = formatNumber(term.periodicity);
    const phase = formatNumber(term.phase);
    const parts = [];
    if (k !== null) parts.push(`k=${k}`);
    if (n !== null) parts.push(`n=${n}`);
    if (phase !== null) parts.push(`phase=${phase}`);
    if (parts.length) {
      lines.push(parts.join(" "));
    }
    const scaleParts = [];
    const scee = formatNumber(term.scee);
    const scnb = formatNumber(term.scnb);
    if (scee !== null) scaleParts.push(`SCEE=${scee}`);
    if (scnb !== null) scaleParts.push(`SCNB=${scnb}`);
    if (scaleParts.length) {
      lines.push(scaleParts.join(" "));
    }
  });
  if (lines.length) {
    labels.push({ lines: lines, position });
  }
  return labels;
}

function buildDihedralIndexLabel(serials) {
  if (!serials || serials.length < 4) {
    return null;
  }
  const posB = atomPosition(atomBySerial.get(serials[1]));
  const posC = atomPosition(atomBySerial.get(serials[2]));
  const position =
    midpoint(posB, posC) || centroid(serials.map((s) => atomPosition(atomBySerial.get(s))));
  const text = `Dihedral ${serials.join("-")}`;
  return { text, position };
}

function buildNonbondedLabels(nonbonded) {
  if (!nonbonded) {
    return [];
  }
  const serials = nonbonded.serials || [];
  if (serials.length < 2) {
    return [];
  }
  const posA = atomPosition(atomBySerial.get(serials[0]));
  const posB = atomPosition(atomBySerial.get(serials[1]));
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
  return [{ text: lines.join("\n"), position }];
}

function buildOneFourLabels(oneFour) {
  if (!oneFour || !oneFour.length) {
    return [];
  }
  const serials = oneFour[0].serials || [];
  let position = null;
  if (serials.length >= 2) {
    const posA = atomPosition(atomBySerial.get(serials[0]));
    const posB = atomPosition(atomBySerial.get(serials[1]));
    position = midpoint(posA, posB);
  }
  const lines = [];
  const multi = oneFour.length > 1;
  oneFour.forEach((term, idx) => {
    const parts = [];
    if (multi) {
      parts.push(`term ${idx + 1}`);
    }
    const scee = formatNumber(term.scee);
    const scnb = formatNumber(term.scnb);
    if (scee !== null) parts.push(`SCEE=${scee}`);
    if (scnb !== null) parts.push(`SCNB=${scnb}`);
    if (parts.length) {
      lines.push(parts.join(" "));
    }
  });
  if (!lines.length) {
    return [];
  }
  return [{ text: lines.join("\n"), position }];
}

function renderInteractionLabels(interaction) {
  if (!interaction || !viewer) {
    return;
  }
  const labels = [];
  if (interaction.mode === "Bond") {
    labels.push(...buildBondLabels(interaction.bonds));
  } else if (interaction.mode === "Angle") {
    labels.push(...buildAngleLabels(interaction.angles));
  } else if (interaction.mode === "Dihedral") {
    const label = buildDihedralIndexLabel(selectionSerials);
    if (label) {
      labels.push(label);
    }
  } else if (interaction.mode === "1-4 Nonbonded") {
    labels.push(...buildOneFourLabels(interaction.one_four));
    labels.push(...buildNonbondedLabels(interaction.nonbonded));
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

function renderModel(pdbB64) {
  const pdb = decodeBase64(pdbB64);
  viewer.clear();
  model = viewer.addModel(pdb, "pdb");
  model.setClickable({}, true, function (atom) {
    if (!atom || !atom.serial) {
      return;
    }
    selectAtom(atom.serial);
  });
  buildAtomIndex();
  attachEmptyClickHandler();
  viewer.zoomTo();
  resizeViewer(false);
  requestRender();
}

function updateAtomDetails(atom) {
  const details = document.getElementById("atom-details");
  if (!details) {
    return;
  }
  const residue = atom.residue || {};
  const parm7 = atom.parm7 || {};

  const leftLines = [];
  const addLine = (list, label, value) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    list.push(
      `<div class=\"atom-detail-row\"><span class=\"atom-detail-label\">${escapeHtml(
        String(label)
      )}:</span> ${escapeHtml(String(value))}</div>`
    );
  };

  addLine(leftLines, "Serial", atom.serial);
  addLine(leftLines, "Atom", atom.atom_name || "");
  addLine(leftLines, "Element", atom.element || "");
  if (parm7.mass !== null && parm7.mass !== undefined) {
    const massText = formatNumber(parm7.mass);
    if (massText !== null) {
      addLine(leftLines, "Mass", `${massText} g/mol`);
    }
  }
  addLine(leftLines, "Residue", `${residue.resname || ""} (${residue.resid || ""})`);
  if (residue.chain) {
    addLine(leftLines, "Chain", residue.chain);
  }
  const coordX = formatNumber(atom.coords.x);
  const coordY = formatNumber(atom.coords.y);
  const coordZ = formatNumber(atom.coords.z);
  if (coordX !== null && coordY !== null && coordZ !== null) {
    addLine(leftLines, "Coords", `${coordX}, ${coordY}, ${coordZ} Angstrom`);
  }
  if (parm7.atom_type) {
    addLine(leftLines, "Atom type", parm7.atom_type);
  }
  if (parm7.atom_type_index !== null && parm7.atom_type_index !== undefined) {
    addLine(leftLines, "Atom type index", parm7.atom_type_index);
  }

  const chargeHeaders = [
    "Charge raw (e*18.2223)",
    "Charge (e)",
    "Rmin (Angstrom)",
    "Epsilon (kcal/mol)",
  ];
  let rawChargeCell = null;
  let chargeCell = null;
  if (parm7.charge_raw && parm7.charge_e !== null && parm7.charge_e !== undefined) {
    const rawValue =
      typeof parm7.charge_raw === "string"
        ? parm7.charge_raw.trim()
        : String(parm7.charge_raw);
    const rawNumber = formatNumber(rawValue);
    const chargeValue = formatNumber(parm7.charge_e);
    if (rawNumber !== null && chargeValue !== null) {
      rawChargeCell = rawNumber;
      chargeCell = `${rawNumber} / 18.2223 = ${chargeValue} e`;
    }
  } else if (parm7.charge !== null && parm7.charge !== undefined) {
    const chargeValue = formatNumber(parm7.charge);
    if (chargeValue !== null) {
      chargeCell = `${chargeValue} e`;
    }
  }
  const rminCell =
    parm7.lj_rmin !== null && parm7.lj_rmin !== undefined
      ? formatNumber(parm7.lj_rmin)
      : null;
  const epsilonCell =
    parm7.lj_epsilon !== null && parm7.lj_epsilon !== undefined
      ? formatNumber(parm7.lj_epsilon)
      : null;

  const leftHtml = leftLines.join("");
  const rightHtml = renderInteractionTable(chargeHeaders, [
    [rawChargeCell, chargeCell, rminCell, epsilonCell],
  ]);
  details.innerHTML = `<div class=\"atom-details-grid\"><div class=\"atom-details-column\">${leftHtml}</div><div class=\"atom-details-column\">${rightHtml}</div></div>`;
}

function updateAboutPanel(atom) {
  const panel = document.getElementById("about-panel");
  const content = document.getElementById("about-content");
  if (!panel || !content) {
    return;
  }
  if (!aboutVisible) {
    return;
  }
  if (!atom) {
    content.textContent = "Select an atom to see the calculation details.";
    return;
  }
  const parm7 = atom.parm7 || {};
  const atomLabel = `Atom #${atom.serial} ${atom.atom_name || ""}`.trim();
  const rawCharge =
    typeof parm7.charge_raw === "string" ? parm7.charge_raw.trim() : parm7.charge_raw;
  const rawChargeText = formatNumber(rawCharge);
  const chargeText = formatNumber(parm7.charge_e);
  const chargeExample =
    rawChargeText !== null && chargeText !== null
      ? `charge (e) = charge_raw / 18.2223 = ${rawChargeText} / 18.2223 = ${chargeText} e`
      : null;

  const typeIndex = parm7.atom_type_index;
  const acoefText = formatNumber(parm7.lj_a_coef);
  const bcoefText = formatNumber(parm7.lj_b_coef);
  const rminText = formatNumber(parm7.lj_rmin);
  const epsilonText = formatNumber(parm7.lj_epsilon);
  let ljExample = null;
  if (typeIndex && acoefText !== null && bcoefText !== null) {
    const rminExample = rminText !== null ? `Rmin = ${rminText} Angstrom` : "Rmin N/A";
    const epsilonExample =
      epsilonText !== null ? `epsilon = ${epsilonText} kcal/mol` : "epsilon N/A";
    ljExample = `A = ${acoefText}, B = ${bcoefText}. ${rminExample}, ${epsilonExample}.`;
  }
  const headerParts = [atomLabel];
  if (typeIndex) {
    headerParts.push(`Type index: ${typeIndex}`);
  }
  const headerLine = headerParts.join(", ");

  content.innerHTML = `
    <div><strong>${escapeHtml(headerLine)}</strong></div>
    ${chargeExample ? `<div class="about-formula">${escapeHtml(chargeExample)}</div>` : ""}
    <div>Rmin and epsilon use diagonal LJ parameters from LENNARD_JONES_ACOEF and LENNARD_JONES_BCOEF via NONBONDED_PARM_INDEX.</div>
    <div class="about-formula">Rmin = (2 * A / B)^(1/6), epsilon = B^2 / (4 * A)</div>
    ${ljExample ? `<div>${escapeHtml(ljExample)}</div>` : ""}
  `;
}

function toggleAboutPanel() {
  aboutVisible = !aboutVisible;
  const panel = document.getElementById("about-panel");
  if (!panel) {
    return;
  }
  if (aboutVisible) {
    panel.classList.remove("hidden");
    updateAboutPanel(currentAtomInfo);
  } else {
    panel.classList.add("hidden");
  }
}

function addHistory(atom) {}

function applyAtomSelection(atom, highlights) {
  if (!atom) {
    return;
  }
  currentAtomInfo = atom;
  renderSelectionSummary();
  updateAboutPanel(atom);
  const selection = selectionSerials.length ? selectionSerials : [atom.serial];
  highlightSerials(selection);
  if (selection.length === 1 && highlights) {
    renderParm7File(highlights);
    return;
  }
  updateParm7Highlights(selection, selectionMode);
}

function selectAtom(serial) {
  if (loading) {
    return;
  }
  lastAtomClick = true;
  updateSelectionState(serial);
  renderSelectionSummary();
  const selection = selectionSerials.length ? selectionSerials : [serial];
  highlightSerials(selection);
  const cached = atomCache.get(serial);
  if (cached) {
    applyAtomSelection(cached.atom, cached.highlights);
    setStatus("success", `Selected atom ${serial} (cached)`);
    return;
  }
  setStatus("loading", `Loading atom ${serial}...`);
  const selectStart = performance.now();
  const api = window.pywebview.api;
  if (api.get_atom_bundle) {
    api
      .get_atom_bundle({ serial: serial })
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
      .catch((err) => {
        reportError(String(err));
      });
    return;
  }
  api
    .get_atom_info({ serial: serial })
    .then((result) => {
      if (!result || !result.ok) {
        const msg = result && result.error ? result.error.message : "Unknown error";
        reportError(msg);
        return;
      }
      console.debug(
        `get_atom_info completed in ${(performance.now() - selectStart).toFixed(1)}ms`
      );
      cacheAtom(serial, { atom: result.atom, highlights: null });
      applyAtomSelection(result.atom, null);
      setStatus("success", `Selected atom ${serial}`);
    })
    .catch((err) => {
      reportError(String(err));
    });
}

function loadFromInputs() {
  const parm7 = document.getElementById("parm7-path").value.trim();
  const rst7 = document.getElementById("rst7-path").value.trim();
  if (!parm7 || !rst7) {
    reportError("Provide both parm7 and rst7 paths");
    return;
  }
  loadSystem(parm7, rst7);
}

async function loadSystem(parm7Path, rst7Path) {
  if (!window.pywebview || !window.pywebview.api) {
    reportError("pywebview API not available");
    return;
  }
  const readyViewer = await ensureViewer();
  if (!readyViewer) {
    return;
  }
  currentAtomInfo = null;
  updateAboutPanel(currentAtomInfo);
  parm7Lines = [];
  parm7Sections = [];
  parm7LineNodes = new Map();
  parm7HighlightsByLine = new Map();
  parm7LinesContainer = null;
  parm7Spacer = null;
  parm7Window = { start: 0, end: 0 };
  parm7ViewIndices = null;
  parm7ViewIndexMap = null;
  const view = document.getElementById("parm7-view");
  if (view) {
    view.textContent = "Loading parm7...";
  }
  const sectionsContainer = document.getElementById("parm7-sections");
  if (sectionsContainer) {
    sectionsContainer.innerHTML = "";
  }
  const loadStart = performance.now();
  setLoading(true);
  setStatus("loading", "Loading system...");
  window.pywebview.api
    .load_system({ parm7_path: parm7Path, rst7_path: rst7Path })
    .then((result) => {
      if (!result || !result.ok) {
        const msg = result && result.error ? result.error.message : "Failed to load";
        reportError(msg);
        setLoading(false);
        return;
      }
      console.debug(
        `load_system completed in ${(performance.now() - loadStart).toFixed(1)}ms`
      );
      renderModel(result.pdb_b64);
      applyStylePreset(document.getElementById("style-select").value, false);
      resizeViewer(true);
      const warn =
        result.warnings && result.warnings.length
          ? ` Warnings: ${result.warnings.join(", ")}`
          : "";
      setStatus("success", `Loaded ${result.natoms} atoms, ${result.nresidues} residues.${warn}`);
      setLoading(false);
      if (window.pywebview.api.get_parm7_text) {
        window.pywebview.api
          .get_parm7_text()
          .then((textResult) => {
            if (!textResult || !textResult.ok) {
              const msg =
                textResult && textResult.error
                  ? textResult.error.message
                  : "Failed to load parm7 text";
              reportError(msg);
              return;
            }
            const text = decodeBase64(textResult.parm7_text_b64 || "");
            parm7Lines = text.split("\n");
            renderParm7File([]);
          })
          .catch((err) => {
            reportError(String(err));
          });
      }
      if (window.pywebview.api.get_parm7_sections) {
        window.pywebview.api
          .get_parm7_sections()
          .then((sectionResult) => {
            if (!sectionResult || !sectionResult.ok) {
              const msg =
                sectionResult && sectionResult.error
                  ? sectionResult.error.message
                  : "Failed to load parm7 sections";
              reportError(msg);
              return;
            }
            parm7Sections = sectionResult.sections || [];
            renderParm7Sections(parm7Sections);
          })
          .catch((err) => {
            reportError(String(err));
          });
      }
    })
    .catch((err) => {
      reportError(String(err));
      setLoading(false);
    });
}

function setInitialPaths(payload) {
  if (!payload) {
    return;
  }
  const parm7Path = payload.parm7 || payload.parm7_path || "";
  const rst7Path = payload.rst7 || payload.rst7_path || "";
  if (!parm7Path || !rst7Path) {
    return;
  }
  const parm7Input = document.getElementById("parm7-path");
  const rst7Input = document.getElementById("rst7-path");
  if (parm7Input) {
    parm7Input.value = parm7Path;
  }
  if (rst7Input) {
    rst7Input.value = rst7Path;
  }
  if (window.pywebview && window.pywebview.api) {
    loadSystem(parm7Path, rst7Path);
    return;
  }
  window.__pendingLoad = { parm7: parm7Path, rst7: rst7Path };
}

window.__setInitialPaths = setInitialPaths;

function runFilter() {
  if (loading) {
    return;
  }
  const resnameInput = document.getElementById("filter-resname");
  const atomnameInput = document.getElementById("filter-atomname");
  const atomtypeInput = document.getElementById("filter-atomtype");
  const chargeMinInput = document.getElementById("filter-charge-min");
  const chargeMaxInput = document.getElementById("filter-charge-max");
  if (!resnameInput || !atomnameInput || !atomtypeInput || !chargeMinInput || !chargeMaxInput) {
    reportError("Filter controls are not available.");
    return;
  }
  const filters = {
    resname_contains: resnameInput.value.trim(),
    atomname_contains: atomnameInput.value.trim(),
    atom_type_equals: atomtypeInput.value.trim(),
    charge_min: chargeMinInput.value.trim(),
    charge_max: chargeMaxInput.value.trim(),
  };

  setStatus("loading", "Running query...");
  window.pywebview.api
    .query_atoms({ filters: filters })
    .then((result) => {
      if (!result || !result.ok) {
        const msg = result && result.error ? result.error.message : "Query failed";
        reportError(msg);
        return;
      }
      highlightSerials(result.serials);
      const truncated = result.truncated ? " (truncated)" : "";
      setStatus("success", `Found ${result.count} atoms${truncated}`);
    })
    .catch((err) => {
      reportError(String(err));
    });
}

function handleOpenDialog() {
  if (!window.pywebview || !window.pywebview.api) {
    reportError("pywebview API not available");
    return;
  }
  window.pywebview.api
    .select_files()
    .then((result) => {
      if (!result || !result.ok) {
        const msg = result && result.error ? result.error.message : "Dialog cancelled";
        reportError(msg);
        return;
      }
      document.getElementById("parm7-path").value = result.parm7_path;
      document.getElementById("rst7-path").value = result.rst7_path;
      loadSystem(result.parm7_path, result.rst7_path);
    })
    .catch((err) => {
      reportError(String(err));
    });
}

function attachEvents() {
  if (eventsAttached) {
    return;
  }
  eventsAttached = true;
  const openBtn = document.getElementById("open-btn");
  const loadBtn = document.getElementById("load-btn");
  const clearBtn = document.getElementById("clear-btn");
  const filterBtn = document.getElementById("filter-btn");
  const aboutBtn = document.getElementById("about-btn");
  const themeBtn = document.getElementById("theme-btn");
  const styleSelect = document.getElementById("style-select");
  const fontInput = document.getElementById("parm7-font-size");
  if (openBtn) openBtn.addEventListener("click", handleOpenDialog);
  if (loadBtn) loadBtn.addEventListener("click", loadFromInputs);
  if (clearBtn) clearBtn.addEventListener("click", clearHighlights);
  if (filterBtn) filterBtn.addEventListener("click", runFilter);
  if (aboutBtn) aboutBtn.addEventListener("click", toggleAboutPanel);
  if (themeBtn) themeBtn.addEventListener("click", () => applyTheme(!darkMode));
  if (styleSelect) {
    styleSelect.addEventListener("change", (event) => {
      applyStylePreset(event.target.value);
    });
  }
  if (fontInput) {
    fontInput.addEventListener("input", (event) => {
      updateParm7FontSize(event.target.value);
    });
  }
}

window.addEventListener("pywebviewready", async function () {
  window.__pywebview_ready = true;
  attachEvents();
  await ensureViewer();
  setStatus("success", "Ready", "");
  applyTheme(darkMode);
  if (window.pywebview && window.pywebview.api && window.pywebview.api.get_ui_config) {
    window.pywebview.api
      .get_ui_config()
      .then((result) => {
        if (result && result.ok) {
          applyUiConfig(result.config);
        }
      })
      .catch(() => {});
  }
  if (window.pywebview && window.pywebview.api && window.pywebview.api.get_initial_paths) {
    window.pywebview.api
      .get_initial_paths()
      .then((result) => {
        if (result && result.ok && result.parm7_path && result.rst7_path) {
          setInitialPaths({ parm7: result.parm7_path, rst7: result.rst7_path });
        }
      })
      .catch(() => {});
  }
  if (window.__pendingLoad) {
    const payload = window.__pendingLoad;
    window.__pendingLoad = null;
    loadSystem(payload.parm7, payload.rst7);
  }
});

window.addEventListener("DOMContentLoaded", function () {
  attachEvents();
  if (!window.pywebview) {
    ensureViewer();
    reportError("pywebview not available. Run via Python app.");
  }
  const fontInput = document.getElementById("parm7-font-size");
  if (fontInput) {
    updateParm7FontSize(fontInput.value);
  }
  applyTheme(darkMode);
  setSelectionMode("Atom");
});

window.addEventListener("resize", function () {
  resizeViewer();
});
