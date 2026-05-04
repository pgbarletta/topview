import { logClientError } from "./bridge.js";
import { CHARGE_SCALE } from "./constants.js";
import { state } from "./state.js";
import { escapeHtml, formatNumber, distance, angleDegrees, dihedralDegrees } from "./utils.js";

/**
 * Update the status bar contents.
 * @param {"error"|"success"|"loading"|string} level
 * @param {string} message
 * @param {string=} detail
 */
export function setStatus(level, message, detail) {
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

/**
 * Report an error to the UI and Python log.
 * @param {string} message
 */
export function reportError(message) {
  const detail = String(message);
  setStatus("error", "Error occurred.", "See log output for details.");
  console.error(detail);
  logClientError(detail).catch(() => {});
}

/**
 * Set the current selection mode and update tabs.
 * @param {string} mode
 */
export function setSelectionMode(mode) {
  state.selectionMode = mode;
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

/**
 * Render a parameter table.
 * @param {Array<string>} headers
 * @param {Array<Array<string|null>>} rows
 * @returns {string}
 */
export function renderInteractionTable(headers, rows) {
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

function _computeMeasurement(mode, interaction) {
  if (state.viewMode !== "3d") {
    return null;
  }
  let serials = null;
  if (mode === "Bond" && Array.isArray(interaction.bonds) && interaction.bonds.length) {
    serials = interaction.bonds[0].serials;
  } else if (mode === "Angle" && Array.isArray(interaction.angles) && interaction.angles.length) {
    serials = interaction.angles[0].serials;
  } else if (mode === "Dihedral" && Array.isArray(interaction.dihedrals) && interaction.dihedrals.length) {
    serials = interaction.dihedrals[0].serials;
  } else if (mode === "Improper" && Array.isArray(interaction.dihedrals) && interaction.dihedrals.length) {
    serials = interaction.dihedrals[0].serials;
  } else if (mode === "1-4 Nonbonded" && Array.isArray(interaction.one_four) && interaction.one_four.length) {
    serials = interaction.one_four[0].serials;
  } else if (mode === "Non-bonded" && interaction.nonbonded && interaction.nonbonded.serials) {
    serials = interaction.nonbonded.serials;
  }
  if (!serials || !serials.length) {
    return null;
  }
  const positions = serials.map((s) => {
    const atom = state.atomBySerial.get(s);
    return atom ? { x: atom.x, y: atom.y, z: atom.z } : null;
  });
  if (positions.some((p) => !p)) {
    return null;
  }
  if ((mode === "Bond" || mode === "1-4 Nonbonded" || mode === "Non-bonded") && positions.length === 2) {
    const d = distance(positions[0], positions[1]);
    return d !== null ? formatNumber(d) + " \u00C5" : null;
  }
  if (mode === "Angle" && positions.length === 3) {
    const a = angleDegrees(positions[0], positions[1], positions[2]);
    return a !== null ? formatNumber(a) + "\u00B0" : null;
  }
  if ((mode === "Dihedral" || mode === "Improper") && positions.length === 4) {
    const d = dihedralDegrees(positions[0], positions[1], positions[2], positions[3]);
    return d !== null ? formatNumber(d) + "\u00B0" : null;
  }
  return null;
}

/**
 * Format interaction details for the selection summary.
 * @param {string} mode
 * @param {object|null} interaction
 * @returns {string}
 */
export function formatInteractionDetails(mode, interaction) {
  if (!interaction || interaction.mode !== mode) {
    return "";
  }
  const measured = _computeMeasurement(mode, interaction);
  const measuredCol = measured || null;
  let headers = [];
  const rows = [];
  if (mode === "Bond") {
    headers = ["k", "r0", "Measured"];
    (interaction.bonds || []).forEach((bond) => {
      rows.push([formatNumber(bond.force_constant), formatNumber(bond.equil_value), measuredCol]);
    });
  } else if (mode === "Angle") {
    headers = ["k", "theta0", "Measured"];
    (interaction.angles || []).forEach((angle) => {
      rows.push([formatNumber(angle.force_constant), formatNumber(angle.equil_value), measuredCol]);
    });
  } else if (mode === "Dihedral") {
    headers = ["k", "n", "phase", "SCEE", "SCNB", "Measured"];
    (interaction.dihedrals || []).forEach((term) => {
      rows.push([
        formatNumber(term.force_constant),
        formatNumber(term.periodicity),
        formatNumber(term.phase),
        formatNumber(term.scee),
        formatNumber(term.scnb),
        measuredCol,
      ]);
    });
  } else if (mode === "Improper") {
    headers = ["k", "n", "phase", "SCEE", "SCNB", "Measured"];
    (interaction.dihedrals || []).forEach((term) => {
      rows.push([
        formatNumber(term.force_constant),
        formatNumber(term.periodicity),
        formatNumber(term.phase),
        formatNumber(term.scee),
        formatNumber(term.scnb),
        measuredCol,
      ]);
    });
  } else if (mode === "1-4 Nonbonded") {
    headers = ["SCEE", "SCNB", "Rmin", "eps", "A", "B", "Measured"];
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
        measuredCol,
      ]);
    });
  } else if (mode === "Non-bonded") {
    headers = ["Rmin", "eps", "A", "B", "Measured"];
    const nb = interaction.nonbonded || null;
    if (nb) {
      rows.push([
        formatNumber(nb.rmin),
        formatNumber(nb.epsilon),
        formatNumber(nb.acoef),
        formatNumber(nb.bcoef),
        measuredCol,
      ]);
    }
  }

  return renderInteractionTable(headers, rows);
}

