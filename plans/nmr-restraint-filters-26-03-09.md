# NMR Restraint Filters - 26-03-09

## 1) Feature summary

Per `codebase-docs/codebasemap.md`:
- `topview/services/nmr_restraints.py` is the source of truth for Amber `&rst` parsing/classification.
- `topview/services/loader.py` owns NMR payload assembly for 3D loads.
- `web/src/app.js`, `web/src/state.js`, and `web/src/viewer.js` own the current NMR overlay UI/rendering path.
- The current behavior in “Default 3D presentation” is a single yellow NMR overlay with a binary show/hide button.

Per `codebase-docs/assets/architecture-overview.mmd`, `codebase-docs/assets/main-execution-sequence.mmd`, and `codebase-docs/assets/module-dependencies.mmd`, the load/render path is:
- `app.js` -> `bridge.py` -> `model.py` -> `loader.py` -> `nmr_restraints.py`
- NMR overlays are rendered entirely in `web/src/viewer.js`

What changes for the user:
- NMR restraints are classified by effective atom count into `distance`, `angle`, or `dihedral`.
- A trailing `0` in `iat` is treated as a sentinel and discarded before classification.
- Distance restraints render yellow, angle restraints pink, dihedral restraints purple.
- The current show/hide NMR button becomes a dropdown with:
  - `Hide all`
  - `Show all`
  - `Show distance`
  - `Show angle`
  - `Show dihedral`
- Each visible restraint shows the equilibrium value from `r2` as just the number, with no unit suffix.

What changes internally:
- Python parser logic changes in `topview/services/nmr_restraints.py` to trim a trailing sentinel zero and expose an explicit display value derived from `r2`.
- Existing load payloads from `topview/services/loader.py` are extended, not replaced.
- JS UI state changes from a binary NMR visible flag to a filter mode.
- `web/src/viewer.js` filters overlays by type and applies per-kind colors/labels.

## 2) Impacted components and “why”

### `topview/services/nmr_restraints.py`
- Responsibility: parse and validate Amber `&rst` blocks.
- Changes:
  - modify `NmrRestraint`
  - update `_parse_iat(...)`
  - preserve `_classify_restraint(...)`
  - update `_parse_restraint_block(...)`
  - update `to_dict()`
- Why:
  - classification belongs in Python per the Python-first rule in `codebase-docs/codebasemap.md`
  - the trailing-zero rule is a parsing rule, not a viewer rule

### `topview/services/loader.py`
- Responsibility: build `SystemLoadResult`, including `nmr_restraints` and `nmr_summary`.
- Changes:
  - no API or control-flow rewrite
  - verify the enriched `record.to_dict()` output is passed through unchanged
- Why:
  - loader is the documented source of the NMR payload handed to the model/frontend

### `topview/model/model.py`
- Responsibility: store and return load results.
- Changes:
  - no new method expected
  - confirm enriched NMR payload is forwarded intact
- Why:
  - maintain current model contract with additive payload evolution only

### `topview/model/state.py`
- Responsibility: typed backend state.
- Changes:
  - likely no structural type change beyond comments/doc consistency
- Why:
  - NMR payload remains `List[Dict[str, object]]`

### `topview/bridge.py`
- Responsibility: JS↔Python RPC boundary.
- Changes:
  - no new method required
  - optional field compatibility for the new NMR entry key
- Why:
  - current `load_system` response already carries NMR data

### `web/src/state.js`
- Responsibility: frontend shared state.
- Changes:
  - replace `nmrVisible` with a filter mode string
- Why:
  - binary visibility is no longer sufficient for per-kind filtering

### `web/src/app.js`
- Responsibility: load orchestration and control wiring.
- Changes:
  - replace button update logic with dropdown logic
  - initialize/reset `state.nmrFilter`
  - wire `change` events
- Why:
  - current NMR control management is centralized here

### `web/src/viewer.js`
- Responsibility: persistent NMR overlay rendering.
- Changes:
  - add per-kind color selection
  - add per-kind filter checks
  - render labels using existing viewer-label machinery
- Why:
  - the codebase map explicitly documents viewer.js as the NMR overlay renderer

### `web/index.html`
- Responsibility: toolbar markup.
- Changes:
  - replace `#toggle-nmr` button with an NMR filter dropdown
- Why:
  - this is where the current control is defined

### `web/styles.css`
- Responsibility: toolbar styling.
- Changes:
  - remove button-specific fixed-width assumptions
  - style the dropdown wrapper/select
