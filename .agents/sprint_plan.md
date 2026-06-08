# NeuroElectroMap — Sprint Plan

Status: `[x]` Done | `[ ]` Open | `[~]` Partial

---

## Milestone 1 — Project Setup

| ID  | Issue                                              | Status | Notes |
|-----|----------------------------------------------------|--------|-------|
| S-1 | Repo, folder structure, `requirements.txt`         | `[x]`  | `03628f8` project setup |
| S-2 | `.gitignore` (Python, data, outputs)               | `[x]`  | Present |
| S-3 | `README.md` with setup, run, dataset instructions  | `[x]`  | Rewritten `c804e9d`; refreshed `185fee6` |
| S-4 | `Makefile` targets: `setup`, `data`, `run`, `test` | `[x]`  | `make setup && make data` fully automates onboarding |
| S-5 | CI/CD via GitHub Actions                           | `[x]`  | `db8d618` — Python 3.11/3.12/3.13 on Ubuntu + 3.13 on macOS |

---

## Milestone 2 — Phase 1: Data Preparation (Weeks 1–2)

| ID   | Issue                                              | Status | File / Commit |
|------|----------------------------------------------------|--------|---------------|
| P1-1 | NIfTI loader (`load_nifti`)                        | `[x]`  | `src/loader.py:14` |
| P1-2 | Affine extraction & orientation check              | `[x]`  | `src/loader.py:24` |
| P1-3 | Reorient to RAS+ (`reorient_to_ras`)               | `[x]`  | `src/loader.py:37` |
| P1-4 | Brain masking via nilearn                          | `[x]`  | `src/loader.py:42` |
| P1-5 | Unit tests                                         | `[x]`  | `tests/test_loader.py` |
| P1-6 | Dataset download robustness                        | `[x]`  | `551025d` — partial-download masquerading as complete fix in `download_ds004473.py` |

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
| P2-8 | Shape filter (elongation ratio) for cable artefacts | `[x]`  | `edf936a` — drops 15 false positives on sub-12 |
| P2-9 | Configurable HU windowing (`ct_clip` parameter)    | `[x]`  | `src/registration.py` — exposed for diagnostic sweeps |

---

## Milestone 4 — Phase 3: Labeling & Atlas (Weeks 6–8)

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P3-1 | MNI normalisation (`normalize_to_mni`)             | `[x]`  | `src/labeling.py:19` |
| P3-2 | Patient → MNI warp via `talairach.xfm`             | `[x]`  | `main.py` — `_parse_talairach_xfm` reads FreeSurfer XFM |
| P3-3 | Brodmann lookup via `BA_exvivo.annot` (offline)    | `[x]`  | `src/labeling.py` — `lookup_brodmann_surface`; no network needed |
| P3-4 | Euclidean error validation (initial NN matcher)    | `[x]`  | `src/labeling.py:121` — superseded by Milestone 7 shaft-aware matcher |
| P3-5 | Unit tests — labeling                              | `[x]`  | `tests/test_labeling.py` — 35 tests |
| P3-6 | Ground-truth dataset for validation                | `[x]`  | ds004473 acquired (OpenNeuro / OHSU); BIDS TSV ingestion via `_detect_tsv_units` + `_detect_tsv_frame` |
| P3-7 | Subcortical labelling via `aparc+aseg.mgz`         | `[x]`  | `src/labeling.py` `lookup_aseg` + `_find_nearest_labeled_voxel` rescue (5 mm radius); regression guard `6ff24f4` |

---

## Milestone 5 — Phase 4: Visualization & Delivery (Weeks 9–10)

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P4-1 | PyVista 3D render + matplotlib fallback            | `[x]`  | `src/visualization.py` |
| P4-2 | CSV / Excel report export                          | `[x]`  | `src/labeling.py:152` |
| P4-3 | CLI (`--mri`, `--ct`, `--subject-dir`, `--plot`)   | `[x]`  | `main.py` |
| P4-4 | End-to-end integration test with real patient data | `[x]`  | ds004473 sub-12 pipeline ran end-to-end; TSV ground-truth loading added to `load_ground_truth` |
| P4-5 | Unit tests — visualization                         | `[x]`  | `tests/test_visualization.py` — 2 smoke tests (matplotlib save path) |

