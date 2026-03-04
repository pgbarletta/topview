# Use the Codebase Map First (and keep it updated)

Before touching the repository, you must read:
- `codebase-analysis-docs/codebasemap.md`
- every Mermaid diagram in `codebase-analysis-docs/assets/` (`*.mmd`)

Treat these docs as the **source of truth** for architecture, compute/data flow, capability boundaries, invariants (units/determinism/precision), and the source-file + symbol index.

When proposing any change, you must:
1) cite the relevant section(s) of `codebasemap.md` and any relevant `assets/*.mmd` by path,
2) identify the exact files/symbols you will touch (repo-relative paths + symbol names), and
3) list the invariants/tests/validation expectations that must remain true.

After modifying the codebase, you must **update `codebase-analysis-docs/`** to match reality:
- revise `codebasemap.md` sections affected (architecture/capabilities/invariants/etc.)
- update the **source-file + symbol index** for any files whose classes/functions/globals changed
- add/update Mermaid diagrams in `assets/` if flows/modules changed
- note changes in `OPEN QUESTIONS` / `ASSUMPTIONS` only if they remain unresolved
