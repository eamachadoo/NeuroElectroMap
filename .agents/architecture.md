# NeuroElectroMap — Architecture & Coordinate Systems

## Pipeline Data Flow

```
MRI (.nii.gz)  ──► reorient RAS+ ──► brain mask ──► mri_masked.nii.gz
CT  (.nii.gz)  ──► reorient RAS+ ──┐
                                    ├──► dipy rigid registration ──► ct_registered.nii.gz
                                    │         (Mutual Information)
                                    │         output: 4×4 affine + resampled CT in MRI space
                                    │
                              ct_registered ──► HU > 3000 threshold
                                             ──► 3D CCA (scipy.ndimage.label)
                                             ──► electrode centroids (voxel → scanner RAS)
                                                        │
                                              scanner RAS → tkRAS (via T1.mgz vox2ras/vox2ras_tkr)
                                                        │
                                              brain-shift correction (nearest pial vertex)
                                                        │
                                              tkRAS → MNI Talairach (talairach.xfm)
                                                        │
                                              Brodmann lookup (BA_exvivo.annot)
                                                        │
                                              CSV/Excel report + 3D render
```

---

## Coordinate Spaces (Critical)

Three distinct coordinate systems are used. Confusing them causes errors of 50–150 mm.

| Space          | Origin                        | Used for                              |
|----------------|-------------------------------|---------------------------------------|
| **Scanner RAS**| MRI scanner isocentre         | NIfTI affine output, electrode mm coords from registered CT |
| **tkRAS**      | Centre of FOV (FreeSurfer)    | Pial surface vertices, surface annotations |
| **MNI Talairach** | Standard template brain    | Atlas lookup, cross-subject comparison |

### Converting between spaces

```python
# Scanner RAS → tkRAS  (required before brain-shift correction)
t1_mgz = nibabel.load("sample_seeg/mri/T1.mgz")
scanner_to_tkr = t1_mgz.header.get_vox2ras_tkr() @ np.linalg.inv(t1_mgz.header.get_vox2ras())
coord_tkr = (scanner_to_tkr @ np.append(coord_ras, 1.0))[:3]

# tkRAS → MNI Talairach  (via talairach.xfm parser in main.py)
mni_coord = (patient_to_mni @ np.append(coord_tkr, 1.0))[:3]
```

---

## Module Responsibilities

| File                    | Phase    | Key functions                                      |
|-------------------------|----------|----------------------------------------------------|
| `src/loader.py`         | 1        | `load_nifti`, `get_affine`, `reorient_to_ras`, `apply_brain_mask` |
| `src/registration.py`   | 2.1      | `register_ct_to_mri`, `apply_affine_to_points`     |
| `src/segmentation.py`   | 2.2–2.3  | `segment_electrodes`, `correct_brain_shift`         |
| `src/labeling.py`       | 3.1–3.3  | `normalize_to_mni`, `lookup_brodmann_surface`, `compute_euclidean_error`, `export_report` |
| `src/visualization.py`  | 4.1      | `plot_electrodes` → `plot_3d_pyvista` / `plot_3d_matplotlib` |
| `main.py`               | 4.3      | CLI entry point, orchestrates all phases           |
| `scripts/download_data.py` | —    | Downloads MNE sample sEEG dataset (MRI + CT)       |

---

## CLI Reference

```bash
python main.py \
  --mri         <path/to/T1.nii.gz>          # Pre-operative MRI
  --ct          <path/to/CT.nii.gz>          # Post-operative CT
  --subject-dir <path/to/freesurfer/subject> # FreeSurfer subject dir (surf/, mri/, label/)
  --output-dir  outputs/                     # Default: outputs/
  --format      csv|xlsx                     # Default: csv
  --plot                                     # Save 3D render to outputs/figures/
  --validate    <path/to/ground_truth.json>  # Optional: compute Euclidean error
```

Ground truth JSON format:
```json
[{"id": 1, "gt_mm": [x, y, z]}, {"id": 2, "gt_mm": [x, y, z]}]
```

---

## Output Structure

```
outputs/
├── processed/
│   ├── mri_masked.nii.gz       # Brain-masked MRI
│   └── ct_registered.nii.gz    # CT resampled into MRI space
├── figures/
│   └── electrodes_3d.png       # 3D render (if --plot)
└── reports/
    └── electrode_report.csv    # Final results table
```
