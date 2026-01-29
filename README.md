# Topview

Offline desktop viewer for AMBER parm7 + rst7 files (or parm7-only 2D depictions) using pywebview, 3Dmol.js, MDAnalysis, and RDKit.

## Requirements

- Python 3.9+
- `pywebview`
- `MDAnalysis`
- `rdkit` (for parm7-only 2D depictions)
- `gtk` (optionally)

## Install

cd into the `topview` dir and:

```bash
pip install .
```

If you need gtk support, make sure you have the necessary dependencies and:

```bash
pip install .[gtk]
```

## Run

Loading topology+structure:

```bash
topview file.parm7 file.rst7
```

Parm7-only with a 2D depiction of a single residue (defaults to `LIG`):

```bash
topview file.parm7
```

Enable debug logging to a file:

```bash
topview file.parm7 --log-file /path/to/topview.log
```


## Notes

- Atom serials in the PDB output are forced to match the 1-based parm7 atom order.
- Atom metadata and selection details are rendered in the JS info panel.
