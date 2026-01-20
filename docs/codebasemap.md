# Codebase Map

## Files, classes, and functions

`app.py`
- `_parse_args(argv)`: parse CLI args (parm7/rst7, `--log-file`, `--info-font-size`), enforce both-or-none paths.
- `_configure_logging(log_file)`: configure logging to stdout or a file.
- `create_app(initial_paths=None, info_font_size=13.0)`: build `Worker`, `Model`, `Api`, and the pywebview window.
- `main()`: entrypoint; parse args, configure logging, set initial paths, start pywebview.

`api.py`
- `_error(code, message, details=None)`: standard error payload for JS.
- `Api.__init__(model, worker, initial_paths=None, ui_config=None)`: store dependencies and UI config.
- `Api.set_window(window)`: store pywebview window for dialogs.
- `Api.get_initial_paths(payload=None)`: return CLI file paths once, then clear them.
- `Api.get_ui_config(payload=None)`: return UI config (info popup font size).
- `Api.load_system(payload)`: validate payload and run `Model.load_system` via `Worker`.
- `Api.get_atom_info(payload)`: validate payload and call `Model.get_atom_info`.
- `Api.get_atom_bundle(payload)`: validate payload and call `Model.get_atom_bundle`.
- `Api.query_atoms(payload)`: validate payload and call `Model.query_atoms` via `Worker`.
- `Api.get_residue_info(payload)`: validate payload and call `Model.get_residue_info`.
- `Api.get_parm7_text(payload=None)`: return base64 parm7 text from `Model`.
- `Api.get_parm7_sections(payload=None)`: return section metadata from `Model`.
- `Api.get_parm7_highlights(payload)`: validate serials/mode and call `Model.get_parm7_highlights`.
- `Api.select_files(payload=None)`: open parm7/rst7 file dialogs.
- `Api.log_client_error(payload)`: log client-side errors to Python logs.

`model.py`
- Constants: `CHARGE_SCALE`, `_PARM7_DESCRIPTIONS`, `_PARM7_DEPRECATED`.
- `ResidueMeta`: residue metadata dataclass; `to_dict()` returns JS payload.
- `AtomMeta`: atom metadata dataclass; `to_dict()` returns JS payload.
- `Parm7Token`: token metadata (value, line, start, end).
- `Parm7Section`: section metadata (name, format width/count, tokens).
- `ModelError`: error type with `to_result()` for API payloads.
- `_parse_int_tokens(tokens)`: parse integer token list.
- `_parse_float_tokens(tokens)`: parse float token list (Fortran D supported).
- `_parse_int_values(values)`: parse integer strings for multiprocessing use.
- `_parse_float_values(values)`: parse float strings for multiprocessing use.
- `_parse_int_token_value(token)`: parse a single token into int.
- `_parse_float_token_value(token)`: parse a single token into float.
- `_build_lj_by_type(...)`: compute LJ diagonal parameters from arrays.
- `_build_lj_by_type_from_tokens(...)`: compute LJ parameters directly from tokens.
- `compute_lj_tables(...)`: multiprocessing-friendly LJ builder.
- `_timed_call(fn, *args, **kwargs)`: measure function time.
- `_load_parm7_descriptions()`: parse section descriptions from `daux/src_parm7_ref.md`.
- `_load_parm7_deprecated_flags()`: parse deprecated flags from `daux/src_parm7_ref.md` plus overrides.
- `_guess_element(atom_name)`: infer element from atom name.
- `_safe_attr(atoms, attr)`: safe MDAnalysis attribute read.
- `Model.__init__(cpu_submit=None)`: initialize state, caches, and locks.
- `Model._parse_parm7(path)`: mmap + parse parm7 into sections/tokens.
- `Model.get_parm7_text()`: return base64 parm7 text.
- `Model.get_parm7_sections()`: return section list with descriptions and deprecated flags.
- `Model._build_parm7_highlights(meta, sections)`: base per-atom highlights.
- `Model._get_int_section(name, section)`: cache and parse int section values.
- `Model._get_float_section(name, section)`: cache and parse float section values.
- `Model._pointer_to_serial(value)`: convert parm7 pointer to atom serial.
- `Model._match_triplet(a, b, c, serials)`: order-insensitive angle match.
- `Model._match_quad(a, b, c, d, serials)`: order-insensitive dihedral match.
- `Model._add_highlight(...)`: add highlight span with de-duplication.
- `Model._add_param_highlight(...)`: highlight a parameter value by index.
- `Model._get_param_value(...)`: read float parameter value by index.
- `Model._get_ntypes(...)`: determine LJ matrix size from NB index or ACOEF.
- `Model._nonbond_index(...)`: compute flattened NB index location.
- `Model._extract_bond_params(...)`: return bond parameters for a selected pair.
- `Model._extract_angle_params(...)`: return angle parameters for a selected triplet.
- `Model._extract_dihedral_params(...)`: return dihedral terms for a selected quartet.
- `Model._extract_14_params(...)`: return SCEE/SCNB for 1-4 endpoints.
- `Model._extract_nonbonded_params(...)`: return LJ parameters for a nonbonded pair.
- `Model._highlight_nonbonded_pair(...)`: highlight NB index and LJ/HB params for pairs.
- `Model._highlight_bond_entries(...)`: highlight bond arrays and parameter sections.
- `Model._highlight_angle_entries(...)`: highlight angle arrays and parameter sections.
- `Model._highlight_dihedral_entries(...)`: highlight dihedral arrays and parameter sections.
- `Model._highlight_14_pairs(...)`: highlight dihedral entries that define 1-4 pairs.
- `Model.get_parm7_highlights(serials, mode=None)`: return highlights + interaction data for mode.
- `Model.get_atom_bundle(serial)`: return atom metadata + base highlights.
- `Model.load_system(parm7_path, rst7_path)`: load MDAnalysis `Universe`, parse parm7, build LJ tables, build PDB, store state.
- `Model.get_atom_info(serial)`: return atom metadata.
- `Model.query_atoms(filters, max_results=50000)`: filter atoms by strings/ranges.
- `Model.get_residue_info(resid)`: return residue metadata and serials.