- Why:
  - current CSS specifically targets `#toggle-nmr`

### `tests/test_nmr_restraints.py`
- Responsibility: parser coverage.
- Changes:
  - add trailing-zero sentinel classification tests
  - add non-trailing-zero rejection test
  - add serialized `r2` display-value coverage
- Why:
  - parsing/classification semantics must be regression-tested in Python

### `codebase-docs/codebasemap.md`
- Responsibility: source-of-truth architecture and source/symbol index.
- Changes:
  - update NMR behavior description
  - update symbol index for changed functions/fields
- Why:
  - repo instructions require docs to match reality after code changes

### `codebase-docs/assets/*.mmd`
- Responsibility: architecture/flow diagrams.
- Changes:
  - likely no change unless the viewer node text should explicitly mention filtered NMR rendering
- Why:
  - only needed if the flow/module boundary documentation materially changes

## 3) Data model changes (Python)

Relevant source-of-truth sections:
- `codebase-docs/codebasemap.md`:
  - “Sources of Truth”
  - “Default 3D presentation”
  - “Main Compute/Data Flow”
  - “Determinism/Reproducibility”
  - “Precision and Numeric Semantics”
- `codebase-docs/assets/architecture-overview.mmd`
- `codebase-docs/assets/main-execution-sequence.mmd`

### `NmrRestraint` changes

Current file/symbols to touch:
- `topview/services/nmr_restraints.py` / `NmrRestraint`
- `topview/services/nmr_restraints.py` / `NmrRestraint.to_dict`

Planned dataclass shape:
- existing fields unchanged
- add:
  - `equilibrium_value: float`

Pseudo-signature:
- `@dataclass(frozen=True) class NmrRestraint: ... equilibrium_value: float`

### Parsing change

Current file/symbols to touch:
- `topview/services/nmr_restraints.py` / `_parse_iat`
- `topview/services/nmr_restraints.py` / `_classify_restraint`
- `topview/services/nmr_restraints.py` / `_parse_restraint_block`

Proposed behavior:
- parse `iat` tokens in order
- allow exactly one trailing `0`
- remove that trailing `0` from the effective serial list
- reject any `0` that appears before the final token
- continue rejecting:
  - negative/group indices
  - indices greater than `natom`
  - effective counts other than 2/3/4

### Loader/state impact

Current file/symbols to touch:
- `topview/services/loader.py` / `SystemLoadResult`
- `topview/model/model.py` / `load_system`

No new backend cache or index is required.
- `nmr_restraints` remains a list of JSON-serializable dicts
- `nmr_summary` remains `{distance, angle, dihedral, total}`

### Explicit serial mapping statement

Serial remains the canonical ID end-to-end, per the correlation invariant in `codebase-docs/codebasemap.md`.

This feature does not alter:
- MDAnalysis atom ordering
- `AtomMeta.serial`
- PDB serial output
- `3Dmol` atom serials
- JS selection payloads
- Python model lookups

The only change is that the NMR parser may trim a trailing sentinel `0` before classification. The resulting `serials` list still consists only of real 1-based topology atom serials.

### Memory considerations for large systems

Impact is small:
- one extra float per NMR record
- one frontend filter string
- labels computed on demand for only the currently visible restraints

Avoid:
- precomputing label positions in Python
- duplicating grouped NMR arrays per type in the load payload

## 4) Python↔JS bridge contract changes

Relevant source-of-truth sections:
- `codebase-docs/codebasemap.md`: “Main Compute/Data Flow”, “Parallelism Model”
- `codebase-docs/assets/main-execution-sequence.mmd`

No new RPC method is required.

### Existing method kept

Pseudo-signatures:
- `Api.load_system(payload: dict) -> dict`
- `Model.load_system(parm7_path: str, rst7_path: Optional[str], resname: Optional[str], nmr_path: Optional[str]) -> dict | ModelError`

### Changed success payload

Changed `nmr_restraints` entry schema:

```json
{
  "kind": "dihedral",
  "serials": [2414, 1996, 839, 16],
  "r1": -180.0,
  "r2": 119.26935,
  "r3": 119.26935,
  "r4": 180.0,
  "rk2": 96.99,
  "rk3": 96.99,
  "line_start": 42,
  "equilibrium_value": 119.26935
}
```

Outer load payload remains additive-compatible:

```json
{
  "ok": true,
  "view_mode": "3d",
  "pdb_b64": "...",
  "natoms": 2414,
  "nresidues": 154,
  "warnings": [],
  "nmr_restraints": [ ... ],
  "nmr_summary": {
    "distance": 1,
    "angle": 2,
    "dihedral": 3,
    "total": 6
  }
}
```

