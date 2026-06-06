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

## Testing the pipeline with your own dataset

The five-step quick-start above runs the pipeline on a bundled
patient (ds004473 sub-12). To run it on **your own T1 + CT** instead,
the command is:

```bash
make run \
  MRI=/path/to/your/T1w.nii.gz \
  CT=/path/to/your/post_op_CT.nii.gz \
  SUBJECT_DIR=/path/to/freesurfer/subjects/patient_id
```

The pipeline needs a **FreeSurfer reconstruction of the same T1**
(specifically the pial surfaces, `BA_exvivo.annot`, `aparc.annot`,
`aparc+aseg.mgz`, and `talairach.xfm`). If you have those files,
~1–2 minutes per patient. If you do not, the standard `recon-all`
takes 6–12 hours on CPU; FastSurfer is a documented faster
alternative.

A full walk-through — required files, exact directory layout,
ground-truth validation, expected runtime, how to read the outputs,
and the four most common failure modes with concrete fixes — lives
in **[`docs/TESTING_GUIDE.md`](docs/TESTING_GUIDE.md)**. Read that
before running against your own data; it answers every "what does
this error mean" question we have hit so far.

For the design rationale behind each pipeline step and the
investigation that produced the current validation numbers, see
[`docs/PIPELINE_DESIGN.md`](docs/PIPELINE_DESIGN.md) and
[`docs/VALIDATION_FINDINGS.md`](docs/VALIDATION_FINDINGS.md).

---

## All make targets

```
make setup             Create venv + install runtime dependencies
make install-dev       Also install pytest and dev tools
make install-desktop   Also install pywebview (for native window)
make data              Download MNE sample sEEG dataset (~25 MB, smoke-test only)
make data-ds004473     Download ds004473 sub-12 from OpenNeuro (~75 MB)
make test              Run the test suite (104 tests, ~8 s, no data required)
make run-ds004473      Run pipeline on ds004473 sub-12 (recommended)
make run MRI=… CT=… SUBJECT_DIR=…   Run pipeline on any dataset (see docs/TESTING_GUIDE.md)
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

All 104 tests use synthetic data — no dataset download, no network access required.

| File | Coverage | Tests |
|---|---|---|
| `test_loader.py` | NIfTI I/O + brain masking | 3 |
| `test_registration.py` | CT → MRI rigid registration | 3 |
| `test_segmentation.py` | Electrode detection + brain-shift | 8 |
| `test_labeling.py` | BA + ASEG labelling + shaft-aware validation | 37 |
| `test_visualization.py` | 3D visualization | 2 |
| `test_export_viewer.py` | Viewer data export (incl. lobe codes) | 36 |
| `test_ground_truth.py` | BIDS GT loading + frame/units detection | 8 |
| `test_dev_server.py` | Local dev HTTP server | 7 |
| **Total** | | **104** |

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
├── docs/
│   ├── TESTING_GUIDE.md        How to run on your own dataset (read this first)
│   ├── PIPELINE_DESIGN.md      Design rationale per step (clinical + technical)
│   └── VALIDATION_FINDINGS.md  Investigation of the registration residual
│
├── data/                       Input NIfTI / FreeSurfer (git-ignored)
└── outputs/                    Pipeline outputs (git-ignored)
```

---

## Known limitations

- HU > 3000 + 3D connected-component segmentation still picks up cables, connectors, and partial-volume artifacts in the post-op CT. The size + elongation filters drop the obvious ones (~87 of 300 components on ds004473 sub-12) but the remaining ~213 candidates still include some non-anatomical pieces. `make run-ds004473` bypasses this entirely by running with `--use-ground-truth` against the dataset's verified electrode positions.
- The rigid Mutual-Information CT→MRI registration has a known residual on certain CT modalities — most prominently intra-operative O-arm CTs — that the validation matcher exposes as a high mean error on patient sub-12. This is *not* a matching bug: the shaft-aware matcher (`src/labeling.compute_euclidean_error`) reconstructs anatomically correct contact pairings, but the registration places whole shafts ~15–40 mm from their true position. Full diagnosis and the proposed `bbregister` fix path are documented in [`docs/VALIDATION_FINDINGS.md`](docs/VALIDATION_FINDINGS.md).
- `correct_brain_shift` snaps centroids to the nearest pial vertex. For depth (sEEG) electrodes this gives a cortical entry point, not the contact's true depth. Brodmann labels remain meaningful (the trajectory's nearest cortical area); ASEG is the ground truth for subcortical contacts.
- The 2D schematic is anatomically simplified (10 lobes / sub-regions). Electrode placement within a region is a deterministic scatter, not a true projection — use the 3D view for accurate localisation.

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