`pdb_writer.py`
- `PdbWriterError`: error type.
- `_format_atom_name(name)`: pad/truncate atom name to PDB width.
- `_format_resname(resname)`: pad/truncate residue name.
- `_format_element(element)`: format element symbol column.
- `write_pdb(atom_metas)`: build a PDB text block from atom metadata.

`worker.py`
- `Worker.__init__(max_workers=1, max_processes=0)`: thread pool + optional process pool.
- `Worker.submit(fn, *args, **kwargs)`: submit work to thread pool.
- `Worker.submit_cpu(fn, *args, **kwargs)`: submit work to process pool when enabled.

`web/app.js`
- State: viewer/model references, selection state, caches, parm7 virtualization state, theme state.
- Constants: `SECTION_MODE_MAP`, `stylePresets`, highlight colors/opacity.
- `setStatus(level, message, detail)`: update status bar text.
- `reportError(message)`: show UI error and log to Python.
- `escapeHtml(text)`: HTML escape helper.
- `formatNumber(value)`: format to 3 decimals, no scientific notation.
- `requestRender()`: schedule a single viewer render via animation frame.
- `getViewerBackgroundColor()`: resolve CSS background color.
- `getLabelStyle()`: resolve CSS label styling.
- `applyTheme(isDark)`: toggle dark/light mode and update viewer background.
- `getHighlightAtomRadius()`: size highlight spheres based on style.
- `getHighlightBondRadius()`: size highlight cylinders based on style.
- `addHighlightSphere(center, radius)`: add translucent atom overlay.
- `addHighlightCylinder(start, end, radius)`: add translucent bond overlay.
- `atomPosition(atom)`: return position object for 3Dmol atom.
- `midpoint(posA, posB)`: compute midpoint for labels.
- `centroid(positions)`: compute centroid for labels.
- `addViewerLabel(text, position)`: add single-line viewer label.
- `addViewerLabelLines(lines, position)`: add stacked labels with offsets.
- `cacheAtom(serial, payload)`: LRU cache for atom bundle responses.
- `setSelectionMode(mode)`: update mode title and tabs.
- `getSectionMode(name)`: map parm7 flag to a selection mode.
- `buildAtomIndex()`: build serial/index/bond lookup maps.
- `areBonded(serialA, serialB)`: check bond adjacency in the current model.
- `isDihedralChain(serials)`: check if four atoms form a bonded chain.
- `buildAdjacency(serials)`: build adjacency list for given serials.
- `findBondPath(serials)`: find a bonded path ordering for angle/dihedral.
- `bondDistance(serialA, serialB, maxDepth=3)`: shortest bond distance up to 3 hops.
- `selectionLabel(serial)`: format a human-readable atom label.
- `renderInteractionTable(headers, rows)`: build HTML table for interaction values.
- `formatInteractionDetails(mode, interaction)`: format mode-specific parameter tables.
- `atomLabelText(serial, atomRecord)`: label for atom selection.
- `renderSelectionSummary()`: update right panel summary for current mode.
- `updateSelectionState(serial)`: update selection and resolve mode.
- `resetSelectionState()`: clear selection and summary.
- `attachEmptyClickHandler()`: track empty clicks without clearing selection.
- `getParm7ViewLineCount()`: line count for current view.
- `getParm7LineIndex(viewIndex)`: map view index to actual line index.
- `getParm7ViewIndex(lineIndex)`: map line index to view index.
- `setParm7SectionView(section)`: restrict parm7 view to a single section.
- `updateParm7FontSize(value)`: update CSS var and rebuild virtualization.
- `applyUiConfig(config)`: apply Python-provided UI config.
- `ensureSectionTooltip()`: create tooltip element once.
- `showSectionTooltip(button, text)`: display and position tooltip.
- `hideSectionTooltip()`: hide tooltip.
- `renderParm7File(highlights)`: ensure parm7 view exists and apply highlights.
- `buildParm7View()`: set up virtualization containers and sizing.
- `renderParm7Line(viewIndex)`: render a single parm7 line with highlights.
- `renderParm7Window()`: render visible window of parm7 lines.
- `onParm7Scroll()`: throttled scroll handler.
- `applyParm7Highlights(highlights)`: update highlight map and scroll to first match.
- `renderParm7Sections(sections)`: render section buttons with tooltips and colors.
- `updateParm7Highlights(serials, mode)`: fetch highlights + interaction from Python.
- `setLoading(isLoading)`: disable/enable UI controls.
- `load3Dmol()`: load vendor 3Dmol script.
- `ensureViewer()`: initialize 3Dmol viewer if missing.
- `attachZoomHandler()`: intercept wheel and apply zoom.
- `resizeViewer(renderNow=true)`: resize viewer on layout changes.
- `decodeBase64(b64)`: base64 decode helper.
- `applyBaseStyle()`: apply base viewer style.
- `applyStylePreset(key, renderNow=true)`: apply style presets.
- `clearHighlights()`: clear labels, overlays, selection, and parm7 highlights.
- `highlightSerials(serials)`: highlight atoms/bonds without changing colors.
- `buildBondLabels(bonds)`: build bond parameter labels.
- `buildAngleLabels(angles)`: build angle parameter labels.
- `buildDihedralLabels(dihedrals)`: build dihedral parameter labels (utility).
- `buildDihedralIndexLabel(serials)`: build single dihedral index label.
- `buildNonbondedLabels(nonbonded)`: build nonbonded parameter labels.
- `buildOneFourLabels(oneFour)`: build 1-4 parameter labels.
- `renderInteractionLabels(interaction)`: add selection mode labels to viewer.
- `renderModel(pdbB64)`: load PDB into 3Dmol and enable picking.
- `updateAtomDetails(atom)`: render Atom panel and parameter table.
- `updateAboutPanel(atom)`: render short charge/LJ explanation.
- `toggleAboutPanel()`: show/hide About panel.
- `addHistory(atom)`: placeholder (no-op).
- `applyAtomSelection(atom, highlights)`: update selection summary and parm7 highlights.
- `selectAtom(serial)`: click handler, fetch atom bundle and update UI.
- `loadFromInputs()`: read path inputs and load system.
- `loadSystem(parm7Path, rst7Path)`: call Python load, render model, load parm7 text/sections.
- `setInitialPaths(payload)`: set CLI paths and trigger load.
- `runFilter()`: query atoms using filter inputs (if present).
- `handleOpenDialog()`: open native file dialog.
- `attachEvents()`: attach UI event handlers.
- Event listeners: `pywebviewready`, `DOMContentLoaded`, `resize`.

