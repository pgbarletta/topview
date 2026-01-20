# Topview

Offline desktop viewer for AMBER parm7 + rst7 files using pywebview, 3Dmol.js, and MDAnalysis.

## Requirements

- Python 3.9+
- `pywebview`
- `MDAnalysis`

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

You can also run the package entrypoint:

```bash
python -m topview /path/to/file.parm7 /path/to/file.rst7
```

Enable debug logging to a file:

```bash
python -m topview.app --log-file /path/to/topview.log
```

## Notes

- Atom serials in the PDB output are forced to match the 1-based parm7 atom order.
- Atom metadata and selection details are rendered in the JS info panel.
