# NeuroElectroMap — Project Blueprint

## Objective
Develop a neuroimaging pipeline to localise intracranial electrodes (sEEG/ECoG) in 3D space
by fusing pre-operative MRI (anatomy) with post-operative CT (electrode position).

**Clinical goal:** Map each electrode coordinate to a Brodmann area so neurologists know
which functional region each electrode is recording from (e.g. "Electrode 7 → BA22, Wernicke's Area").

**Precision target:** Mean Euclidean Error < 2.0 mm (standard clinical threshold).

**Timeline:** March 18 – May 31 (10 weeks).

---

## Technical Stack

| Library       | Role                                               |
|---------------|----------------------------------------------------|
| `nibabel`     | NIfTI / MGZ I/O and affine matrix manipulation     |
| `nilearn`     | Brain masking, image arithmetic                    |
| `mne`         | FreeSurfer surface I/O, coordinate transforms      |
| `dipy`        | Rigid-body CT-to-MRI registration (Mutual Info)    |
| `scipy`       | 3D connected-component analysis                    |
| `scikit-image`| Region properties (centroids)                      |
| `pyvista`     | Interactive 3D cortical surface render             |
| `matplotlib`  | Fallback 3D scatter render                         |
| `pandas`      | CSV / Excel report export                          |

---

## Implementation Phases

### Phase 1 — Data Preparation (Weeks 1–2)
- **1.1** NIfTI loader (`src/loader.py`)
- **1.2** Affine extraction and RAS+/LPS orientation check
- **1.3** Brain masking via `nilearn.masking.compute_brain_mask`

### Phase 2 — Fusion Engine (Weeks 3–5)
- **2.1** Rigid CT-to-MRI registration: Mutual Information optimisation → 4×4 affine
- **2.2** Electrode segmentation: HU > 3000 threshold → 3D Connected Component Analysis → centroids
- **2.3** Brain-shift correction: snap centroids to nearest pial surface vertex
  - ⚠️ Only meaningful for **ECoG** (surface grids). For **sEEG** (depth), large distances (30–120 mm) are expected and correct.

### Phase 3 — Anatomical Labeling (Weeks 6–8)
- **3.1** MNI normalisation via FreeSurfer `talairach.xfm` (tkRAS → MNI Talairach)
- **3.2** Brodmann lookup via FreeSurfer `BA_exvivo.annot` surface annotations (offline, no network)
- **3.3** Validation: Mean Euclidean Error vs. ground truth JSON

### Phase 4 — Visualization & Delivery (Weeks 9–10)
- **4.1** 3D render: PyVista (interactive) with matplotlib fallback
- **4.2** CSV / Excel report: `[Electrode_ID, X_mm, Y_mm, Z_mm, Brodmann_Area, Anatomy_Label]`
- **4.3** CLI: `python main.py --mri <path> --ct <path> --subject-dir <path>`

---

## Key Mathematical Constraint

All coordinate transforms follow:

```
P_target = M_affine · P_source
```

Applied at every stage: CT voxel → scanner RAS → tkRAS → MNI.