`web/index.html`
- Layout only; defines toolbar, status, viewer, info panel, About panel, and parm7 panel.

`web/styles.css`
- Styling only; defines layout, theme variables, mode colors, and table/tooltip styles.

`web/vendor/3Dmol-min.js`
- Third-party 3Dmol bundle (minified).

`tests/test_mapping.py`
- `test_pdb_writer_serials_order()`: verify PDB serial ordering.

`README.md`
- Usage documentation; no functions.

`plan.md`
- Planning notes; no functions.

`pyproject.toml`
- Project metadata and dependencies; no functions.

`uv.lock`
- Locked dependency graph; no functions.

`.gitignore`
- Git ignore rules; no functions.

`.claude/agents/0planner.md`
- Planner instructions; no functions.

`.claude/agents/1planner.md`
- Planner instructions; no functions.

`.claude/agents/0refactorer.md`
- Refactorer instructions; no functions.

`.claude/agents/coder.md`
- Coder instructions; no functions.

`.claude/plan.md`
- Planner notes; no functions.

`.claude/pprompt.txt`
- Prompt context; no functions.

`docs/codebasemap.md`
- Codebase map (this file); no functions.

`daux/src_parm7_ref.md`
- Parm7 format reference; no functions.

`daux/0prompt.md`
- Prompt/context notes; no functions.