### Worker choice

Use existing behavior only:
- `load_system` continues through `Worker.submit(...)`

Do not add:
- a new RPC for filtering
- `Worker.submit_cpu(...)` for this feature

### JS async error handling

No new pattern needed:
- parser failures still surface through the existing `load_system` error result
- JS continues using `reportError(...)`, `setLoading(false)`, and current load failure handling

### Backwards compatibility

Treat `equilibrium_value` as optional on the JS side:
- preferred source: `restraint.equilibrium_value`
- fallback: `restraint.r2`

This preserves compatibility with older payloads or tests.

## 5) JS/UI changes

Relevant source-of-truth sections:
- `codebase-docs/codebasemap.md`: “Default 3D presentation”, “UI mode/state contracts and default viewer style policy”
- `codebase-docs/assets/architecture-overview.mmd`
- `codebase-docs/assets/module-dependencies.mmd`

### `web/index.html`

Current file/symbols to touch:
- `web/index.html` / toolbar markup around `#toggle-nmr`

Replace:
- `<button id="toggle-nmr" type="button" hidden>Hide NMR</button>`

With:
- a wrapper label/select pair, for example:
  - wrapper id: `nmr-filter-wrapper`
  - select id: `nmr-filter`

Option values:
- `hide_all`
- `show_all`
- `distance`
- `angle`
- `dihedral`

Option labels:
- `Hide all`
- `Show all`
- `Show distance`
- `Show angle`
- `Show dihedral`

### `web/src/state.js`

Current file/symbols to touch:
- `web/src/state.js` / `state`

Replace:
- `nmrVisible: true`

With:
- `nmrFilter: "show_all"`

### `web/src/app.js`

Current file/symbols to touch:
- `web/src/app.js` / `updateNmrButton`
- `web/src/app.js` / `loadSystem`
- event attachment block for the existing NMR button

Add/change pseudo-signatures:
- `function normalizeNmrFilter(value) -> string`
- `function updateNmrFilterControl() -> void`
- `function resetNmrUiState() -> void`

Behavior on successful 3D load with NMR:
- store `state.nmrRestraints`
- store `state.nmrSummary`
- set `state.nmrFilter = "show_all"`
- show the dropdown

Behavior on 2D load or no restraints:
- clear `state.nmrRestraints`
- reset summary
- set a safe default filter state
- hide the dropdown

Dropdown behavior:
- on `change`, update `state.nmrFilter`
- trigger the persistent overlay rerender path

### `web/src/viewer.js`

Current file/symbols to touch:
- `web/src/viewer.js` / `renderNmrRestraints`
- `web/src/viewer.js` / `drawNmrSegment`
- `web/src/viewer.js` / `drawNmrPlane`
- `web/src/viewer.js` / `drawNmrMarker`
- NMR color constants near the top of the file

Add helper functions:
- `function getNmrColor(kind) -> string`
- `function shouldRenderNmrKind(kind) -> boolean`
- `function getNmrEquilibriumValue(restraint) -> number | null`
- `function buildNmrRestraintLabel(restraint) -> { text, position } | null`

Per-kind colors:
- `distance`: yellow
- `angle`: pink
- `dihedral`: purple

Suggested constant map:
- `const NMR_COLORS = { distance: "#ffff00", angle: "#ff69b4", dihedral: "#8000ff" }`

Filter behavior:
- `hide_all`: render none
- `show_all`: render all
- `distance`: only `distance`
- `angle`: only `angle`
- `dihedral`: only `dihedral`

Label text:
- distance: numeric `r2` only
- angle: numeric `r2` only
- dihedral: numeric `r2` only

Label positions:
- distance: midpoint of atoms 1-2
- angle: atom 2 position, fallback centroid
- dihedral: midpoint of atoms 2-3

Selection/picking behavior:
- unchanged
- must remain entirely serial-based via `state.atomBySerial`

### DOM rendering responsibilities

No change:
- Python parses and validates
- JS owns the viewer control, viewer overlay filter state, and all DOM updates
- info panel remains JS-rendered

## 6) End-to-end data flow for the feature

Relevant source-of-truth sections:
- `codebase-docs/codebasemap.md`: “Startup Spine”, “Main Compute/Data Flow”
- `codebase-docs/assets/main-execution-sequence.mmd`

### Load path

