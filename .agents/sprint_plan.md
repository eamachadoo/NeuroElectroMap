# NeuroElectroMap — Sprint Plan

Status: `[x]` Done | `[ ]` Open | `[~]` Partial

---

## Milestone 1 — Project Setup

| ID  | Issue                                              | Status | Notes |
|-----|----------------------------------------------------|--------|-------|
| S-1 | Repo, folder structure, `requirements.txt`         | `[x]`  | Done |
| S-2 | `.gitignore` (Python, data, outputs)               | `[x]`  | Present |
| S-3 | `README.md` with setup, run, dataset instructions  | `[x]`  | Present |
| S-4 | `Makefile` targets: `setup`, `data`, `run`, `test` | `[x]`  | `make setup && make data` fully automates onboarding |

---

## Milestone 2 — Phase 1: Data Preparation (Weeks 1–2)

| ID   | Issue                                              | Status | File |
|------|----------------------------------------------------|--------|------|
| P1-1 | NIfTI loader (`load_nifti`)                        | `[x]`  | `src/loader.py:14` |
| P1-2 | Affine extraction & orientation check              | `[x]`  | `src/loader.py:24` |
| P1-3 | Reorient to RAS+ (`reorient_to_ras`)               | `[x]`  | `src/loader.py:37` |
| P1-4 | Brain masking via nilearn                          | `[x]`  | `src/loader.py:42` |
| P1-5 | Unit tests                                         | `[x]`  | `tests/test_loader.py` |

---

## Milestone 3 — Phase 2: Fusion Engine (Weeks 3–5)

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P2-1 | Rigid CT-to-MRI registration (Mutual Information)  | `[x]`  | `src/registration.py:17` |
| P2-2 | `apply_affine_to_points` utility                   | `[x]`  | `src/registration.py:68` |
| P2-3 | Electrode segmentation (HU > 3000 + 3D CCA)        | `[x]`  | `src/segmentation.py:17` |
| P2-4 | Brain-shift correction (nearest pial vertex)       | `[x]`  | `src/segmentation.py:69` |
| P2-5 | Load real pial surface via MNE                     | `[x]`  | `main.py` — uses `mne.read_surface` for LH+RH pial |
| P2-6 | Unit tests — registration                          | `[x]`  | `tests/test_registration.py` |
| P2-7 | Unit tests — segmentation                          | `[x]`  | `tests/test_segmentation.py` |

---

## Milestone 4 — Phase 3: Labeling & Atlas (Weeks 6–8)

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P3-1 | MNI normalisation (`normalize_to_mni`)             | `[x]`  | `src/labeling.py:19` |
| P3-2 | Patient → MNI warp via `talairach.xfm`             | `[x]`  | `main.py` — `_parse_talairach_xfm` reads FreeSurfer XFM |
| P3-3 | Brodmann lookup via `BA_exvivo.annot` (offline)    | `[x]`  | `src/labeling.py` — `lookup_brodmann_surface`; no network needed |
| P3-4 | Euclidean error validation                         | `[x]`  | `src/labeling.py:121` |
| P3-5 | Unit tests — labeling                              | `[x]`  | `tests/test_labeling.py` |
| P3-6 | Ground-truth dataset for validation                | `[~]`  | ds004473 acquired (Oregon OHSU, real sEEG patients); ground truth TSV identified; unit conversion metres→mm done; nearest-neighbour validation logic still needed |

---

## Milestone 5 — Phase 4: Visualization & Delivery (Weeks 9–10)

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P4-1 | PyVista 3D render + matplotlib fallback            | `[x]`  | `src/visualization.py` |
| P4-2 | CSV / Excel report export                          | `[x]`  | `src/labeling.py:152` |
| P4-3 | CLI (`--mri`, `--ct`, `--subject-dir`, `--plot`)   | `[x]`  | `main.py` |
| P4-4 | End-to-end integration test with real patient data | `[~]`  | ds004473 sub-12 pipeline ran end-to-end; 3D render shows electrodes on brain; BA labels produced; validation logic needs fixing (compare centroid_mm vs GT, nearest-neighbour matching) |
| P4-5 | Unit tests — visualization                         | `[ ]`  | `tests/test_visualization.py` not yet created |

---

## Open Blockers

| Priority | ID   | Issue | Why it blocks |
|----------|------|-------|---------------|
| 🔴 High  | P4-4 | Fix validation logic | Must compare `centroid_mm` (scanner RAS) vs GT, use nearest-neighbour matching, not zip(); pial surface for ds004473 sub-12 is still the MNE sample subject — needs FreeSurfer recon-all on sub-12's T1w |
| 🟡 Med   | P3-6 | Nearest-neighbour matching | 228 detected objects vs ~50 ground truth contacts; zip() silently truncates; need spatial matching |
| 🟢 Low   | P4-5 | Visualization tests | No coverage for `visualization.py` |
