import {
  getInitialPaths,
  getParm7Sections,
  getParm7Text,
  getUiConfig,
  hasApiMethod,
  loadSystem as apiLoadSystem,
  queryAtoms,
  selectFiles,
} from "./bridge.js";
import { resetParm7State, renderParm7File, renderParm7Sections, updateParm7FontSize } from "./parm7.js";
import { selectAtom, clearSelection } from "./selection.js";
import { state } from "./state.js";
import {
  attachSystemInfoExport,
  attachSystemInfoRowActions,
  attachSystemInfoTabs,
  loadSystemInfo,
  resetSystemInfoState,
  updateInfoFontSize,
} from "./system_info.js";
import {
  applyTheme,
  ensureViewer,
  applyStylePreset,
  highlightSerials,
  renderModel,
  render2dModel,
  resizeViewer,
} from "./viewer.js";
import {
  applyUiConfig,
  reportError,
  setLoading,
  setSelectionMode,
  setStatus,
  toggleAboutPanel,
} from "./ui.js";
import { decodeBase64 } from "./utils.js";

window.__pywebview_ready = false;
window.__pendingLoad = null;
let pywebviewWarningTimer = null;

function loadFromInputs() {
  const parm7 = document.getElementById("parm7-path").value.trim();
  const rst7 = document.getElementById("rst7-path").value.trim();
  if (!parm7) {
    reportError("Provide a parm7 path");
    return;
  }
  loadSystem(parm7, rst7 || null);
}

async function loadSystem(parm7Path, rst7Path, resname) {
  if (!hasApiMethod("load_system")) {
    reportError("pywebview API not available");
    return;
  }
  clearSelection();
  state.atomCache = new Map();
  resetSystemInfoState();
  resetParm7State();
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

  try {
    const result = await apiLoadSystem(parm7Path, rst7Path, resname);
    if (!result || !result.ok) {
      const msg = result && result.error ? result.error.message : "Failed to load";
      reportError(msg);
      setLoading(false);
      return;
    }
    console.debug(
      `load_system completed in ${(performance.now() - loadStart).toFixed(1)}ms`
    );
    if (result.view_mode === "2d") {
      const rendered = render2dModel(result.depiction, selectAtom, clearSelection);
      if (!rendered) {
        setLoading(false);
        return;
      }
      const info = result.depiction || {};
      const label = info.resname ? `${info.resname}${info.resid ? " " + info.resid : ""}` : "2D";
      const warn =
        result.warnings && result.warnings.length
          ? ` Warnings: ${result.warnings.join(", ")}`
          : "";
      setStatus(
        "success",
        `Loaded ${label} (${result.natoms} atoms, ${result.nresidues} residues).${warn}`
      );
      setLoading(false);
    } else {
      const readyViewer = await ensureViewer();
      if (!readyViewer) {
        setLoading(false);
        return;
      }
      renderModel(result.pdb_b64, selectAtom, clearSelection);
      const styleSelect = document.getElementById("style-select");
      if (styleSelect) {
        applyStylePreset(styleSelect.value, false);
      }
      resizeViewer(true);
      const warn =
        result.warnings && result.warnings.length
          ? ` Warnings: ${result.warnings.join(", ")}`
          : "";
      setStatus(
        "success",
        `Loaded ${result.natoms} atoms, ${result.nresidues} residues.${warn}`
      );
      setLoading(false);
    }
  } catch (err) {
    reportError(String(err));
    setLoading(false);
    return;
  }

  if (hasApiMethod("get_parm7_text")) {
    try {
      const textResult = await getParm7Text();
      if (!textResult || !textResult.ok) {
        const msg =
          textResult && textResult.error
            ? textResult.error.message
            : "Failed to load parm7 text";
        reportError(msg);
      } else {
        const text = decodeBase64(textResult.parm7_text_b64 || "");
        state.parm7Lines = text.split("\n");
        renderParm7File([]);
      }
    } catch (err) {
      reportError(String(err));
    }
  }

  if (hasApiMethod("get_parm7_sections")) {
    try {
      const sectionResult = await getParm7Sections();
      if (!sectionResult || !sectionResult.ok) {
        const msg =
          sectionResult && sectionResult.error
            ? sectionResult.error.message
            : "Failed to load parm7 sections";
        reportError(msg);
      } else {
        state.parm7Sections = sectionResult.sections || [];
        renderParm7Sections(state.parm7Sections);
      }
    } catch (err) {
      reportError(String(err));
    }
  }

  if (hasApiMethod("get_system_info")) {
    loadSystemInfo().catch((err) => {
      reportError(String(err));
    });
  }
}

