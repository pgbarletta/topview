# Codebase Map

## Files, classes, and functions

`topview/app.py`
- `_parse_args(argv)`: parse CLI args (parm7/rst7, `--log-file`, `--info-font-size`), enforce both-or-none paths.
- `_configure_logging(log_file)`: configure logging to stdout or a file.
- `create_app(initial_paths=None, info_font_size=13.0)`: build `Worker`, `Model`, `Api`, and the pywebview window.
- `main()`: entrypoint; parse args, configure logging, set initial paths, start pywebview.

`topview/bridge.py`
- `error_result(code, message, details=None)` via `topview.errors` for standard payloads.
- `Api.__init__(model, worker, initial_paths=None, initial_resname=None, ui_config=None)`: store dependencies and UI config.
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
- `Api.get_system_info(payload=None)`: return system info tables.
- `Api.get_system_info_selection(payload)`: selection for system info table rows.
- `Api.save_system_info_csv(payload)`: save CSV export.
- `Api.select_files(payload=None)`: open parm7/rst7 file dialogs.
- `Api.log_client_error(payload)`: log client-side errors to Python logs.

`topview/model/model.py`
- `Model.__init__(cpu_submit=None)`: initialize state, caches, and locks.
- `Model.load_system(parm7_path, rst7_path, resname=None)`: load MDAnalysis `Universe`, parse parm7, build LJ tables, build PDB/depiction, store state.
- `Model.get_atom_info(serial)`: return atom metadata.
- `Model.get_atom_bundle(serial)`: return atom metadata + base highlights.
- `Model.get_parm7_text()`: return base64 parm7 text.
- `Model.get_parm7_sections()`: return section list with descriptions and deprecated flags.
- `Model.get_parm7_highlights(serials, mode=None)`: return highlights + interaction data for mode (Atom/Bond/Angle/Dihedral/Improper/1-4/Non-bonded).
- `Model.query_atoms(filters, max_results=50000)`: filter atoms by strings/ranges.
- `Model.get_residue_info(resid)`: return residue metadata and serials.
- `Model.get_system_info()`: return system info tables (builds in background on load).
- `Model.get_system_info_selection(table, row_index, cursor=0)`: selection for system info row.
- `Model._get_system_info_selection_index()`: lazy build selection index.
- `Model._get_bond_adjacency()`: lazy build bond adjacency for improper/rotatable logic.

`topview/model/highlights.py`
- `HighlightEngine`: compute parm7 highlights and interaction payloads.
- Supports modes: Atom, Bond, Angle, Dihedral, Improper, 1-4 Nonbonded, Non-bonded.
- Improper support: detects central-first improper selection and filters dihedral records by bonding adjacency.

`topview/model/state.py`
- `ResidueMeta`, `AtomMeta`, `Parm7Token`, `Parm7Section` dataclasses.
- `ModelState` includes caches, system info futures, and `bond_adjacency`.

`topview/model/query.py`
- `query_atoms(...)`: filter atoms by name/type/charge/residue criteria.

`topview/services/loader.py`
- `load_system_data(...)`: load MDAnalysis universe, parse parm7, build metadata, PDB, and (optional) depiction.

`topview/services/system_info.py`
- `build_system_info_tables(...)`: build Info-panel tables from parm7 sections.
- Tables: `atom_types`, `bond_types`, `angle_types`, `dihedral_types`, `improper_types`, `one_four_nonbonded`, `nonbonded_pairs`.
- Dihedral table includes `amber_rotatable` (T/F) computed from `is_rotable.md` algorithm (heavy central bond, torsion presence, non-overlapping terminal neighbor sets).

`topview/services/system_info_selection.py`
- `build_system_info_selection_index(...)`: build lookup tables for row-to-selection mapping.
- Includes improper selection mapping (central-first ordering).

`topview/services/pdb_writer.py`
- `write_pdb(atom_metas)`: build a PDB text block from atom metadata with stable serial ordering.

`topview/worker.py`
- `Worker.__init__(max_workers=1, max_processes=0)`: thread pool + optional process pool.
- `Worker.submit(fn, *args, **kwargs)`: submit work to thread pool.
- `Worker.submit_cpu(fn, *args, **kwargs)`: submit work to process pool when enabled.

`web/src/app.js`
- Bootstraps UI, loads system, attaches event handlers.

`web/src/selection.js`
- Selection state machine for Atom/Bond/Angle/Dihedral/Improper/1-4/Non-bonded.
- Improper selection: central atom first, then 3 bonded neighbors.

`web/src/viewer.js`
- 3Dmol viewer management and highlighting.
- Theme-aware highlight color/opacity (higher contrast in light/dark modes).
- Improper label rendering and central-to-neighbor highlight lines.

`web/src/system_info.js`
- Renders Info tables with sortable headers (single-column sort; special `ijkl indices` sorting).
- Handles row selection and highlight matching.

`web/src/parm7.js`
- Parm7 panel virtualization + highlighting + auto section selection.

`web/src/ui.js`
- Status bar updates, selection summary rendering, parameter tables (including Improper).

`web/src/constants.js`
- UI constants, section→mode mapping, style presets.

`web/src/state.js`
- UI state store (selection, caches, system info, sorting state).

`web/index.html`
- Layout: toolbar, status, viewer, selection panel, info panel, parm7 panel.
- Mode tabs include Improper.

`web/styles.css`
- Styling, theme variables, mode colors, system info sorting arrows, highlight contrast variables.

`web/vendor/3Dmol-min.js`
- Third-party 3Dmol bundle (minified).

`tests/test_mapping.py`
- `test_pdb_writer_serials_order()`: verify PDB serial ordering.

`tests/test_improper_selection.py`
- Improper selection index ordering and mapping.

`tests/test_rotatable_dihedral.py`
- Rotatable-bond detection and dihedral table column presence.

`README.md`
- Usage documentation.

`plan.md`
- Planning notes (updated per feature requests).

`pyproject.toml`
- Project metadata and dependencies.

`uv.lock`
- Locked dependency graph.

`.gitignore`
- Git ignore rules.

`.claude/agents/planner.md`
- Planner instructions.

`.claude/agents/coder.md`
- Coder instructions.

`docs/codebasemap.md`
- Codebase map (this file).

`daux/src_parm7_ref.md`
- Parm7 format reference.

`daux/binder_IDC-5270.parm7`
- Sample parm7 topology.

`daux/binderref_IDC-5270.rst7`
- Sample rst7 coordinates.
