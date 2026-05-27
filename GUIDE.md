# NeuroElectroMap — Reproduction Guide

This guide walks you through setting up the environment, downloading the
dataset, and running the full 3D intracranial electrode localisation pipeline.

---

## 1. Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 or newer |
| Git | any recent version |
| Disk space | ~500 MB (code + data + outputs) |
| OS | macOS, Linux, or Windows (WSL recommended on Windows) |

---

## 2. Clone the repository

```bash
git clone <repo-url>
cd NeuroElectroMap
```

---

## 3. Create the virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

> First import of the pipeline will take ~15 seconds while scipy and nilearn
> build their caches — this is normal.

---

## 4. Download the dataset

The pipeline was validated against **OpenNeuro ds004473**  
*(Stereoelectroencephalography during a forced two-choice task — OHSU, Oregon)*

🔗 **Dataset page:** https://openneuro.org/datasets/ds004473/versions/1.0.2

You only need the files for **one subject (sub-12)**. Two download options are
provided below.

---

### Option A — Direct download (no extra tools needed)

Run the helper script that downloads exactly the files the pipeline needs:

```bash
python scripts/download_ds004473.py
```

This script fetches sub-12's T1w MRI, CT, and FreeSurfer derivatives directly
from OpenNeuro's public S3 bucket and places them under `data/raw/ds004473/`.

---

### Option B — Full dataset via Datalad

If you want all 8 subjects:

```bash
pip install datalad
datalad install https://github.com/OpenNeuroDatasets/ds004473.git data/raw/ds004473
cd data/raw/ds004473
datalad get sub-12/anat/ derivatives/freesurfer-7.3.2/sub-12/
```

---

### Option C — MNE demo dataset (quick smoke-test, no FreeSurfer needed)

For a fast sanity-check with synthetic sample data:

```bash
make data   # downloads the MNE sample sEEG dataset (~250 MB)
make run MRI=data/raw/mne_seeg_sample/T1.nii.gz \
         CT=data/raw/mne_seeg_sample/CT.nii.gz
```

> ⚠️ The MNE sample uses a surrogate FreeSurfer subject, so brain-shift
> corrections will be large and Brodmann labels may be inaccurate. Use
> ds004473 for proper results.

---

## 5. Run the pipeline

After Option A or B above, run:

```bash
make run \
  MRI=data/raw/ds004473/sub-12/anat/sub-12_T1w.nii.gz \
  CT=data/raw/ds004473/sub-12/anat/sub-12_ct.nii.gz \
  SUBJECT_DIR=data/raw/ds004473/derivatives/freesurfer-7.3.2/sub-12
```

Or directly with Python:

```bash
python main.py \
  --mri      data/raw/ds004473/sub-12/anat/sub-12_T1w.nii.gz \
  --ct       data/raw/ds004473/sub-12/anat/sub-12_ct.nii.gz \
  --subject-dir data/raw/ds004473/derivatives/freesurfer-7.3.2/sub-12 \
  --plot \
  --output-dir outputs/
```

---

## 6. Expected outputs

The pipeline takes ~45 seconds end-to-end.

| Output file | Description |
|---|---|
| `outputs/reports/electrode_report.csv` | Electrode ID, XYZ coordinates (mm), Brodmann area, anatomy label, shift correction |
| `outputs/figures/electrodes_3d.png` | 3D render of the cortical surface with electrode positions |
| `outputs/processed/mri_masked.nii.gz` | Brain-masked T1w MRI |
| `outputs/processed/ct_registered.nii.gz` | CT aligned to MRI space |

The CSV report and 3D render from a completed run on sub-12 are already
committed to this repository under `outputs/` for reference.

---

## 7. Command reference

```bash
make setup        # Create venv and install all dependencies
make data         # Download MNE sample dataset
make test         # Run the test suite
make run MRI=... CT=... SUBJECT_DIR=...   # Run the full pipeline
```

For validation against ground-truth electrode positions, add:

```bash
python main.py ... --validate path/to/ground_truth.json
```

Ground-truth JSON format:

```json
[
  {"id": 1, "gt_mm": [-12.3, 45.1, 20.0]},
  {"id": 2, "gt_mm": [-14.0, 47.2, 18.5]}
]
```

---

## 8. Project structure

```
NeuroElectroMap/
├── main.py                   # CLI entry point (Phase 4 – Task 4.3)
├── requirements.txt          # Runtime dependencies
├── requirements-dev.txt      # + pytest for testing
├── Makefile                  # Convenience commands
├── GUIDE.md                  # This file
├── src/
│   ├── loader.py             # Phase 1: NIfTI I/O, brain masking
│   ├── registration.py       # Phase 2: CT-to-MRI rigid registration (dipy)
│   ├── segmentation.py       # Phase 2: Electrode detection + brain-shift correction
│   ├── labeling.py           # Phase 3: MNI normalisation, Brodmann lookup, reporting
│   └── visualization.py      # Phase 4: 3D rendering (pyvista / matplotlib fallback)
├── tests/                    # Unit tests (pytest)
├── scripts/
│   ├── download_data.py      # Downloads MNE sample dataset
│   └── download_ds004473.py  # Downloads ds004473 sub-12 from OpenNeuro S3
├── data/                     # Patient data — git-ignored, download via Section 4
└── outputs/
    ├── reports/              # ✅ Committed — electrode CSV results
    ├── figures/              # ✅ Committed — 3D renders
    └── processed/            # git-ignored — large intermediate NIfTI files
```