---

## Milestone 6 — Phase 5: Clinical Viewer

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P5-1 | `scripts/export_for_viewer.py` + `--export-viewer` | `[x]`  | Pipeline → `outputs/viewer/data.{json,js}` (mesh decimated to ~33k verts/hemisphere) |
| P5-2 | Viewer shell (`index.html`, `app.jsx`, `regions.js`) | `[x]`  | `7239fe1` — Top bar, 2D/3D toggle, light/dark theme, legend, error screen |
| P5-3 | Side panel (`panel.jsx`)                            | `[x]`  | `7239fe1` — Overview / Region detail / Electrode detail |
| P5-4 | 2D schematic view (`brain2d.jsx`)                   | `[x]`  | `7239fe1` — SVG lateral schematic, BA regions, electrode hover, selection sync |
| P5-5 | 3D anatomical view (`brain3d.jsx`)                  | `[x]`  | `034d764` — Plotly Mesh3d semi-transparent + Scatter3d electrodes |
| P5-6 | Tests + README                                      | `[x]`  | `c804e9d` — 79 tests total, including `test_export_viewer.py` (33 tests); README rewritten |
| P5-7 | Desktop launcher (`pywebview`)                      | `[x]`  | `db8d618` + `0850d70` — `scripts/launch_desktop.py` + `make desktop` |
| P5-8 | Multi-patient comparison view                       | `[x]`  | `c490434` + `f14c294` + `a487bb0` — auto-scanned `manifest.js`, per-patient subdirs `outputs/viewer/<id>/data.json`, dropdown selector for sub-1/2/12 |
| P5-9 | Brain-shift display in tooltips ("X mm from cortex") | `[x]`  | `098ea58` — `pial_distance_mm` surfaced in panel + hover |
| P5-10 | Schematic colouring polish (default colours + click-through) | `[x]`  | `5fe3406` + `cb3bf5a` + `b57fe4c` — every region clickable + coloured even when empty |
| P5-11 | Legend grouping + collapse                          | `[x]`  | `499fd4d` + `dd54020` — grouped by region, collapsed by default with localStorage |
| P5-12 | 3D colouring with lobe fallback via `aparc.annot`   | `[x]`  | BA + DK lobe fallback — ~93–95 % cortex coverage on sub-12 |
| P5-13 | Dev server cache-busting + browser auto-open        | `[x]`  | `a03fb0f` + `1555519` + `07711a3` — mtime-based JSX cache-bust, port 8765 conflict recovery |

---

## Milestone 7 — Validation, Ground-Truth Mode & BIDS Robustness

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| P7-1 | `--use-ground-truth` pipeline mode                  | `[x]`  | `46c6a8a` — GT positions replace CT segmentation; all contacts get clinical names (LTP1, RAHIPP3, …) |
| P7-2 | BIDS TSV unit/frame auto-detection                  | `[x]`  | `_detect_tsv_units` + `_detect_tsv_frame` — reads `*_coordsystem.json` sidecar |
| P7-3 | ACPC coordinate frame fix (30 mm offset bug)        | `[x]`  | `235dbce` — T1w scanner-RAS vs T1.mgz scanner-RAS resolved via ACPC GT |
| P7-4 | Clinical electrode-name rendering fix               | `[x]`  | `a26cc45` — `nemElecLabel` helper; "LSMA14" no longer shown as "ELSMA14" |
| P7-5 | Iteration 1 — Nearest-neighbour matcher (baseline)  | `[x]`  | Mean 22.4 mm — superseded; documented as starting state in `VALIDATION_FINDINGS.md` |
| P7-6 | Iteration 2 — Hungarian one-to-one matcher          | `[x]`  | Mean 27.9 mm — exposed shaft-poaching failure mode |
| P7-7 | Iteration 3 — Shaft-aware matcher (final)           | `[x]`  | `8623bd3` — PCA axis per shaft + local Hungarian; falls back to flat Hungarian for prefix-less GT; mean 8.5 mm at r=10 mm |
| P7-8 | Validation diagnostic scripts                       | `[x]`  | `70d3a5f` — `sweep_registration_window.py`, `oracle_start_registration.py`, `make validate-ds004473` target |
| P7-9 | Validate GT mode on all 3 ds004473 patients         | `[x]`  | sub-1: 119 electrodes / 97 % coverage; sub-2: 121 / 96 %; sub-12: 119 / 98 % |
| P7-10 | Regenerate per-patient viewer bundles               | `[x]`  | `71204c4` + `6607e45` — all three subjects re-exported with shape filter + GT mode |

