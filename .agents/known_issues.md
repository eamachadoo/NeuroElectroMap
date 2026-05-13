# NeuroElectroMap — Known Issues & Gotchas

This file documents non-obvious problems discovered during development.
Read this before modifying any coordinate-handling code.

---

## 1. Brain-shift corrections will always be large for sEEG

**Symptom:** `[WARNING] Electrode N: large brain-shift correction XX mm` for every electrode.

**Why:** `correct_brain_shift` snaps each centroid to the *nearest pial surface vertex*.
The pial surface is the *outer* cortical shell. sEEG electrodes are implanted *inside* the
brain (depth electrodes). A depth electrode 30 mm inside the brain will always be 30+ mm
from the nearest surface point. This is correct behaviour, not an error.

**Consequence:** The `corrected_mm` field for sEEG holds the surface entry-point estimate,
not a corrected depth position. The Brodmann lookup uses `corrected_mm` (nearest surface
vertex), which gives the cortical area closest to the electrode trajectory — an acceptable
clinical approximation but not the same as the electrode's true anatomical depth.

**Fix needed for sEEG accuracy:** Replace nearest-surface snapping with trajectory-based
localisation (fit a line through contacts along the shaft, intersect with atlas parcels).

---

## 2. Three coordinate spaces — never mix them

| Space        | Used in                          | Origin                 |
|--------------|----------------------------------|------------------------|
| Scanner RAS  | NIfTI affines, electrode mm coords after segmentation | MRI scanner isocentre |
| tkRAS        | FreeSurfer pial surface vertices, `.annot` labels | Centre of FOV in T1.mgz |
| MNI Talairach| Atlas lookup, cross-patient comparison | Standard template brain |

Electrode centroids from `segment_electrodes` are in **scanner RAS**.
Pial vertices from `mne.read_surface` are in **tkRAS**.
They are offset by up to ~50 mm — the `scanner_to_tkr` transform in `main.py` handles this.
Do not remove or bypass this conversion.

---

## 3. The Talairach atlas download fails on macOS Python 3.14

**Symptom:** `SSLCertVerificationError` when `nilearn.datasets.fetch_atlas_talairach` tries
to reach `www.talairach.org`.

**Why:** Python 3.14 on Homebrew uses a different SSL certificate store than the system.
`SSL_CERT_FILE` env vars are ignored by nilearn's internal download session.

**Resolution:** The pipeline no longer uses `fetch_atlas_talairach`. Brodmann lookup is now
done via `lookup_brodmann_surface` in `src/labeling.py`, which reads the FreeSurfer
`lh.BA_exvivo.annot` and `rh.BA_exvivo.annot` files that ship with the MNE sample dataset.
No network access is required at runtime.

---

## 4. `mne.transforms.read_talxfm` does not exist in MNE ≥ 1.7

**Symptom:** `ImportError: cannot import name 'read_talxfm' from 'mne.transforms'`

**Resolution:** The function was removed from the public API. `main.py` now uses
`_parse_talairach_xfm`, a local parser that reads the plain-text XFM format directly.
Do not attempt to re-import from `mne.transforms`.

---

## 5. FreeSurfer subject directory is required at runtime

`--subject-dir` must point to a directory containing:
```
<subject>/
├── mri/
│   ├── T1.mgz                  # for scanner→tkRAS transform
│   └── transforms/
│       └── talairach.xfm       # for tkRAS→MNI transform
├── surf/
│   ├── lh.pial                 # left hemisphere pial surface
│   └── rh.pial                 # right hemisphere pial surface
└── label/
    ├── lh.BA_exvivo.annot      # Brodmann area annotations
    └── rh.BA_exvivo.annot
```

The MNE sample dataset (`make data`) provides all of these under
`data/raw/mne_seeg_sample/sample_seeg/`.

---

## 6. `ds003844` on OpenNeuro is not suitable for this pipeline

All electrode coordinates in ds003844 are `0 0 0` (not released) and there are no MRI or CT
NIfTI files — only iEEG recordings and a JPEG photograph reference. Do not attempt to use it.
Use the MNE sample sEEG dataset instead (`make data`).
