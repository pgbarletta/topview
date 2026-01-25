# Topview

Offline desktop viewer for AMBER parm7 + rst7 files (or parm7-only 2D depictions) using pywebview, 3Dmol.js, MDAnalysis, and RDKit.

## Requirements

- Python 3.9+
- `pywebview`
- `MDAnalysis`
- `rdkit` (for parm7-only 2D depictions)

## Vendor 3Dmol

Copy the official `3Dmol-min.js` build into `web/vendor/3Dmol-min.js`.
The app defaults to local assets and does not load from CDN.

## Run

```bash
python -m topview.app
```

Or pass files directly:

```bash
python -m topview.app /path/to/file.parm7 /path/to/file.rst7
```

Parm7-only with a 2D depiction of a residue (defaults to `LIG`):

```bash
python -m topview.app /path/to/file.parm7 --resname LIG
```

You can also run the package entrypoint:

```bash
python -m topview /path/to/file.parm7 /path/to/file.rst7
```

Enable debug logging to a file:

```bash
python -m topview.app --log-file /path/to/topview.log
```

Note: Use a recent `rdkit` build compatible with your Python version.

## Notes

- Atom serials in the PDB output are forced to match the 1-based parm7 atom order.
- Atom metadata and selection details are rendered in the JS info panel.
