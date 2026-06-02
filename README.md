# NeuroElectroMap

**3D intracranial electrode localization via CT + MRI fusion, with an interactive 2D/3D clinical viewer.**

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

Localizes sEEG / ECoG electrodes by fusing a pre-operative MRI (anatomy) with a post-operative CT (electrode position), then assigns each contact both a Brodmann area (surface, `BA_exvivo.annot`) and a Desikan-Killiany / subcortical label (volumetric, `aparc+aseg.mgz`). Results are exported to CSV/Excel and to an interactive browser viewer for visualisation.

---

## From zero to the web viewer — step by step

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11 or newer | Check with `python3 --version` |
| Git | Any recent version |
| ~500 MB free disk space | Code + dataset + outputs |
| macOS or Linux | Windows: use WSL 2 |

---

### 1. Clone the repository

```bash
git clone <repo-url> NeuroElectroMap
cd NeuroElectroMap
```

---

### 2. Create the virtual environment and install dependencies

```bash
make setup
```

This creates `.venv/` and installs all runtime dependencies (~3 min on first run).

> If you don't have `make`, run manually:
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate
> pip install -r requirements.txt
> ```

---

### 3. Download the dataset

```bash
make data-ds004473
```

Downloads **sub-12 from OpenNeuro ds004473** (real sEEG patient, 75 MB) directly from the public S3 mirror — no account or extra tools required. Files land under `data/raw/ds004473/`.

---

### 4. Run the pipeline

```bash
make run-ds004473
```

This runs the full pipeline on sub-12 and writes the viewer bundle automatically (~45 seconds). It uses the dataset's verified ground-truth electrode positions, so CT segmentation is skipped and all contacts get their clinical names (e.g. `LTP1`, `RAHIPP3`).

When it finishes you will see:

```
Exported viewer data → outputs/viewer/data.json
Exported viewer data → outputs/viewer/data.js
```

---

### 5. Open the web viewer

```bash
make viewer
```

This starts a local HTTP server on port 8765 and opens your browser automatically.  
If the browser does not open, navigate to **http://localhost:8765/** manually.

Press `Ctrl-C` in the terminal to stop the server when you are done.

---

### What you will see

The viewer has two modes, toggled in the top bar:

**2D schematic** — a lateral brain SVG with all electrode contacts placed into their anatomical regions. Cortical contacts are grouped by Brodmann area; subcortical contacts are pooled below (Limbic, Thalamus, Basal Ganglia, White Matter, Ventricles).

**3D anatomical** — the real pial surface rendered as a semi-transparent mesh (coloured by per-vertex Brodmann area), with the 228 electrode contacts at their true tkRAS coordinates.

Clicking any electrode in either view opens its detail in the side panel (region, BA label, ASEG label, coordinates). The legend is grouped by clinical region. A light/dark theme toggle is in the top-right corner.

---

## All make targets

```
make setup             Create venv + install runtime dependencies
make install-dev       Also install pytest and dev tools
make install-desktop   Also install pywebview (for native window)
make data              Download MNE sample sEEG dataset (~25 MB, smoke-test only)
make data-ds004473     Download ds004473 sub-12 from OpenNeuro (~75 MB)
make test              Run the test suite (79 tests, ~3 s, no data required)
make run-ds004473      Run pipeline on ds004473 sub-12 (recommended)
make run MRI=… CT=… SUBJECT_DIR=…   Run pipeline on any dataset
make viewer            Serve the viewer at http://localhost:8765/
make desktop           Open the viewer in a native desktop window (needs install-desktop)
make ports             List all TCP ports currently in LISTEN state
```

---

## Pipeline outputs (`outputs/`)

| File | Contents |
|---|---|
| `reports/electrode_report.csv` | One row per contact — ID, name, X/Y/Z (mm), BA, anatomy, shift |
| `figures/electrodes_3d.png` | PyVista render of the pial surface with electrode positions |
| `processed/mri_masked.nii.gz` | Brain-masked T1w MRI |
| `processed/ct_registered.nii.gz` | CT resampled into MRI space |
| `viewer/data.json`, `viewer/data.js` | Bundle consumed by the interactive viewer |

---

## Native desktop window (optional)

If you prefer a standalone window instead of a browser tab:

```bash
make install-desktop   # one-off: installs pywebview
make desktop
```

A native window opens using `WKWebView` (macOS), `Edge WebView2` (Windows), or `WebKitGTK` (Linux). Closing the window stops the background server.

---

## Running the tests

```bash
make test
```

All 79 tests use synthetic data — no dataset download, no network access required.

| File | Coverage | Tests |
|---|---|---|
| `test_loader.py` | NIfTI I/O + brain masking | 4 |
| `test_registration.py` | CT → MRI rigid registration | 2 |
| `test_segmentation.py` | Electrode detection | 3 |
| `test_labeling.py` | BA + ASEG labelling | 35 |
| `test_visualization.py` | 3D visualization | 2 |
| `test_export_viewer.py` | Viewer data export | 33 |
| **Total** | | **79** |

CI runs on every push across Python 3.11, 3.12, 3.13 on Ubuntu and 3.13 on macOS.

---

## Pipeline architecture

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
   │  segment_electrodes (HU > 3000 + 3D CCA)                  │
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
   └───────────────────────────────────────────────────────────┘
```

Three coordinate systems are in play — scanner RAS, FreeSurfer tkRAS, and MNI Talairach. Getting the conversions wrong shifts contacts by 50–150 mm. See `.agents/architecture.md` for the full conversion math.

---

## Project layout

```
NeuroElectroMap/
├── main.py                     CLI entry point — orchestrates phases 1-5
├── Makefile                    All convenience commands
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

## Known limitations

- The HU > 3000 segmentation can pick up cables, connectors, and partial-volume artifacts in the post-op CT. On ds004473 sub-12 about half of the 228 detected contacts are likely real; the rest land outside the segmented brain volume and surface in the viewer's "Unknown" pool with an explanatory note. `make run-ds004473` bypasses this by using the dataset's verified ground-truth positions directly.
- `correct_brain_shift` snaps centroids to the nearest pial vertex. For depth (sEEG) electrodes this gives a cortical entry point, not the contact's true depth. Brodmann is still meaningful (the trajectory's nearest cortical area); ASEG is the ground truth for subcortical contacts.
- The 2D schematic is anatomically simplified (10 lobes / sub-regions). Electrode placement within a region is a deterministic scatter, not a real projection — use the 3D view for accurate localisation.

---

## Tech stack

| Concern | Library |
|---|---|
| NIfTI / MGZ I/O | `nibabel` |
| Brain masking | `nilearn` |
| Surface I/O | `mne` (`read_surface`, `read_annot`) |
| CT → MRI rigid | `dipy` (Mutual Information optimiser) |
| 3D connected components | `scipy.ndimage` |
| Region centroids | `scikit-image` |
| 3D render (server) | `pyvista` + `matplotlib` fallback |
| 3D render (web) | `plotly.js` (`Mesh3d` + `Scatter3d`) inside React + Babel-standalone |
| Desktop window | `pywebview` |
| Tabular export | `pandas` |
| Tests / CI | `pytest`, GitHub Actions |

---

## Acknowledgements

Dataset: **ds004473** (Rockhill et al., 2022 — OHSU sEEG) via OpenNeuro. Sample dataset: MNE sample sEEG. FreeSurfer atlases: `BA_exvivo.annot`, `aparc+aseg.mgz`.
