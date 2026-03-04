You are a coding agent. Implement a runnable desktop molecular viewer application EXACTLY matching the architecture requirements below. Output the full contents of each file. Keep it minimal but complete.

Tech stack:
- Python desktop shell: pywebview (native window embedding HTML/JS)
- In-viewer rendering: 3Dmol.js (WebGL)
- File parsing/data model: MDAnalysis (primary input: AMBER parm7 + rst7)
- No MD trajectories: render a single static structure from parm7+rST7
- Info panel MUST be rendered in JavaScript (DOM), populated by calling Python over the pywebview JS↔Python bridge.
- Top priority: robust correlation between parm7 topology fields and the rendered molecule.

REFERENCES (use these as primary sources; do not invent APIs)
pywebview:
- https://pywebview.flowrl.com/api/
- https://pywebview.flowrl.com/guide/interdomain
- https://pywebview.flowrl.com/examples/evaluate_js.html
- https://github.com/r0x0r/pywebview/blob/master/examples/js_api.py

3Dmol.js:
- https://3dmol.org/doc/
- https://3dmol.csb.pitt.edu/doc/tutorial-code.html
- https://3dmol.csb.pitt.edu/doc/GLViewer.html
- https://3dmol.csb.pitt.edu/doc/GLModel.html
- https://3dmol.csb.pitt.edu/doc/AtomSpec.html
- https://github.com/3dmol/3Dmol.js

MDAnalysis:
- Use MDAnalysis.Universe(parm7, rst7) and access Universe.atoms/residues and positions.

-------------------------------------------------------------------------------
CRITICAL CORRELATION REQUIREMENT (DO NOT BREAK)
-------------------------------------------------------------------------------
Define and preserve a canonical atom identifier:
- canonical_serial := parm7 atom index in 1-based numbering (1..N)
This canonical_serial MUST be the same value that appears as:
- Python-side mapping key
- The PDB serial number written into the structure string sent to JS
- The value observed in 3Dmol atom objects as atom.serial
Click selection must round-trip:
3Dmol atom click -> atom.serial -> Python get_atom_info(serial) -> returns parm7 metadata for that same atom

Do NOT rely on “whatever MDAnalysis writer does” if it can change ordering/serials. Implement a minimal PDB writer to guarantee serial numbering and ordering.

-------------------------------------------------------------------------------
DELIVERABLE FILES / STRUCTURE
-------------------------------------------------------------------------------
Create this repository layout:

/app.py
/api.py
/model.py
/pdb_writer.py
/worker.py
/tests/test_mapping.py
/web/index.html
/web/app.js
/web/styles.css
/web/vendor/3Dmol-min.js   (vendored; see note below)
(optional) /README.md

Vendoring note:
- Runtime must be offline (no internet required).
- Include a README comment instructing to copy 3Dmol-min.js from official 3Dmol builds into web/vendor/.
- During development you MAY include an optional dev toggle to use a CDN, but the default must load local vendor/3Dmol-min.js.

-------------------------------------------------------------------------------
APPLICATION BEHAVIOR & UI
-------------------------------------------------------------------------------
UI layout (JS-rendered):
- Left: 3Dmol viewer canvas
- Right: info panel (atom/residue details), plus selection history list
- Top toolbar:
  - “Open parm7 + rst7” button (use pywebview file dialog if feasible; otherwise fallback to two path inputs + Load button)
  - Style preset dropdown (e.g., “Cartoon+Ligand”, “Sticks”, “Spheres”)
  - Search/filter section (simple):
     - residue name contains
     - atom name equals/contains
     - atom type equals (from parm7 if available)
     - charge range (if available)
  - “Clear selection” button
- Status area for progress/errors (loading indicator when Python is working)

Interactions:
1) Load structure:
   - User chooses parm7 and rst7.
   - Python loads via MDAnalysis, builds mapping tables, writes PDB string with serials 1..N, returns base64-encoded PDB and counts.
   - JS decodes and renders in 3Dmol, applies default style, and enables picking.