/**
 * Build a display label for a selected atom.
 * @param {number} serial
 * @returns {string}
 */
export function selectionLabel(serial) {
  const cached = state.atomCache.get(serial);
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

/**
 * Render the right-hand summary panel.
 */
export function renderSelectionSummary() {
  const details = document.getElementById("atom-details");
  if (!details) {
    return;
  }
  if (!state.selectionSerials.length) {
    details.textContent = "No atom selected.";
    return;
  }
  let displaySerials = state.selectionSerials;
  if (state.selectionMode === "Atom" && state.currentAtomInfo) {
    updateAtomDetails(state.currentAtomInfo);
    return;
  }
  if (state.currentInteraction) {
    if (
      state.selectionMode === "Bond" &&
      Array.isArray(state.currentInteraction.bonds) &&
      state.currentInteraction.bonds.length
    ) {
      displaySerials = state.currentInteraction.bonds[0].serials || displaySerials;
    } else if (
      state.selectionMode === "Angle" &&
      Array.isArray(state.currentInteraction.angles) &&
      state.currentInteraction.angles.length
    ) {
      displaySerials = state.currentInteraction.angles[0].serials || displaySerials;
    } else if (
      state.selectionMode === "Dihedral" &&
      Array.isArray(state.currentInteraction.dihedrals) &&
      state.currentInteraction.dihedrals.length
    ) {
      displaySerials = state.currentInteraction.dihedrals[0].serials || displaySerials;
    } else if (
      state.selectionMode === "Improper" &&
      Array.isArray(state.currentInteraction.dihedrals) &&
      state.currentInteraction.dihedrals.length
    ) {
      displaySerials = state.currentInteraction.dihedrals[0].serials || displaySerials;
    } else if (
      state.selectionMode === "1-4 Nonbonded" &&
      Array.isArray(state.currentInteraction.one_four) &&
      state.currentInteraction.one_four.length
    ) {
      displaySerials = state.currentInteraction.one_four[0].serials || displaySerials;
    } else if (
      state.selectionMode === "Non-bonded" &&
      state.currentInteraction.nonbonded &&
      state.currentInteraction.nonbonded.serials
    ) {
      displaySerials = state.currentInteraction.nonbonded.serials || displaySerials;
    }
  }
  let title = "";
  if (state.selectionMode === "Bond") {
    title = "Bonded atoms";
  } else if (state.selectionMode === "Angle") {
    title = "Angle atoms";
  } else if (state.selectionMode === "Dihedral") {
    title = "Dihedral atoms";
  } else if (state.selectionMode === "Improper") {
    title = "Improper atoms";
  } else if (state.selectionMode === "1-4 Nonbonded") {
    title = "1-4 nonbonded atoms";
  } else if (state.selectionMode === "Non-bonded") {
    title = "Non-bonded atoms";
  }
  const lines = (displaySerials || []).map((serial, idx) => {
    return `<div>Atom ${idx + 1}: <strong>${escapeHtml(selectionLabel(serial))}</strong></div>`;
  });
  const left = `<div class="selection-summary"><div>${escapeHtml(title)}</div>${lines.join(
    ""
  )}</div>`;
  const right = formatInteractionDetails(state.selectionMode, state.currentInteraction);
  let ljBlock = "";
  if (state.selectionMode === "Non-bonded" && state.selectionSerials.length === 2) {
    const c0 = state.atomCache.get(state.selectionSerials[0]);
    const c1 = state.atomCache.get(state.selectionSerials[1]);
    if (c0 && c0.atom && c1 && c1.atom) {
      ljBlock = buildNonbondedLjFormulaBlock(c0.atom, c1.atom);
    }
  }
  if (right) {
    details.innerHTML = `<div class="selection-summary-grid">${left}<div class="selection-details">${right}</div></div>${ljBlock}`;
  } else {
    details.innerHTML = `${left}${ljBlock}`;
  }
}

/**
 * Update the atom details panel.
 * @param {object} atom
 */
export function updateAtomDetails(atom) {
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
    `Charge raw (e*${CHARGE_SCALE})`,
    "Charge (e)",
    "Rmin/2 (Angstrom)",
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
      chargeCell = `${rawNumber} / ${CHARGE_SCALE} = ${chargeValue} e`;
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
  const acoefText =
    parm7.lj_a_coef !== null && parm7.lj_a_coef !== undefined
      ? formatNumber(parm7.lj_a_coef)
      : null;
  const bcoefText =
    parm7.lj_b_coef !== null && parm7.lj_b_coef !== undefined
      ? formatNumber(parm7.lj_b_coef)
      : null;

  const leftHtml = leftLines.join("");
  const rightHtml = renderInteractionTable(chargeHeaders, [
    [rawChargeCell, chargeCell, rminCell, epsilonCell],
  ]);
  let ljBlock = "";
  if (parm7.atom_type_index && acoefText !== null && bcoefText !== null) {
    ljBlock = buildLjFormulaBlock(acoefText, bcoefText, rminCell, epsilonCell);
  }
  details.innerHTML = `<div class="atom-details-grid"><div class="atom-details-column">${leftHtml}</div><div class="atom-details-column">${rightHtml}</div></div>${ljBlock}`;
}

function buildLjFormulaBlock(acoefText, bcoefText, rminText, epsilonText) {
  const rminPart = rminText !== null ? `Rmin/2 = ${rminText} Angstrom` : "Rmin/2 N/A";
  const epsPart = epsilonText !== null ? `epsilon = ${epsilonText} kcal/mol` : "epsilon N/A";
  return `<div class="lj-formula-block">
    <div>Rmin/2 and epsilon use diagonal LJ parameters from LENNARD_JONES_ACOEF and LENNARD_JONES_BCOEF via NONBONDED_PARM_INDEX.</div>
    <div class="about-formula">Rmin/2 = (2 * A / B)^(1/6) / 2, epsilon = B^2 / (4 * A)</div>
    <div>A = ${escapeHtml(acoefText)}, B = ${escapeHtml(bcoefText)} → ${rminPart}, ${epsPart}.</div>
  </div>`;
}

function buildNonbondedLjFormulaBlock(atom1, atom2) {
  const p1 = atom1.parm7 || {};
  const p2 = atom2.parm7 || {};
  const r1 = p1.lj_rmin;
  const e1 = p1.lj_epsilon;
  const r2 = p2.lj_rmin;
  const e2 = p2.lj_epsilon;
  if (r1 == null || e1 == null || r2 == null || e2 == null) {
    return "";
  }
  const r1Text = formatNumber(r1);
  const e1Text = formatNumber(e1);
  const r2Text = formatNumber(r2);
  const e2Text = formatNumber(e2);
  if (r1Text === null || e1Text === null || r2Text === null || e2Text === null) {
    return "";
  }
  const label1 = `#${atom1.serial} ${atom1.atom_name || ""}`.trim();
  const label2 = `#${atom2.serial} ${atom2.atom_name || ""}`.trim();
  return `<div class="lj-formula-block">
    <div>Non-bonded LJ combining rules: Rmin/2_ij = Rmin/2_1 + Rmin/2_2, epsilon_ij = sqrt(eps_1 * eps_2).</div>
    <div>Atom ${escapeHtml(label1)}: Rmin/2 = ${escapeHtml(r1Text)} Angstrom, eps = ${escapeHtml(e1Text)} kcal/mol.</div>
    <div>Atom ${escapeHtml(label2)}: Rmin/2 = ${escapeHtml(r2Text)} Angstrom, eps = ${escapeHtml(e2Text)} kcal/mol.</div>
  </div>`;
}

/**
 * Toggle UI controls while loading.
 * @param {boolean} isLoading
 */
export function setLoading(isLoading) {
  state.loading = Boolean(isLoading);
  const disabled = state.loading;
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

/**
 * Apply UI configuration from the backend.
 * @param {object} config
 */
export function applyUiConfig(config) {
  if (!config) {
    return;
  }
  const size = Number(config.info_font_size);
  if (!Number.isNaN(size) && size > 0) {
    document.documentElement.style.setProperty("--info-pop-font-size", `${size}pt`);
    const input = document.getElementById("info-font-size");
    if (input) {
      input.value = String(Math.round(size));
    }
  }
}