`daux/binder_IDC-5270.parm7`
- Sample parm7 topology; no functions.

`daux/binderref_IDC-5270.rst7`
- Sample rst7 coordinates; no functions.

`__pycache__/model.cpython-312.pyc`
- Python bytecode artifact; no functions.

`__pycache__/worker.cpython-312.pyc`
- Python bytecode artifact; no functions.

`__pycache__/api.cpython-312.pyc`
- Python bytecode artifact; no functions.

`__pycache__/pdb_writer.cpython-312.pyc`
- Python bytecode artifact; no functions.

`tests/__pycache__/test_mapping.cpython-312-pytest-9.0.2.pyc`
- Python bytecode artifact; no functions.

`.pytest_cache/README.md`
- Pytest cache readme; no functions.

`.pytest_cache/.gitignore`
- Pytest cache ignore; no functions.

`.pytest_cache/CACHEDIR.TAG`
- Pytest cache tag; no functions.

`.pytest_cache/v/cache/nodeids`
- Pytest cache node IDs; no functions.

`.venv/`
- Virtual environment directory (generated; not enumerated).

## Class and module interactions

- `app.py` wires `Worker`, `Model`, and `Api` together and exposes `Api` to pywebview.
- `Api` acts as the boundary between JS and Python, validating inputs and delegating to `Model` through `Worker`.
- `Worker` provides thread/process pools for background work; `Api` uses it for `load_system` and `query_atoms`.
- `Model` owns all parsed data and computed metadata, uses `MDAnalysis` for structure loading, and uses `write_pdb` to build the PDB for 3Dmol.
- `web/app.js` calls the `Api` methods through pywebview, then renders state to the DOM and 3Dmol viewer.
- `web/index.html` and `web/styles.css` define the layout/appearance for the JS logic.

## Runtime flows

### Startup

1. `app.py:main` parses CLI args, configures logging, and calls `create_app`.
2. `create_app` instantiates `Worker`, `Model`, and `Api`, then creates a pywebview window with `Api` bound as `js_api`.
3. pywebview loads `web/index.html`, which loads `web/app.js`.
4. `pywebviewready` in `web/app.js` attaches UI events, creates the viewer (`ensureViewer`), applies theme, fetches UI config (`Api.get_ui_config`), and fetches initial paths (`Api.get_initial_paths`).
5. If initial paths exist, `setInitialPaths` triggers `loadSystem`.

### Parm7 + rst7 loading

1. `loadSystem(parm7Path, rst7Path)` (JS) clears UI state and calls `Api.load_system`.
2. `Api.load_system` submits `Model.load_system` to the `Worker` thread pool.
3. `Model.load_system`:
   - Runs `MDAnalysis.Universe(parm7, rst7)` and `_parse_parm7` in a local `ThreadPoolExecutor`.
   - `_parse_parm7` uses mmap to parse sections and tokens for relevant flags.
   - Builds LJ tables from `ATOM_TYPE_INDEX`, `NONBONDED_PARM_INDEX`, `LENNARD_JONES_ACOEF`, and `LENNARD_JONES_BCOEF`.
   - Builds `AtomMeta` and `ResidueMeta` lists and caches (`_meta_by_serial`, `_residue_index`).
   - Writes PDB text via `write_pdb` and stores base64 text.
