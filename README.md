# NeuroElectroMap

**3D intracranial electrode localization via CT + MRI fusion, with an
interactive 2D/3D clinical viewer.**

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

Localizes sEEG / ECoG electrodes by fusing a pre-operative MRI (anatomy)
with a post-operative CT (electrode position), then assigns each contact
both a Brodmann area (surface, `BA_exvivo.annot`) and a Desikan-Killiany
/ subcortical label (volumetric, `aparc+aseg.mgz`). Results are exported
to CSV/Excel for clinical review and to an interactive browser viewer
(or native desktop window) for visualisation.

---

## Quick start — the 3-command tour

For someone evaluating the project from scratch (clean machine, Python 3.11+):

```bash
make setup                 # venv + dependencies                (~3 min)
make data-ds004473         # download sub-12 from OpenNeuro     (~1 min, 75 MB)
make test                  # run the test suite                  (~3 s, 79 tests)
make run-ds004473          # full pipeline + viewer export       (~3-5 min)
make install-desktop       # install pywebview (one-off)         (~30 s)
make desktop               # open the viewer as a native window
```

After `make desktop` the viewer opens showing **228 electrodes from
patient sub-12** with full BA + ASEG labels.

---

## What you get

### Pipeline outputs (`outputs/`)

| File                                | Contents                                                |
|-------------------------------------|---------------------------------------------------------|
| `reports/electrode_report.csv`      | One row per electrode — ID, X/Y/Z (mm), BA, anatomy, shift |
| `figures/electrodes_3d.png`         | PyVista render (pial surface + electrodes)              |
| `processed/mri_masked.nii.gz`       | Brain-masked MRI                                        |
| `processed/ct_registered.nii.gz`    | CT resampled into MRI space                             |
| `viewer/data.json`, `viewer/data.js`| Bundle consumed by the interactive viewer               |

### Interactive viewer

Two modes, toggled in the top bar:

**🧠 2D schematic** — lateral brain SVG with electrodes scattered into
their anatomical regions (BA-mapped on the cortex, aseg-mapped grouped
in a subcortical "pool" beneath: Limbic, Thalamus, Basal ganglia, White
matter, Ventricles…).

**🧊 3D anatomical** — real pial surface (Plotly `Mesh3d`,
semi-transparent so deep contacts stay visible), coloured by per-vertex
BA, with the actual 228 electrodes in their tkRAS coordinates.

Side panel cycles through three states: Overview → Region detail →
Electrode detail. Both views stay in sync with the panel + legend; the
theme toggle (light / dark) persists in `localStorage`.

---

## Setup (manual, if you skip `make setup`)

```bash
git clone <repo-url> NeuroElectroMap
cd NeuroElectroMap

# Virtual environment
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
pip install -r requirements-dev.txt        # for pytest
pip install -r requirements-desktop.txt    # for the native window
```

Python **3.11+** is supported (CI covers 3.11, 3.12, 3.13 on Ubuntu and
3.13 on macOS).

---

## Datasets

Both supported datasets are downloaded straight from public S3 mirrors —
no `datalad` / `git-annex` setup required.

```bash
make data              # MNE sample sEEG (small, dev / smoke testing)
make data-ds004473     # OpenNeuro ds004473 sub-12 (real patient, 228 contacts)
```

The download scripts pull only the files the pipeline needs (T1, CT,
`talairach.xfm`, pial surfaces, `BA_exvivo.annot`, `aparc+aseg.mgz`).
Datasets land under `data/raw/` which is git-ignored.

Need a different sub-X from ds004473? Edit the `FILES` list in
`scripts/download_ds004473.py` — same structure.

---

## Running the pipeline

```bash
# Shortcut for ds004473 sub-12
make run-ds004473

# Or general form
make run \
  MRI=path/to/T1w.nii.gz \
  CT=path/to/ct.nii.gz \
  SUBJECT_DIR=path/to/freesurfer/subject
```

`make run` always passes `--export-viewer` so the viewer bundle is
refreshed automatically. Direct invocation is also fine:

```bash
.venv/bin/python main.py \
  --mri ... --ct ... --subject-dir ... \
  --plot --export-viewer --output-dir outputs/
```

### Optional validation against ground truth

```bash
.venv/bin/python main.py ... --validate path/to/ground_truth.{json,tsv}
```

