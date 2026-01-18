# Parm7 Viewer

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
python app.py
```

Or pass files directly:

```bash
python app.py /path/to/file.parm7 /path/to/file.rst7
```

Enable debug logging to a file:

```bash
python app.py --log-file /path/to/parmviewer.log
```

## Notes

- Atom serials in the PDB output are forced to match the 1-based parm7 atom order.
- Atom metadata and selection details are rendered in the JS info panel.