4. JS receives `{pdb_b64, natoms, nresidues}` and calls:
   - `renderModel` to load the PDB into 3Dmol and rebuild the atom index.
   - `applyStylePreset` and `resizeViewer` for visual setup.
   - `Api.get_parm7_text` and `Api.get_parm7_sections` to populate the parm7 panel and section buttons.

### Selection event (atom click)

Shared selection path
1. 3Dmol click handler (`renderModel`) calls `selectAtom(serial)`.
2. `selectAtom` updates selection state (`updateSelectionState`), updates the summary, and highlights atoms/bonds (`highlightSerials`).
3. `selectAtom` loads atom data via `Api.get_atom_bundle` (cached when possible).
4. `applyAtomSelection` updates `currentAtomInfo`, renders details/about, and updates parm7 highlights. If the selection has multiple atoms, it calls `updateParm7Highlights` to fetch mode-specific highlights and interactions.
5. `updateParm7Highlights` calls `Api.get_parm7_highlights`, which delegates to `Model.get_parm7_highlights` to return highlight spans and interaction data.
6. JS updates the parm7 viewer, the right-hand summary table (`formatInteractionDetails`), and renders viewer labels (`renderInteractionLabels`).

Mode-specific behavior
- Atom:
  - `updateSelectionState` sets mode to `Atom` with a single serial.
  - `get_atom_bundle` returns per-atom highlights from `_build_parm7_highlights`.
  - `updateAtomDetails` renders the Atom panel with charge/Rmin/epsilon table; no parameter labels beyond the atom label.
- Bond:
  - Mode is `Bond` when two atoms are bonded (`areBonded`).
  - `Model._highlight_bond_entries` highlights bond arrays and `BOND_FORCE_CONSTANT`/`BOND_EQUIL_VALUE`.
  - `Model._extract_bond_params` returns k and r0 values; `formatInteractionDetails` renders them in the table.
  - `buildBondLabels` adds bond parameter labels at the midpoint.
- Angle:
  - Mode is `Angle` when `findBondPath` finds a 3-atom chain.
  - `Model._highlight_angle_entries` highlights angle arrays and `ANGLE_FORCE_CONSTANT`/`ANGLE_EQUIL_VALUE`.
  - `Model._extract_angle_params` returns k and theta0; `buildAngleLabels` labels the angle center.
- Dihedral:
  - Mode is `Dihedral` when `findBondPath` finds a 4-atom chain.
  - `Model._highlight_dihedral_entries` highlights dihedral arrays and dihedral parameter sections.
  - `Model._extract_dihedral_params` returns all dihedral terms; the right panel lists all terms in a table.
  - Viewer label uses `buildDihedralIndexLabel` to show only the dihedral indices.
- 1-4 Nonbonded:
  - Mode is `1-4 Nonbonded` when two atoms are distance 3 in bond graph (`bondDistance`).
  - `Model._extract_14_params` returns SCEE/SCNB from dihedral entries defining 1-4 pairs.
  - `Model._highlight_14_pairs` highlights those dihedral entries and `SCEE_SCALE_FACTOR`/`SCNB_SCALE_FACTOR`.
  - `Model._highlight_nonbonded_pair` highlights `NONBONDED_PARM_INDEX` and LJ A/B (or HBOND) entries for the pair.
  - `formatInteractionDetails` renders SCEE/SCNB plus LJ values; labels show 1-4 terms and LJ values.
- Non-bonded:
  - Mode is `Non-bonded` for two atoms that are not bonded and not 1-4.
  - `Model._highlight_nonbonded_pair` highlights `NONBONDED_PARM_INDEX` and LJ/HB parameters.
  - `Model._extract_nonbonded_params` returns type indices, A/B, Rmin, epsilon for the pair.
  - `buildNonbondedLabels` labels LJ values at the pair midpoint.