JSON form (also accepts BIDS `_electrodes.tsv`):

```json
[
  {"id": 1, "gt_mm": [-12.3, 45.1, 20.0]},
  {"id": 2, "gt_mm": [-14.0, 47.2, 18.5]}
]
```

Prints per-contact + mean / max Euclidean error. Clinical target is
mean error < 2 mm.

---

## Opening the viewer

### Browser (good for development — hot-reload friendly)

```bash
make viewer
# open http://localhost:8765/viewer/
```

`scripts/dev_server.py` sends `Cache-Control: no-cache` headers so JSX
edits show up on a normal page reload.

### Native window (recommended for demos and clinical use)

```bash
make install-desktop   # once
make desktop
```

A `pywebview`-managed window opens with the same viewer — no browser,
no terminal URL, own icon on the dock. Uses the system WebView
(`WKWebView` on macOS, `Edge WebView2` on Windows, `WebKitGTK` on
Linux). Closing the window stops the background server.

---

## Architecture

```
                 ┌──────────────────────────────┐
                 │ Pre-op MRI .nii.gz           │
                 │ Post-op CT .nii.gz           │
                 │ FreeSurfer recon: pial,      │
                 │   BA_exvivo.annot,           │
                 │   aparc+aseg.mgz             │
                 └──────────────┬───────────────┘
                                ▼
   ┌──── Phase 1 ──────────────────────────────────────────────┐
   │  load_nifti → reorient_to_ras → apply_brain_mask          │
   └──────────────┬────────────────────────────────────────────┘
                  ▼
   ┌──── Phase 2 ──────────────────────────────────────────────┐
   │  register_ct_to_mri (Mutual Information rigid)            │
   │  segment_electrodes (HU>3000 + 3D CCA)                    │
   │  scanner RAS → tkRAS (via T1.mgz vox2ras/vox2ras_tkr)     │
   │  correct_brain_shift (nearest pial vertex)                │
   └──────────────┬────────────────────────────────────────────┘
                  ▼
   ┌──── Phase 3 ──────────────────────────────────────────────┐
   │  tkRAS → MNI Talairach (talairach.xfm)                    │
   │  lookup_brodmann_surface (BA_exvivo.annot per electrode)  │
   │  lookup_aseg (Desikan-Killiany + subcortical, w/ radius)  │
   └──────────────┬────────────────────────────────────────────┘
                  ▼
   ┌──── Phase 4 ──────────────────────────────────────────────┐
   │  CSV / Excel report                                       │
   │  PyVista 3D render (matplotlib fallback)                  │
   └──────────────┬────────────────────────────────────────────┘
                  ▼
   ┌──── Phase 5 (--export-viewer) ────────────────────────────┐
   │  decimate mesh ~80% (PyVista, label-preserving via NN)    │
   │  bundle into outputs/viewer/{data.json, data.js}          │
   └──────────────┬────────────────────────────────────────────┘
                  ▼
   ┌──── Viewer (React + Plotly, served by dev_server.py) ─────┐
   │  brain2d.jsx   schematic SVG + subcortical pool           │
   │  brain3d.jsx   Plotly Mesh3d + Scatter3d                  │
   │  panel.jsx     Overview / Region / Electrode detail       │
   │  Launched standalone via launch_desktop.py + pywebview    │
   └───────────────────────────────────────────────────────────┘
```

Three coordinate systems are juggled — getting them wrong drops the
accuracy by 50–150 mm. See `.agents/architecture.md` for the full
conversion math.

---

## Project layout