1. User opens `parm7 + rst7` with an NMR file.
2. `web/src/app.js` `loadSystem(...)` calls `Api.load_system`.
3. `topview/bridge.py` sends the request through `Worker.submit(...)`.
4. `topview/model/model.py` calls `topview/services/loader.py`.
5. `topview/services/loader.py` calls `parse_nmr_restraints(...)`.
6. `topview/services/nmr_restraints.py`:
   - parses `iat`
   - trims a trailing sentinel `0`
   - classifies by effective count
   - stores `equilibrium_value = r2`
7. Loader serializes those records into `SystemLoadResult.nmr_restraints`.
8. The bridge returns the normal load response.
9. `web/src/app.js` stores the NMR payload and sets `state.nmrFilter = "show_all"`.
10. `renderModel(...)` loads the PDB.
11. `renderPersistentViewerOverlays()` calls `renderNmrRestraints()`.
12. `renderNmrRestraints()` filters by `state.nmrFilter`, resolves atoms by serial, draws geometry, and adds numeric labels.

### Filter-change path

1. User picks `Show angle` in the dropdown.
2. `web/src/app.js` updates `state.nmrFilter = "angle"`.
3. JS triggers the normal persistent overlay rerender path.
4. `web/src/viewer.js` redraws only angle restraints in pink, with numeric labels.

### 2D path

1. User loads a 2D-only system.
2. `web/src/app.js` clears NMR state and hides the dropdown.
3. `web/src/viewer.js` renders no NMR overlays because the view mode is not `3d`.

## 7) Performance + concurrency plan

Relevant source-of-truth sections:
- `codebase-docs/codebasemap.md`: “Parallelism Model”
- `codebase-docs/assets/main-execution-sequence.mmd`

Potential UI-freeze points:
- drawing a large number of NMR labels/shapes repeatedly

Avoidance plan:
- keep all filter changes local to JS
- do not call back into Python for dropdown changes
- do not reload the model or reparse the NMR file
- use the existing persistent overlay redraw path and render throttling

Worker plan:
- keep `Api.load_system` on `Worker.submit(...)`
- do not add `Worker.submit_cpu(...)`

Model lock/state plan:
- no new backend mutable state tied to the UI filter
- do not hold model state locks for any filter operation because no Python round trip is needed

Incremental update strategy:
- full load once
- incremental overlay rerender on dropdown change

Caching strategy:
- Python: existing `nmr_restraints` model state
- JS: existing `state.nmrRestraints`

Invalidation:
- clear/reset on any new load
- hide/reset on 2D mode
- default to `show_all` on successful 3D+NMR load

## 8) Robustness + error cases

Relevant source-of-truth sections:
- `codebase-docs/codebasemap.md`: “Precision and Numeric Semantics”, “Determinism/Reproducibility”

### Trailing `0` sentinel

Example:
- `iat=839,16,0`

Python behavior:
- accepted
- effective serial list becomes `[839, 16]`

JS user-visible behavior:
- no error
- rendered as a distance restraint

Recovery:
- none needed

### Non-trailing `0`

Example:
- `iat=839,0,16`

Python error:
- continue using the current unsupported zero/group index error family

JS user-visible message:
- existing load failure surfaced through `reportError(...)`

Recovery:
- keep current failed-load semantics; do not partially apply new NMR state

### Out-of-range index

Python error:
- existing “exceeds topology atom count” validation

JS behavior:
- existing load failure path

Recovery:
- same as current failed-load handling

### Missing/malformed `r2`

Python error:
- existing missing/invalid float parsing error path

JS behavior:
- load fails through the existing error path

Recovery:
- same as current behavior

### Unknown frontend `kind`

JS behavior:
- skip rendering safely
- do not break rendering for valid kinds

Recovery:
- keep the remainder of overlays visible

### Many restraints

JS behavior:
- labels may become dense
- rendering remains functional because filtering is local and incremental

Recovery:
- none required for the first implementation

## 9) Testing strategy (must be concrete)

Relevant source-of-truth sections:
- `codebase-docs/codebasemap.md`: file index entries for `tests/test_nmr_restraints.py` and `tests/test_mapping.py`
- correlation invariant in the same map

### Unit tests

Primary file:
- `tests/test_nmr_restraints.py`

Add tests:

1. `test_parse_nmr_restraints_discards_trailing_zero_before_classification`
- examples:
  - `iat=10,20,0` -> `distance`
  - `iat=10,20,30,0` -> `angle`
  - `iat=10,20,30,40,0` -> `dihedral`
- assert the returned `serials` do not include `0`

