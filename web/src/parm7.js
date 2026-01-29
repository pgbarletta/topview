import { getParm7Highlights } from "./bridge.js";
import { PARM7_FONT_MAX, PARM7_FONT_MIN, SECTION_MODE_MAP } from "./constants.js";
import { state } from "./state.js";
import { escapeHtml } from "./utils.js";

const PARM7_SECTION_PREFS = {
  Atom: ["LENNARD_JONES_ACOEF", "HBOND_ACOEF"],
  Bond: ["BOND_FORCE_CONSTANT", "BOND_EQUIL_VALUE"],
  Angle: ["ANGLE_FORCE_CONSTANT", "ANGLE_EQUIL_VALUE"],
  Dihedral: ["DIHEDRAL_FORCE_CONSTANT", "DIHEDRAL_PERIODICITY", "DIHEDRAL_PHASE"],
  Improper: ["DIHEDRAL_FORCE_CONSTANT", "DIHEDRAL_PERIODICITY", "DIHEDRAL_PHASE"],
  "1-4 Nonbonded": [
    "LENNARD_JONES_ACOEF",
    "HBOND_ACOEF",
    "SCEE_SCALE_FACTOR",
    "SCNB_SCALE_FACTOR",
  ],
  "Non-bonded": ["LENNARD_JONES_ACOEF", "HBOND_ACOEF"],
};

/**
 * Reset parm7 state and virtualization buffers.
 */
export function resetParm7State() {
  state.parm7Lines = [];
  state.parm7Sections = [];
  state.parm7LineNodes = new Map();
  state.parm7HighlightsByLine = new Map();
  state.parm7LinesContainer = null;
  state.parm7Spacer = null;
  state.parm7LineHeight = 16;
  state.parm7Window = { start: 0, end: 0 };
  state.parm7ViewIndices = null;
  state.parm7ViewIndexMap = null;
}

function getParm7ViewLineCount() {
  return state.parm7ViewIndices ? state.parm7ViewIndices.length : state.parm7Lines.length;
}

function getParm7LineIndex(viewIndex) {
  return state.parm7ViewIndices ? state.parm7ViewIndices[viewIndex] : viewIndex;
}

function getParm7ViewIndex(lineIndex) {
  if (!state.parm7ViewIndexMap) {
    return lineIndex;
  }
  return state.parm7ViewIndexMap.get(lineIndex);
}

/**
 * Apply a line range filter based on a parm7 section.
 * @param {object|null} section
 */
export function setParm7SectionView(section) {
  const view = document.getElementById("parm7-view");
  if (!view) {
    return;
  }
  if (!section) {
    state.parm7ViewIndices = null;
    state.parm7ViewIndexMap = null;
  } else {
    const startLine = Math.max(0, section.line || 0);
    const endLine = Math.min(
      state.parm7Lines.length - 1,
      section.end_line !== undefined ? section.end_line : section.line || 0
    );
    state.parm7ViewIndices = [];
    state.parm7ViewIndexMap = new Map();
    for (let line = startLine; line <= endLine; line += 1) {
      state.parm7ViewIndexMap.set(line, state.parm7ViewIndices.length);
      state.parm7ViewIndices.push(line);
    }
  }
  buildParm7View();
  view.scrollTop = 0;
  renderParm7Window();
}

/**
 * Update the parm7 font size and reflow virtualization.
 * @param {number|string} value
 */
export function updateParm7FontSize(value) {
  const size = Number(value);
  if (!size || Number.isNaN(size)) {
    return;
  }
  const clamped = Math.min(PARM7_FONT_MAX, Math.max(PARM7_FONT_MIN, Math.round(size)));
  document.documentElement.style.setProperty("--parm7-font-size", `${clamped}pt`);
  const input = document.getElementById("parm7-font-size");
  if (input && input.value !== String(clamped)) {
    input.value = String(clamped);
  }
  if (state.parm7Lines.length) {
    buildParm7View();
  }
}