---

## Milestone 8 — Documentation

| ID   | Issue                                              | Status | Notes |
|------|----------------------------------------------------|--------|-------|
| D-1  | `docs/PIPELINE_DESIGN.md` — design rationale       | `[x]`  | Per-phase comparative analysis (chosen / discarded / inviable) for every decision point |
| D-2  | `docs/VALIDATION_FINDINGS.md` — iteration log      | `[x]`  | `70d3a5f` — 3 matcher iterations + window sweep + oracle start; root-cause analysis pinning failure to MI metric |
| D-3  | Redmine — Design Rationale & Comparative Analysis chapter | `[x]`  | New Chapter 5 with 5.1–5.7 (Phases 1–6 rationale + cross-phase trade-offs) |
| D-4  | Redmine — Validation Iteration Log chapter         | `[x]`  | New Chapter 6 (6.1–6.7) — to be uploaded after D-3 stabilises |
| D-5  | README refresh (counts, limitations, narrative)    | `[x]`  | `185fee6` + `c804e9d` + `241cf7a` — installation guide, end-to-end story, current numbers |

---

## Backlog (future milestones)

| Future | Issue | Status | Notes |
|--------|-------|--------|-------|
| F-1 | **Standalone `.app` / `.exe` bundle (#9b)** | `[ ]` | Package the viewer + pre-built `outputs/viewer/*` with PyInstaller. Scoped viewer-only (no pipeline) — ~150 MB. macOS arm64 from this machine. Documented Windows/Linux build process. No code signing — uses `xattr -cr` workaround. Approved but deferred behind F-2 per user 2026-06-02. |
| F-2 | **Web deployment via GitHub Pages (#9a)** | `[ ]` | Push viewer + per-patient `data.json` to `gh-pages` so the professor accesses it from a public URL — `https://eamachadoo.github.io/NeuroElectroMap/viewer/`. Approved by user 2026-06-02; implementation paused for a bug-fix pass first. Covers 80 % of the distribution need at ~30 min cost. |
| F-3 | **Dataset upload UI** | `[ ]` | Professor uploads their own dataset (BIDS-like, same format as ds004473) through the UI; the pipeline processes it and the result becomes available in the viewer's patient dropdown alongside the existing subjects. MVP ~4–5 h: file picker → server-side make run → manifest refresh. Logged 2026-06-02.|
| F-4 | **bbregister registration backend** | `[ ]` | Substitute MI rigid registration with FreeSurfer boundary-based registration. Expected to drop ds004473 sub-12 residual from ~18 mm to <2 mm. Documented in `VALIDATION_FINDINGS.md` §9.1. Trade-off: makes the pipeline depend on FreeSurfer binaries for best results; MI path remains as no-extra-deps fallback. |
| F-5 | **Shaft-aware predicted clustering** | `[ ]` | Extend the matcher so predicted electrodes also carry inferred shaft IDs, enabling two-stage shaft-to-shaft matching even on datasets where the GT does not split shafts. Documented in `PIPELINE_DESIGN.md` §4.4. |

---

## Open Blockers

None.
