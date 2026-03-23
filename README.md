# NeuroElectroMap
**3D Intracranial Electrode Localization via CT + MRI Fusion**

Localizes sEEG/ECoG electrodes in 3D space by fusing a pre-operative MRI (anatomy) with a post-operative CT (electrode position), then maps each electrode to a Brodmann area.

---

## Requirements

- Python **3.10+**
- ~4 GB disk space for dependencies + atlas data

---

## Setup (one-time)

```bash
# 1. Clone
git clone <repo-url>
cd NeuroElectroMap

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

For running tests, install dev dependencies instead:
```bash
pip install -r requirements-dev.txt
```

---

## Data

Place your NIfTI files in `data/` (this folder is git-ignored — each team member manages their own copy):

```
data/
  mri.nii.gz    ← pre-operative T1 MRI
  ct.nii.gz     ← post-operative CT
```

### Public test datasets

| Dataset | MRI + CT | Link |
|---------|----------|------|
| OpenNeuro ds003688 | Yes (sEEG) | https://openneuro.org/datasets/ds003688 |
| MNI Open iEEG | Yes (ECoG) | Search "MNI open iEEG" on OSF.io |
| Zenodo sEEG localization | Yes | Search "sEEG localization" on zenodo.org |

Download one subject's `*_T1w.nii.gz` (MRI) and `*_CT.nii.gz` (CT), rename them, and drop them in `data/`.

---

## Usage

```bash
# Basic run
python main.py --mri data/mri.nii.gz --ct data/ct.nii.gz

# With 3D plot + Excel report
python main.py --mri data/mri.nii.gz --ct data/ct.nii.gz --plot --format xlsx

# With validation against ground-truth markers
python main.py --mri data/mri.nii.gz --ct data/ct.nii.gz --validate data/ground_truth.json
```

Via Makefile:
```bash
make run MRI=data/mri.nii.gz CT=data/ct.nii.gz
```

**Ground truth JSON format** (for `--validate`):
```json
[
  {"id": 1, "gt_mm": [-12.3, 45.1, 20.0]},
  {"id": 2, "gt_mm": [-14.0, 47.2, 18.5]}
]
```

### Outputs

| File | Description |
|------|-------------|
| `outputs/reports/electrode_report.csv` | Electrode ID, XYZ coords, Brodmann area, anatomy label |
| `outputs/figures/electrodes_3d.png` | 3D render of brain + electrodes (see note below) |
| `outputs/processed/mri_masked.nii.gz` | Brain-masked MRI |
| `outputs/processed/ct_registered.nii.gz` | CT aligned to MRI space |

> **Visualization note:** `--plot` uses **pyvista** for an interactive 3D mesh render when a pial surface is available. If pyvista is not installed or no surface mesh is provided, it automatically falls back to a **matplotlib** 3D scatter plot. Both save to `outputs/figures/electrodes_3d.png`.

---

## Running Tests

```bash
make test
# or directly:
pytest tests/ -v
```

---

## Project Structure

```
NeuroElectroMap/
├── main.py                  # CLI entry point
├── requirements.txt         # Runtime dependencies
├── requirements-dev.txt     # + pytest for testing
├── Makefile                 # Convenience commands
├── src/
│   ├── loader.py            # Phase 1: NIfTI I/O, brain masking
│   ├── registration.py      # Phase 2: CT-to-MRI rigid registration
│   ├── segmentation.py      # Phase 2: Electrode detection + brain-shift correction
│   ├── labeling.py          # Phase 3: MNI normalization, Brodmann lookup, reporting
│   └── visualization.py     # Phase 4: 3D rendering
├── tests/                   # Unit tests (pytest)
├── data/                    # Your NIfTI files — git-ignored
└── outputs/                 # Pipeline outputs — git-ignored
```

---

## Pipeline Overview

```
MRI (.nii.gz)  ──┐
                  ├─► Brain Mask ──► CT Registration ──► Electrode Segmentation
CT  (.nii.gz)  ──┘                                              │
                                                                 ▼
                                              Brain-Shift Correction (pial surface)
                                                                 │
                                                                 ▼
                                              MNI Normalization + Brodmann Lookup
                                                                 │
                                                                 ▼
                                              CSV Report + 3D Visualization
```

**Precision target:** mean localization error < 2.0 mm.