2) Click atom:
   - JS receives 3Dmol atom object, reads atom.serial.
   - JS calls Python window.pywebview.api.get_atom_info({serial}) (Promise).
   - JS renders info panel with returned fields (escape HTML) and highlights selected atom in 3Dmol.
   - Add entry to selection history (serial + residue + atom name).
3) Search/filter:
   - JS sends filter object to Python query_atoms(filters).
   - Python returns a list of serials.
   - JS highlights those atoms (e.g., sticks) and shows result count; clicking a result selects that atom.

Performance/robustness:
- MDAnalysis parsing + metadata build must not freeze UI. Use a background worker thread in Python for load_system and large queries if needed.
- Use a thread-safe state store (Lock) for meta tables.
- JS must show “Loading…” state and disable interactions while load is running.
- Return structured errors: { ok:false, error:{code,message,details?} } and handle in UI.

-------------------------------------------------------------------------------
PYTHON↔JS BRIDGE (pywebview contract)
-------------------------------------------------------------------------------
Implement a Python js_api object exposed to JS. JS accesses it only after 'pywebviewready'.
Expose at minimum:

1) load_system(payload) -> result
   payload: { parm7_path: string, rst7_path: string }
   result (success):
     {
       ok: true,
       pdb_b64: string,
       natoms: int,
       nresidues: int,
       warnings: string[]
     }
   result (error):
     { ok:false, error:{code:string, message:string, details?:any} }

2) get_atom_info(payload) -> result
   payload: { serial: int }
   result (success):
     {
       ok:true,
       atom:{
         serial:int,
         atom_name:string,
         element:string|null,
         residue:{
           resid:int|string,
           resname:string,
           segid?:string|null,
           chain?:string|null
         },
         coords:{x:float,y:float,z:float},
         parm7:{
           atom_type?:string,
           charge?:float,
           mass?:float,
           ... (include what you can reliably extract)
         }
       }
     }
   result (error): as above

3) query_atoms(payload) -> result
   payload example:
     { filters: { resname_contains?:string, atomname_contains?:string, atom_type_equals?:string, charge_min?:float, charge_max?:float } }
   result (success): { ok:true, serials:int[], count:int, truncated?:bool }
   For huge results, you may truncate and set truncated=true.

4) get_residue_info(payload) -> optional (nice-to-have)
   payload: { resid:int|string }
   result: summary of residue and list of atom serials

JS→Python calls must be Promises and JS must handle rejections/timeouts gracefully.

Python→JS calls via evaluate_js:
- Implement JS functions and call them from Python only when beneficial:
  - ui_set_status({level,message})
  - ui_set_loaded({natoms,nresidues})
But it is acceptable if JS pulls state by awaiting load_system and then updates UI without Python pushing.

-------------------------------------------------------------------------------
DATA MODEL (Python)
-------------------------------------------------------------------------------
Implement a centralized Model/State that stores:
- universe (MDAnalysis Universe) or minimal extracted arrays (prefer minimal to reduce memory)
- meta_by_serial: dict[int -> AtomMeta]
- residue index: resid -> list[serials]
- optional: inverted indices for filtering (resname->serials etc.) for speed

AtomMeta must be built in canonical_serial order (1..N). Ensure ordering matches parm7’s atom order.

Metadata extraction:
- From MDAnalysis atoms/residues:
  - atom.name, residue.resname, residue.resid, positions
  - element best-effort (MDAnalysis may have atom.element; otherwise derive from atom name heuristic)
- From parm7 topology:
  - If MDAnalysis exposes topology attributes for charges/types/masses, use them.
  - If not, leave as null and still preserve mapping.
  - DO NOT parse parm7 manually here; I will later provide parm7 references and you can extend. For now, implement hooks in Model to attach parm7 fields.

PDB writer:
- Write ATOM records in the same order as the atom list that corresponds to parm7 order.
- Se