2. `test_parse_nmr_restraints_rejects_non_trailing_zero`
- example:
  - `iat=10,0,20`
- assert `ValueError`

3. `test_nmr_restraint_to_dict_includes_equilibrium_value`
- parse a known block
- assert `restraint.to_dict()["equilibrium_value"] == restraint.r2`

4. Keep existing tests:
- out-of-range index rejection
- non-restraint file rejection
- existing example summary/classification coverage

### Integration tests

If the repo already has a suitable loader-level pattern, add:
- `tests/test_loader_nmr_payload.py`

Checks:
- a 3D load with an NMR file returns `nmr_restraints` that include:
  - trimmed `serials`
  - expected `kind`
  - `equilibrium_value`

### Mapping correctness checks

Required invariants/tests that must remain true:
- serial ordering preserved in generated PDB
- model lookup by serial remains correct
- NMR serial lists correspond to real topology serials

Validation:
- rerun `tests/test_mapping.py`
- if a loader-level test is added, assert every NMR serial exists in the loaded atom metadata map

### Manual UI verification

1. Load a structure with at least one distance, one angle, and one dihedral restraint.
2. Confirm `Show all` renders all visible restraint types with yellow/pink/purple colors.
3. Confirm `Show distance` shows only distance restraints.
4. Confirm `Show angle` shows only angle restraints.
5. Confirm `Show dihedral` shows only dihedral restraints.
6. Confirm `Hide all` removes all NMR overlays.
7. Confirm each visible restraint displays the numeric value from `r2`, with no units.
8. Confirm atom picking, highlighting, and parm7-linked selection still behave normally.

## 10) Implementation checklist (ordered steps)

1. Update `topview/services/nmr_restraints.py`.
   - modify `NmrRestraint`
   - add `equilibrium_value`
   - change `_parse_iat(...)` to discard only a trailing zero sentinel
   - keep classification based on effective atom count
   - update `to_dict()`

2. Verify pass-through behavior in `topview/services/loader.py`.
   - confirm `record.to_dict()` is the only needed schema propagation step
   - keep `summarize_nmr_restraints(...)` unchanged unless tests show it needs adjustment

3. Verify no backend contract changes are needed in `topview/model/model.py` or `topview/bridge.py`.
   - keep additive payload compatibility only

4. Update `web/src/state.js`.
   - replace `nmrVisible` with `nmrFilter`

5. Update `web/index.html`.
   - replace the NMR button with the dropdown markup

6. Update `web/styles.css`.
   - remove button-specific width assumptions
   - style the new NMR filter control

7. Update `web/src/app.js`.
   - replace `updateNmrButton()` with dropdown management
   - initialize/reset `state.nmrFilter`
   - attach the `change` listener
   - trigger overlay rerender on changes

8. Update `web/src/viewer.js`.
   - add per-kind color mapping
   - add filter checks
   - update marker/segment/plane drawing to use the chosen color
   - add numeric label rendering from `equilibrium_value`/`r2`

9. Extend tests.
   - update `tests/test_nmr_restraints.py`
   - add a loader-level NMR payload test if practical

10. Run targeted validation.
   - `pytest -q tests/test_nmr_restraints.py tests/test_mapping.py`
   - include any new loader test if added

11. Update `codebase-docs/codebasemap.md`.
   - revise the NMR behavior description
   - update the source-file/symbol index for touched files/symbols

12. Update Mermaid diagrams only if needed.
   - annotate viewer/NMR overlay rendering if the documentation would otherwise be misleading

## 11) Tradeoffs and alternatives (brief, but real)

### Option 1: parse trailing-zero sentinel in Python

Pros:
- consistent with Python-first parsing documented in `codebase-docs/codebasemap.md`
- keeps summaries, validation, and rendered kinds aligned
- easy to test in `pytest`

Cons:
- requires a small parser change

Chosen because classification semantics belong in Python.

### Option 2: reinterpret trailing zero only in JS

Pros:
- avoids backend schema changes

Cons:
- duplicates parsing semantics in the frontend
- risks mismatch between backend summary counts and rendered kinds
- violates the documented backend/frontend boundary

Rejected.

### Option 3: use three independent toggles instead of a dropdown

Pros:
- allows combinations like distance+angle without dihedral

Cons:
- larger UI footprint
- more state complexity
- not what the user requested

Rejected for this feature.

### Option 4: show units with the displayed value

Pros:
- clearer semantics

Cons:
- the user explicitly requested number-only labels

Rejected for this implementation.