function ensureSectionTooltip() {
  if (state.sectionTooltip) {
    return state.sectionTooltip;
  }
  state.sectionTooltip = document.createElement("div");
  state.sectionTooltip.id = "section-tooltip";
  document.body.appendChild(state.sectionTooltip);
  return state.sectionTooltip;
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
  if (state.sectionTooltip) {
    state.sectionTooltip.style.display = "none";
  }
}

/**
 * Render the parm7 panel with highlights.
 * @param {Array<object>} highlights
 */
export function renderParm7File(highlights) {
  const view = document.getElementById("parm7-view");
  if (!view) {
    return;
  }
  if (!state.parm7Lines.length) {
    view.textContent = "No parm7 loaded.";
    return;
  }
  if (!state.parm7LinesContainer) {
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
  state.parm7LineNodes = new Map();
  state.parm7LinesContainer = document.createElement("div");
  state.parm7LinesContainer.className = "parm7-lines";
  state.parm7Spacer = document.createElement("div");
  state.parm7Spacer.className = "parm7-spacer";
  view.appendChild(state.parm7Spacer);
  view.appendChild(state.parm7LinesContainer);

  const sample = document.createElement("div");
  sample.className = "parm7-line";
  sample.textContent = " ";
  state.parm7LinesContainer.appendChild(sample);
  state.parm7LineHeight = sample.getBoundingClientRect().height || 16;
  state.parm7LinesContainer.removeChild(sample);
  state.parm7Spacer.style.height = `${getParm7ViewLineCount() * state.parm7LineHeight}px`;
  state.parm7Window = { start: 0, end: 0 };
  renderParm7Window();

  if (!state.parm7ScrollAttached) {
    view.addEventListener("scroll", onParm7Scroll, { passive: true });
    state.parm7ScrollAttached = true;
  }
}

function renderParm7Line(viewIndex) {
  const lineIndex = getParm7LineIndex(viewIndex);
  const line = state.parm7Lines[lineIndex] || "";
  const ranges = state.parm7HighlightsByLine.get(lineIndex);
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
  if (!view || !state.parm7LinesContainer) {
    return;
  }
  const height = view.clientHeight || 0;
  const scrollTop = view.scrollTop || 0;
  const buffer = 40;
  const startIndex = Math.max(0, Math.floor(scrollTop / state.parm7LineHeight) - buffer);
  const totalLines = getParm7ViewLineCount();
  const endIndex = Math.min(
    totalLines,
    Math.ceil((scrollTop + height) / state.parm7LineHeight) + buffer
  );
  if (startIndex === state.parm7Window.start && endIndex === state.parm7Window.end) {
    return;
  }
  state.parm7Window = { start: startIndex, end: endIndex };
  state.parm7LineNodes.clear();
  state.parm7LinesContainer.innerHTML = "";
  const fragment = document.createDocumentFragment();
  for (let idx = startIndex; idx < endIndex; idx += 1) {
    const div = document.createElement("div");
    div.className = "parm7-line";
    div.dataset.line = String(getParm7LineIndex(idx));
    const rendered = renderParm7Line(idx);
    if (rendered.highlighted) {
      div.innerHTML = rendered.html;
    } else {
      div.textContent = state.parm7Lines[getParm7LineIndex(idx)] || " ";
    }
    fragment.appendChild(div);
    state.parm7LineNodes.set(idx, div);
  }
  state.parm7LinesContainer.style.transform = `translateY(${startIndex * state.parm7LineHeight}px)`;
  state.parm7LinesContainer.appendChild(fragment);
}

function onParm7Scroll() {
  if (state.parm7ScrollScheduled) {
    return;
  }
  state.parm7ScrollScheduled = true;
  window.requestAnimationFrame(() => {
    state.parm7ScrollScheduled = false;
    renderParm7Window();
  });
}

function applyParm7Highlights(highlights) {
  if (!state.parm7LinesContainer) {
    return;
  }
  state.parm7HighlightsByLine = new Map();
  let firstHighlightLine = null;
  let firstHighlightInView = null;
  highlights.forEach((hl) => {
    if (!state.parm7HighlightsByLine.has(hl.line)) {
      state.parm7HighlightsByLine.set(hl.line, []);
    }
    state.parm7HighlightsByLine.get(hl.line).push({ start: hl.start, end: hl.end });
    if (firstHighlightLine === null || hl.line < firstHighlightLine) {
      firstHighlightLine = hl.line;
    }
    if (state.parm7ViewIndexMap && state.parm7ViewIndexMap.has(hl.line)) {
      if (firstHighlightInView === null || hl.line < firstHighlightInView) {
        firstHighlightInView = hl.line;
      }
    }
  });
  const targetLine = firstHighlightInView !== null ? firstHighlightInView : firstHighlightLine;
  if (targetLine !== null) {
    const view = document.getElementById("parm7-view");
    if (view) {
      const viewIndex = getParm7ViewIndex(targetLine);
      if (viewIndex !== undefined) {
        view.scrollTop = viewIndex * state.parm7LineHeight;
      }
    }
  }
  renderParm7Window();
}

/**
 * Render the parm7 section buttons.
 * @param {Array<object>} sections
 */
export function renderParm7Sections(sections) {
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
    button.dataset.flag = section.name;
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

function getSectionMode(name) {
  if (!name) {
    return null;
  }
  const key = String(name).trim().toUpperCase();
  return SECTION_MODE_MAP[key] || null;
}

function getHighlightSections(highlights) {
  const sections = new Set();
  (highlights || []).forEach((hl) => {
    if (hl && hl.section) {
      sections.add(hl.section);
    }
  });
  return sections;
}

function pickSectionName(mode, highlights) {
  const sectionNames = getHighlightSections(highlights);
  const preferred = PARM7_SECTION_PREFS[mode] || [];
  for (const name of preferred) {
    if (sectionNames.has(name)) {
      return name;
    }
  }
  const fallback = (highlights || []).find((hl) => hl && hl.section);
  return fallback ? fallback.section : null;
}

/**
 * Auto-select a parm7 section for the current selection.
 * @param {string} mode
 * @param {Array<object>} highlights
 */
export function autoSelectParm7Section(mode, highlights) {
  if (!state.parm7Sections || !state.parm7Sections.length) {
    return;
  }
  const sectionName = pickSectionName(mode, highlights);
  if (!sectionName) {
    return;
  }
  const section = state.parm7Sections.find((entry) => entry.name === sectionName);
  if (section) {
    setParm7SectionView(section);
  }
}

/**
 * Fetch and apply parm7 highlights for a selection.
 * @param {Array<number>} serials
 * @param {string} mode
 * @returns {Promise<object|null>}
 */
export function fetchParm7Highlights(serials, mode) {
  if (!state.parm7Lines.length) {
    return Promise.resolve({ highlights: [], interaction: null });
  }
  const list = Array.isArray(serials) ? serials : serials ? [serials] : [];
  const cleanSerials = list
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value));
  if (!cleanSerials.length) {
    return Promise.resolve({ highlights: [], interaction: null });
  }
  return getParm7Highlights(cleanSerials, mode).then((result) => {
    if (!result || !result.ok) {
      const msg = result && result.error ? result.error.message : "Failed to highlight parm7";
      return Promise.reject(new Error(msg));
    }
    return {
      highlights: result.highlights || [],
      interaction: result.interaction || null,
    };
  });
}

export function applyParm7SelectionHighlights(mode, highlights) {
  if (!state.parm7Lines.length) {
    renderParm7File([]);
    return;
  }
  const safeHighlights = Array.isArray(highlights) ? highlights : [];
  autoSelectParm7Section(mode, safeHighlights);
  renderParm7File(safeHighlights);
}

export function updateParm7Highlights(serials, mode) {
  if (!state.parm7Lines.length) {
    renderParm7File([]);
    return Promise.resolve(null);
  }
  return fetchParm7Highlights(serials, mode).then((result) => {
    applyParm7SelectionHighlights(mode, result.highlights || []);
    return result.interaction || null;
  });
}