function setInitialPaths(payload) {
  if (!payload) {
    return;
  }
  const parm7Path = payload.parm7 || payload.parm7_path || "";
  const rst7Path = payload.rst7 || payload.rst7_path || "";
  const resname = payload.resname || "";
  if (!parm7Path) {
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
  if (hasApiMethod("load_system")) {
    loadSystem(parm7Path, rst7Path || null, resname || null);
    return;
  }
  state.pendingLoad = { parm7: parm7Path, rst7: rst7Path, resname: resname };
  window.__pendingLoad = state.pendingLoad;
}

window.__setInitialPaths = setInitialPaths;

function runFilter() {
  if (state.loading) {
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
  queryAtoms(filters)
    .then((result) => {
      if (!result || !result.ok) {
        const msg = result && result.error ? result.error.message : "Query failed";
        reportError(msg);
        return;
      }
      const serials = result.serials || [];
      highlightSerials(serials);
      const truncated = result.truncated ? " (truncated)" : "";
      setStatus("success", `Found ${result.count} atoms${truncated}`);
    })
    .catch((err) => {
      reportError(String(err));
    });
}

function handleOpenDialog() {
  if (!hasApiMethod("select_files")) {
    reportError("pywebview API not available");
    return;
  }
  selectFiles()
    .then((result) => {
      if (!result || !result.ok) {
        const msg = result && result.error ? result.error.message : "Dialog cancelled";
        reportError(msg);
        return;
      }
      document.getElementById("parm7-path").value = result.parm7_path;
      document.getElementById("rst7-path").value = result.rst7_path || "";
      loadSystem(result.parm7_path, result.rst7_path || null);
    })
    .catch((err) => {
      reportError(String(err));
    });
}

function updateVisibilityButtons() {
  const waterBtn = document.getElementById("toggle-water");
  if (waterBtn) {
    waterBtn.textContent = state.hideWater ? "Show water" : "Hide water";
  }
  const hydrogenBtn = document.getElementById("toggle-hydrogen");
  if (hydrogenBtn) {
    hydrogenBtn.textContent = state.hideHydrogen ? "Show H (non-water)" : "Hide H (non-water)";
  }
}

function attachEvents() {
  if (state.eventsAttached) {
    return;
  }
  state.eventsAttached = true;
  const openBtn = document.getElementById("open-btn");
  const loadBtn = document.getElementById("load-btn");
  const clearBtn = document.getElementById("clear-btn");
  const waterBtn = document.getElementById("toggle-water");
  const hydrogenBtn = document.getElementById("toggle-hydrogen");
  const filterBtn = document.getElementById("filter-btn");
  const aboutBtn = document.getElementById("about-btn");
  const themeBtn = document.getElementById("theme-btn");
  const styleSelect = document.getElementById("style-select");
  const fontInput = document.getElementById("parm7-font-size");
  const infoFontInput = document.getElementById("info-font-size");
  if (openBtn) openBtn.addEventListener("click", handleOpenDialog);
  if (loadBtn) loadBtn.addEventListener("click", loadFromInputs);
  if (clearBtn) clearBtn.addEventListener("click", clearSelection);
  if (waterBtn) {
    waterBtn.addEventListener("click", () => {
      state.hideWater = !state.hideWater;
      updateVisibilityButtons();
      const styleSelect = document.getElementById("style-select");
      applyStylePreset(styleSelect ? styleSelect.value : state.currentStyleKey);
    });
  }
  if (hydrogenBtn) {
    hydrogenBtn.addEventListener("click", () => {
      state.hideHydrogen = !state.hideHydrogen;
      updateVisibilityButtons();
      const styleSelect = document.getElementById("style-select");
      applyStylePreset(styleSelect ? styleSelect.value : state.currentStyleKey);
    });
  }
  if (filterBtn) filterBtn.addEventListener("click", runFilter);
  if (aboutBtn) aboutBtn.addEventListener("click", () => {
    toggleAboutPanel();
    resizeViewer(false);
  });
  if (themeBtn) themeBtn.addEventListener("click", () => applyTheme(!state.darkMode));
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
  if (infoFontInput) {
    infoFontInput.addEventListener("input", (event) => {
      updateInfoFontSize(event.target.value);
    });
  }
  updateVisibilityButtons();
}

window.addEventListener("pywebviewready", async function () {
  state.pywebviewReady = true;
  window.__pywebview_ready = true;
  if (pywebviewWarningTimer) {
    window.clearTimeout(pywebviewWarningTimer);
    pywebviewWarningTimer = null;
  }
  attachEvents();
  await ensureViewer();
  setStatus("success", "Ready", "");
  applyTheme(state.darkMode);
  if (hasApiMethod("get_ui_config")) {
    getUiConfig()
      .then((result) => {
        if (result && result.ok) {
          applyUiConfig(result.config);
        }
      })
      .catch(() => {});
  }
  if (hasApiMethod("get_initial_paths")) {
    getInitialPaths()
      .then((result) => {
        if (result && result.ok && result.parm7_path) {
          setInitialPaths({
            parm7: result.parm7_path,
            rst7: result.rst7_path,
            resname: result.resname,
          });
        }
      })
      .catch(() => {});
  }
  if (state.pendingLoad) {
    const payload = state.pendingLoad;
    state.pendingLoad = null;
    window.__pendingLoad = null;
    loadSystem(payload.parm7, payload.rst7 || null, payload.resname || null);
  }
});

window.addEventListener("DOMContentLoaded", function () {
  attachEvents();
  attachSystemInfoTabs();
  attachSystemInfoExport();
  attachSystemInfoRowActions();
  if (!window.pywebview) {
    ensureViewer();
    if (!pywebviewWarningTimer) {
      pywebviewWarningTimer = window.setTimeout(() => {
        if (!state.pywebviewReady && !window.pywebview) {
          reportError("pywebview not available. Run via Python app.");
        }
        pywebviewWarningTimer = null;
      }, 1500);
    }
  }
  const fontInput = document.getElementById("parm7-font-size");
  if (fontInput) {
    updateParm7FontSize(fontInput.value);
  }
  const infoFontInput = document.getElementById("info-font-size");
  if (infoFontInput) {
    updateInfoFontSize(infoFontInput.value);
  }
  applyTheme(state.darkMode);
  setSelectionMode("Atom");
});

window.addEventListener("resize", function () {
  resizeViewer();
});