```
NeuroElectroMap/
├── main.py                     CLI entry point — orchestrates phases 1-5
├── Makefile                    setup / data / test / run / viewer / desktop
├── requirements.txt            Runtime dependencies
├── requirements-dev.txt        + pytest, pyyaml
├── requirements-desktop.txt    + pywebview (optional)
├── .github/workflows/ci.yml    Cross-Python / cross-OS CI
│
├── src/
│   ├── loader.py               Phase 1
│   ├── registration.py         Phase 2 (CT → MRI rigid)
│   ├── segmentation.py         Phase 2 (HU threshold + 3D CCA + brain shift)
│   ├── labeling.py             Phase 3 (BA + ASEG + MNI + error metrics)
│   └── visualization.py        Phase 4 (PyVista + matplotlib)
│
├── scripts/
│   ├── download_data.py        MNE sample sEEG
│   ├── download_ds004473.py    OpenNeuro sub-12
│   ├── export_for_viewer.py    Phase 5 — pipeline → data.{json,js}
│   ├── dev_server.py           Local HTTP server with no-cache headers
│   └── launch_desktop.py       pywebview launcher
│
├── viewer/                     React + Plotly single-file app
│   ├── index.html              CSS variables + theme toggle + script glue
│   ├── app.jsx                 Top bar, layout, state, legend
│   ├── panel.jsx               Side panel (Overview / Region / Electrode)
│   ├── brain2d.jsx             Lateral schematic SVG + subcortical pool
│   ├── brain3d.jsx             Plotly Mesh3d + Scatter3d
│   └── regions.js              Static metadata (BA names, schematic paths)
│
├── tests/                      79 pytest tests (synthetic data, no datasets)
│
├── data/                       Input NIfTI / FreeSurfer (git-ignored)
└── outputs/                    Pipeline outputs (git-ignored)
```

---

## Testing

```bash
make test
# or
.venv/bin/python -m pytest tests/ -v
```

| Coverage             | File                          | Tests |
|----------------------|-------------------------------|-------|
| NIfTI I/O + masking  | `test_loader.py`              | 4     |
| Rigid registration   | `test_registration.py`        | 2     |
| Electrode detection  | `test_segmentation.py`        | 3     |
| BA + ASEG labelling  | `test_labeling.py`            | 35    |
| 3D visualization     | `test_visualization.py`       | 2     |
| Viewer bridge        | `test_export_viewer.py`       | 33    |
| **Total**            |                               | **79**|

All tests use synthetic data — no FreeSurfer subject required, no
network. The CI workflow (`.github/workflows/ci.yml`) re-runs them on
every push across Python 3.11 / 3.12 / 3.13 on Ubuntu plus a macOS job.

---

## Known limitations

- The HU > 3000 segmentation can pick up cables, connectors and
  partial-volume artifacts in the post-op CT. On ds004473 sub-12 about
  half of the 228 detected "contacts" are likely real, the rest land
  outside the segmented brain volume. They surface in the viewer's
  "Unknown" pool with an explanatory note.
- `correct_brain_shift` snaps centroids to the nearest pial vertex.
  For depth (sEEG) electrodes this gives a *cortical entry point*, not
  the contact's true depth. Brodmann is still meaningful (the
  trajectory's nearest cortical area); ASEG is the ground truth for
  subcortical contacts.
- The 2D schematic is anatomically simplified (10 lobes / sub-regions),
  drawn from the design hand-off. Electrode placement within a region
  is a deterministic scatter, not a real projection — use the 3D view
  for accurate localisation.
- `aparc+aseg.mgz` lives in FreeSurfer's conformed space; the pipeline
  samples it with `vox2ras_tkr` so the coordinate frame matches the
  pial surface and the BA lookup.

See `.agents/known_issues.md` for a more detailed list, including the
SSL / Talairach atlas download workaround.

---

## Tech stack

| Concern            | Library                                                                |
|--------------------|------------------------------------------------------------------------|
| NIfTI / MGZ I/O    | `nibabel`                                                              |
| Brain masking      | `nilearn`                                                              |
| Surface I/O        | `mne` (`read_surface`, `read_annot` via `nibabel.freesurfer`)          |
| CT → MRI rigid     | `dipy` (Mutual Information optimiser)                                  |
| 3D connected comp. | `scipy.ndimage`                                                        |
| Region centroids   | `scikit-image`                                                         |
| 3D render (server) | `pyvista` (interactive) + `matplotlib` (fallback)                      |
| 3D render (web)    | `plotly.js` (`Mesh3d` + `Scatter3d`) inside a React + Babel-standalone shell |
| Desktop window     | `pywebview` (`WKWebView` / `Edge WebView2` / `WebKitGTK`)              |
| Tabular export     | `pandas`                                                               |
| Tests / CI         | `pytest`, GitHub Actions                                               |

---

## Acknowledgements

Dataset: **ds004473** (Rockhill et al., 2022 — OHSU sEEG) via
OpenNeuro. Sample dataset: MNE sample sEEG. FreeSurfer atlases:
`BA_exvivo.annot`, `aparc+aseg.mgz`.
