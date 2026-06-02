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
| P3-6 | Ground-truth dataset for validation                | `[x]`  | ds004473 acquired (Oregon OHSU, real sEEG patients); nearest-neighbour validation logic implemented in `compute_euclidean_error` |

---

## Milestone 5 — Phase 4: Visualization & Delivery (Weeks 9–10)

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P4-1 | PyVista 3D render + matplotlib fallback            | `[x]`  | `src/visualization.py` |
| P4-2 | CSV / Excel report export                          | `[x]`  | `src/labeling.py:152` |
| P4-3 | CLI (`--mri`, `--ct`, `--subject-dir`, `--plot`)   | `[x]`  | `main.py` |
| P4-4 | End-to-end integration test with real patient data | `[x]`  | ds004473 sub-12 pipeline ran end-to-end; NN validation logic fixed; TSV ground-truth loading added to `load_ground_truth` |
| P4-5 | Unit tests — visualization                         | `[x]`  | `tests/test_visualization.py` — 2 smoke tests (matplotlib save path) |

---

## Milestone 6 — Phase 5: Clinical Viewer (in progress)

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P5-1 | `scripts/export_for_viewer.py` + `--export-viewer` | `[x]`  | Pipeline → `outputs/viewer/data.{json,js}` (mesh decimated to ~33k verts/hemisphere) |
| P5-2 | Viewer shell (`index.html`, `app.jsx`, `regions.js`) | `[x]`  | Top bar, 2D/3D toggle, light/dark theme toggle, legend, error screen |
| P5-3 | Side panel (`panel.jsx`)                            | `[ ]`  | Overview / Region detail / Electrode detail (no mock signal data) |
| P5-4 | 2D schematic view (`brain2d.jsx`)                   | `[ ]`  | SVG lateral schematic, BA regions, electrode hover, selection sync |
| P5-5 | 3D anatomical view (`brain3d.jsx`)                  | `[ ]`  | Plotly Mesh3d semi-transparent + Scatter3d electrodes |
| P5-6 | Tests + README                                      | `[ ]`  | Smoke tests for export script, viewer usage docs |
| P5-7 | Desktop launcher (`pywebview`)                      | `[ ]`  | `scripts/launch_desktop.py` + `make desktop` — opens the viewer in a native window. Implement after P5-5. |

---

## Backlog (future milestones)

| Future | Issue | Notes |
|--------|-------|-------|
| F-1 | **Multi-patient comparison view** | Compare 2 or more patients side-by-side in the viewer. Requires: (a) export script writes per-patient subdirs e.g. `outputs/viewer/sub-12/data.js`; (b) `viewer/index.js` manifest listing available patients; (c) UI: case selector becomes multi-select, side-by-side or overlay layout; (d) common MNI-space coordinate frame so meshes overlay. Mentioned by user 2026-05-31. |
| F-2 | **Standalone `.app` / `.exe` bundle (#9b)** | Package the viewer + pre-built `outputs/viewer/*` with PyInstaller. Scoped viewer-only (no pipeline) — ~150 MB. macOS arm64 from this machine. Documented Windows/Linux build process. No code signing — uses `xattr -cr` workaround. Approved but deferred behind #9a per user 2026-06-02. |
| F-3 | **Web deployment via GitHub Pages (#9a)** | Push viewer + per-patient `data.json` to gh-pages so the professor accesses it from a public URL — `https://eamachadoo.github.io/NeuroElectroMap/viewer/`. Approved by user 2026-06-02; implementation paused for a bug-fix pass first. Covers 80% of the distribution need at ~30 min cost. |

---

## Open Blockers

None.
