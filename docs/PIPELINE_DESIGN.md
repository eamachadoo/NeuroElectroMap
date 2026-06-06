# Pipeline Design Rationale

This document is a companion to the Redmine "Development" wiki pages.
The Redmine describes *what* each step of the NeuroElectroMap pipeline
does; this document records *why* each step was implemented the way it
was. For every decision point, it states the clinical and technical
forces that motivated it, lists the alternatives that were weighed
(tested, conceptually discarded, or ruled infeasible), and closes with
a short justification of the choice that shipped.

The document is organised by the same five development phases as the
Redmine, then refined down to the atomic design choices inside each
phase. Where a choice has been revisited during validation work, the
table also records the next-step option that is documented separately
in [`VALIDATION_FINDINGS.md`](VALIDATION_FINDINGS.md).

---

## Phase 1 — Data Loading & Preparation

### 1.1 NIfTI as the canonical input format

**Rationale.** The clinical constraint is interoperability with
PACS/DICOM-derived neuroimaging tooling and with BIDS datasets such as
OpenNeuro ds004473. The technical constraint is that the pipeline must
read both T1w MRI and post-operative CT without modality-specific
loaders, and must preserve the affine that anchors voxel coordinates
to scanner-RAS millimetres.

| Method | Criterion | Result | Why |
|---|---|---|---|
| nibabel `nib.load` (chosen) | I/O simplicity + affine fidelity | Tested, shipped | Pure-Python, no system deps, returns affine + header without lossy conversions |
| SimpleITK | Affine handling | Conceptually discarded | Requires the ITK C++ runtime; adds install friction without removing any nibabel limitation |
| DICOM at source | Closer to clinical reality | Inviable | Out of scope — datasets we target ship NIfTI; DICOM would require de-anonymisation step |
| Custom binary parser | Removes a dependency | Conceptually discarded | No upside; NIfTI is already a thin header + raw data |

**Justification.** nibabel is the standard NIfTI/MGZ loader in the
Python neuroimaging stack (nilearn, MNE, dipy all consume nibabel
images). Picking it removes any need to translate between in-memory
representations later in the pipeline and means the affine is the
exact one written by the scanner — no implicit resampling.

### 1.2 Reorientation to canonical RAS+

**Rationale.** Scanner-acquired NIfTIs are not guaranteed to be RAS+:
DICOM converters such as `dcm2niix` can emit LPS, SAR, or arbitrary
axis permutations depending on the acquisition. Downstream code
(electrode coordinates, MNI transforms, viewer rendering) assumes
RAS+. A silent left/right swap produces mirrored anatomy that looks
plausible to a casual viewer but would mislabel a patient's
hemispheres.

| Method | Criterion | Result | Why |
|---|---|---|---|
| `nib.as_closest_canonical` (chosen) | Robust + standard | Tested, shipped | Reorients image and affine in lockstep; idempotent for inputs already in RAS+ |
| Assume RAS+ | Zero cost | Conceptually discarded | One mis-oriented input would silently invert the anatomy |
| Reorient to LPS | Matches ITK convention | Conceptually discarded | FreeSurfer surfaces and MNI templates are RAS+ — LPS would force more conversions downstream |
| External `fslreorient2std` | Standard FSL behaviour | Conceptually discarded | Adds an FSL dependency for a one-line nibabel call |

**Justification.** The reorientation is a single line of nibabel code
that handles the only failure mode we cannot detect at runtime
(mirrored anatomy). Done eagerly at load time it disappears from the
rest of the codebase and the rest of the pipeline can assume RAS+
without checking.

### 1.3 Brain masking with nilearn

**Rationale.** Mutual-information registration sees both intra-cranial
signal and the soft-tissue / air gradient outside the skull. The
out-of-brain content is dominated by the head outline, which is
different between pre-operative T1w and post-operative CT (scalp
retraction, surgical pads, head holder); leaving it in lets MI lock
onto a surface that genuinely moved. The clinical constraint is that
we must not erase brain tissue along with the skull.

| Method | Criterion | Result | Why |
|---|---|---|---|
| `nilearn.masking.compute_brain_mask` | No external deps + good for T1w | Tested, kept available but disabled for registration | Already in our dependency tree; works on a single T1 without FS reconstruction |
| Use FreeSurfer `brain.mgz` | Highest quality mask | Conceptually discarded for the MRI step | Would tie even the first registration to a FreeSurfer recon — the pipeline must run on subjects who have not yet been reconstructed |
| ANTs `antsBrainExtraction` | Robust segmentation | Conceptually discarded | Heavy dep + slow; gain over nilearn is marginal on the inputs we accept |
| No masking | Simplest path | Tested, currently used for registration | The current `register_ct_to_mri` deliberately uses the unmasked T1 (see `src/registration.py` and §2.4) because masking zeros valid tissue near the brain rim and confuses MI |

**Justification.** Brain masking is available for downstream coordinate
filtering but the registration step explicitly skips it: empirically
the full T1 outline gives MI more to lock onto, and the brain-shift
project step (§3.4) already filters anything that lands outside the
pial surface.

---

## Phase 2 — Fusion: CT-to-MRI Registration

### 2.1 Rigid-body 6-DOF model

**Rationale.** CT and T1w are the same patient on the same skull;
intracranial geometry does not stretch or shear between acquisitions.
The clinical constraint is that electrode contacts are sub-millimetre
metal objects whose true position is the only thing we measure — any
warp baked into the registration would relocate them by exactly the
warp magnitude. Therefore the registration must capture rigid
displacement and rotation only.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Rigid 6-DOF (chosen) | Physiologically correct | Tested, shipped | 3 translations + 3 rotations is exactly the freedom a head has between two scans of the same patient |
| Affine 12-DOF | Absorbs subtle scanner-scale differences | Conceptually discarded | The extra 6 DOF (scaling + shear) would mask, not fix, geometric scanner distortion (e.g. O-arm cone-beam) and could move electrodes by mm |
| Non-rigid (SyN, B-spline) | Highest residual reduction | Conceptually discarded | Warps the brain interior; would move electrodes by the same field as the warp, defeating the entire measurement |
| Identity (assume aligned) | Simplest | Conceptually discarded | Scanner origins differ by ~100 mm between modalities — would never align |

**Justification.** 6-DOF rigid is the only model whose only failure
mode is "not enough freedom"; any larger model adds freedom that the
underlying physics does not have. If 6-DOF cannot capture the residual
error (see §2.4 and `VALIDATION_FINDINGS.md`) the fix is to change
metric or initial pose, not to add DOFs.

### 2.2 Similarity metric: Mutual Information

**Rationale.** CT and T1w have unrelated intensity scales: bone is
bright in CT and dark in T1; CSF is dark in CT and dark in T1; grey
matter is mid-grey in CT and mid-grey-ish in T1. No simple intensity
correspondence holds, so any metric that assumes one (SSD, NCC) fails.
Mutual Information measures statistical dependence between intensity
histograms and is the standard cross-modal metric in the literature.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Mutual Information (chosen) | Cross-modal standard | Tested, shipped | Implemented in dipy with multi-resolution pyramid; well-understood failure modes |
| Normalised Cross-Correlation | Cheaper to compute | Conceptually discarded | Assumes linear intensity correspondence — false for CT/T1 |
| Sum of Squared Differences | Cheapest | Conceptually discarded | Same as NCC: requires same-modality |
| Boundary-Based Registration (bbregister) | Documented sub-mm on CT/T1 | Conceptually adopted as future work | Requires FreeSurfer binaries; documented as the §9.1 next step in VALIDATION_FINDINGS — expected to drop residual error from ≈18 mm to <2 mm |

**Justification.** MI is the cheapest cross-modal metric that does not
make unfounded intensity assumptions, and dipy ships a tested
implementation. Empirically (VALIDATION_FINDINGS §7) MI converges to
its global optimum on the ds004473 sub-12 O-arm CT but that optimum is
not the geometrically correct pose — a known limitation that motivates
the bbregister roadmap entry without invalidating the current default.

### 2.3 Initial alignment: centres of mass

**Rationale.** MI optimisers are gradient descents over a non-convex
surface. Starting from identity when the two scanners have ~100 mm
origin offsets (typical when CT and MRI are acquired in different
sessions) puts the optimiser on the wrong side of the global minimum
basin and produces nonsense.

| Method | Criterion | Result | Why |
|---|---|---|---|
| `transform_centers_of_mass` (chosen) | Robust + zero extra input | Tested, shipped | Handles arbitrary scanner-origin offsets; computed from the same images already in memory |
| Identity start | Simplest | Tested in development | Diverged; confirmed COM is necessary for our inputs |
| Anatomical landmark (AC/PC) | Higher quality start | Conceptually discarded | Requires landmark picking — manual step contradicts automation goal |
| Oracle GT-centroid start | Best possible | Tested as diagnostic | Confirmed in VALIDATION_FINDINGS §7 that even an oracle start converges to the same wrong MI maximum — proves the issue is the metric, not the start |

**Justification.** COM pre-alignment is the cheapest correct answer
when both the static and moving images are available with affines.
Subsequent diagnostics show that further work on the initial pose is
not the leverage point — the metric is — so we keep COM and invest the
next iteration elsewhere.

### 2.4 CT HU windowing

**Rationale.** Raw CT spans roughly [-1024, 3071] HU. Bone (200–1500
HU) and electrode metal (>3000 HU) are bright; brain tissue lives in
a narrow band around 0–100 HU. Whichever range dominates the
histogram dominates the MI metric. The choice is whether we want MI
to align by the bone outline, by the soft-tissue gradient, or by both.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Soft-tissue clip [-100, 200] (current default) | Focus MI on intracranial gradient | Tested, shipped | Avoids bone histogram swamping the metric; matches dipy / clinical MI examples |
| Bone-only [100, 1500] | Use skull shell as registration anchor | Tested in VALIDATION_FINDINGS §6 | Marginal improvement (18.3 mm mean vs 20.3 mm) — kept available via `ct_clip` parameter but not the default |
| Bone + soft tissue [-100, 1500] | "Use both" | Tested, ruled out | Catastrophic: COM pre-alignment diverged by ~190 mm because the histogram is bimodal |
| No clip [-1024, 3071] | Let MI choose | Tested, equivalent to default | Same convergence as soft-tissue clip (the >200 HU mass dominates anyway) |

**Justification.** The soft-tissue clip is kept as the production
default because it is the most conservative choice and the cross-window
sweep showed no clip choice escapes the ~18 mm floor on the O-arm CT.
The `ct_clip` parameter is exposed on `register_ct_to_mri` so future
diagnostics and per-dataset overrides do not need to fork the function.

---

## Phase 3 — Electrode Segmentation & Brain-Shift

### 3.1 HU threshold (>3000)

**Rationale.** Implanted SEEG/ECoG electrodes are metallic (platinum,
stainless steel) and saturate the CT scale, while bone tops out
around 1500 HU. A simple high-pass threshold cleanly separates the
electrode signal from everything else without any prior on where
electrodes should be.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Global threshold >3000 HU (chosen) | Cheapest, modality-stable | Tested, shipped | Saturated-metal voxels are well above bone in every clinical CT we accept |
| >1000 HU | Wider safety margin | Conceptually discarded | Includes bone and surgical clips; would require an order-of-magnitude more post-filtering |
| >5000 HU | Stricter | Conceptually discarded | Misses electrodes affected by partial-volume effects (small contacts on thin slices read below saturation) |
| Adaptive (top-percentile per patient) | Robust across scanners | Conceptually discarded | Adds per-patient calibration without measurable benefit on the datasets we tested |

**Justification.** A fixed high threshold keeps the segmentation
deterministic and patient-independent and pushes the disambiguation
work into the later shape filter where it belongs.

### 3.2 3D Connected Component Analysis

**Rationale.** A binary threshold mask is a cloud of bright voxels;
the clinical unit is "one electrode contact". CCA groups
6-connected (or 26-connected) bright voxels into objects with
centroids, sizes, and shapes, which is the natural representation for
downstream filtering.

| Method | Criterion | Result | Why |
|---|---|---|---|
| `scipy.ndimage.label` + `skimage.regionprops` (chosen) | Standard, fast | Tested, shipped | Order of milliseconds on a 512³ CT; gives centroid and inertia tensor in one pass |
| Watershed segmentation | Splits merged blobs | Conceptually discarded | Overkill for binary masks; CCA already separates spatially disconnected metal |
| DBSCAN on coordinate list | Density-based | Conceptually discarded | Pays O(N²) over voxel coordinates for a problem CCA solves in O(V) over the volume |
| Template matching against a contact model | Highest geometric accuracy | Conceptually discarded | Requires a template per electrode type; ds004473 ships heterogeneous shafts |

**Justification.** CCA is the only step that turns voxels into
candidate objects without imposing any geometric prior. We keep the
geometry-free representation as long as possible because every prior
risks missing a contact that the prior did not anticipate.

### 3.3 Size and shape filters

**Rationale.** CCA on the raw mask produces hundreds of components;
most are not electrode contacts (cable artefacts, surgical hardware,
sub-voxel noise). The filter must remove these false positives
without losing real contacts. The clinical constraint is that a
missed contact is a clinical error; a kept artefact is only a viewer
annoyance.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Size 3–500 vox + elongation ≤5 (chosen) | Empirical, transparent | Tested, shipped | On ds004473 sub-12 rejects 72 by size + 15 by shape; 213 candidates retained, in line with the expected ≈100–200 real contacts |
| Size filter only | Simpler | Tested in development | Lets through cable components (long thin metal sleeves saturating CT) — visually polluting the viewer |
| Shape filter only | Stricter | Conceptually discarded | Lets through single-voxel saturation artefacts |
| ML classifier on patch features | Highest specificity | Conceptually discarded | No labelled training data; not justifiable for the current dataset coverage |
| Restrict to brain mask | Eliminate scalp/holder | Conceptually discarded | Real contacts near burr holes can score "out-of-brain" on a tight mask; would lose true positives |

**Justification.** Two cheap, orthogonal filters together remove the
clearly non-anatomical components without imposing per-patient
priors. The remaining false positives (cable segments inside the
volume) are documented as a known limitation in
[Redmine §4.1.1](#) and motivate the geometric shaft-clustering work
that the shaft-aware matcher already partially uses.

### 3.4 Brain-shift correction: project to nearest pial vertex

**Rationale.** Detected centroids sit at the CT contact position,
which after CT→MRI registration is close to the cortex but not
guaranteed to be *on* the pial surface. The clinical convention for
surface electrodes is the cortical point; for depth electrodes the
contact's volumetric position. The chosen rule is: snap to the
nearest pial vertex and additionally record the snap distance, so the
caller can decide which version to use per electrode.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Nearest pial vertex (chosen) | Cheap + recoverable | Tested, shipped | Produces a clean surface coordinate; original CT centroid stays in the electrode dict so depth contacts still have their true position |
| Skip correction | Simplest | Conceptually discarded | Surface-electrode visualisation would draw contacts hanging in space above the cortex |
| Sub-pial projection at fixed offset | Anatomically more correct | Conceptually discarded | Requires per-electrode-type offset; not present in our metadata |
| Trajectory-fit (per shaft) | Best for depth contacts | Documented as next step | Belongs to the same family as the shaft-aware matcher (§4.4); future iteration |

**Justification.** Snapping to the pial surface is reversible (we
keep both coordinates) and gives clinicians a single canonical
"display" coordinate. Depth-contact precision is preserved because
the volumetric ASEG labelling (§4.3) operates on the original
centroid, not on the snapped one.

---

## Phase 4 — Anatomical Labelling

### 4.1 MNI Talairach normalisation via `talairach.xfm`

**Rationale.** MNI coordinates are the lingua franca of inter-subject
neuroscience: they let two patients' contacts be compared even when
their native scans differ in size and orientation. The constraint is
that the conversion must be deterministic and reproducible per
patient and must not require a runtime web download.

| Method | Criterion | Result | Why |
|---|---|---|---|
| FreeSurfer `talairach.xfm` linear matrix (chosen) | Deterministic, already on disk | Tested, shipped | Parsed directly from the plain-text file in `mri/transforms/`; no extra tooling |
| ANTs SyN to MNI152 | Non-linear, more accurate | Conceptually discarded | Heavy install + per-patient compute; gain over linear Talairach not justified for a *display* coordinate |
| Online template fetching (e.g. nilearn `fetch_icbm152`) | Avoids local file dep | Conceptually discarded | Runtime web dependency breaks reproducibility and offline use |
| Skip normalisation | Stay in tkRAS | Conceptually discarded | Removes any cross-subject comparison capability planned in the multi-patient viewer |

**Justification.** Reading the linear `talairach.xfm` keeps the
pipeline offline-reproducible and matches what every other FreeSurfer
consumer does. Non-linear MNI registration is an explicit non-goal
because the pipeline already produces patient-native labels via
BA_exvivo and aparc+aseg, which are anatomically more accurate per
patient than an MNI-projected template would be.

### 4.2 Cortical labelling via `BA_exvivo.annot`

**Rationale.** Brodmann areas remain the most clinically understood
cortical parcellation for presurgical planning. The constraint is
that the labelling must reflect the patient's own anatomy, not a
template warped from another patient.

| Method | Criterion | Result | Why |
|---|---|---|---|
| FreeSurfer `BA_exvivo.annot` per vertex (chosen) | Patient-specific surface labels | Tested, shipped | Already in the FS recon; nearest-vertex lookup is O(log V) with a KD-tree |
| Volumetric Brodmann atlas in MNI | One file, no surface | Conceptually discarded | Requires MNI normalisation and loses per-patient sulcal/gyral detail |
| Online nilearn fetch (`fetch_juelich`) | Modernised atlas | Conceptually discarded | Runtime web dependency; Juelich does not map cleanly onto classical BA numbering used clinically |
| Manual labelling | Highest accuracy | Inviable | Defeats automation goal |

**Justification.** BA_exvivo is the recommended surface atlas for
clinical Brodmann labelling and ships with every FreeSurfer
reconstruction. Pairing it with a KD-tree over the pial vertices is
the textbook implementation and matches the workflow that the FS
documentation suggests.

### 4.3 Subcortical labelling via `aparc+aseg.mgz`

**Rationale.** Many SEEG contacts sit in mesial structures
(hippocampus, amygdala, entorhinal cortex) or in subcortical nuclei
(thalamus, putamen). BA_exvivo only labels the cortical surface;
those depth contacts need a volumetric label.

| Method | Criterion | Result | Why |
|---|---|---|---|
| FreeSurfer `aparc+aseg.mgz` voxel lookup (chosen) | Covers cortex + subcortex | Tested, shipped | Single volume gives Desikan-Killiany cortical parcels and aseg subcortical labels |
| Harvard-Oxford atlas in MNI | Open, well-documented | Conceptually discarded | Template-warped; less patient-specific than the FS recon already on disk |
| AAL atlas | Common in fMRI | Conceptually discarded | Same as Harvard-Oxford: template-based |
| DKT only (no aseg) | Drop subcortical | Conceptually discarded | Would silently mislabel depth electrodes as cortical |
| Nearest-labelled-voxel fallback (`_find_nearest_labeled_voxel`) | Robustness | Added on top of chosen method | A contact slightly outside its true label (sub-voxel registration residual) is rescued by a 5 mm radius search |

**Justification.** Aparc+aseg is the single volumetric map that
covers both cortex and subcortex with consistent ID numbering. The
nearest-labelled-voxel rescue handles the realistic case of a contact
landing one voxel outside its target structure due to registration
sub-millimetre noise.

### 4.4 Validation matcher — *shaft-aware*

**Rationale.** Validation needs to pair each detected contact with
its ground-truth counterpart so a Euclidean distance can be reported.
The constraint, surfaced by VALIDATION_FINDINGS §2–§3, is that naive
matchers produce numbers that say more about the matcher than about
the registration.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Nearest-neighbour (original) | Simplest | Tested, replaced | Allowed many GT contacts to claim the same predicted; inflated some pairs and deflated others |
| Hungarian one-to-one over full cost matrix | Honest exclusivity | Tested, replaced | Removes collisions but, lacking anatomical priors, swaps adjacent shafts and reports a higher mean than before (27.9 mm) |
| **Shaft-aware: PCA axis per shaft + local Hungarian** (chosen) | Anatomically constrained one-to-one | Tested, shipped | Falls back to flat Hungarian when GT lacks shaft prefixes; restores monotonic intra-shaft assignments (see VALIDATION_FINDINGS §4) |
| Manual contact-by-contact pairing | Reference accuracy | Inviable | Defeats automation; ~120 contacts per patient |
| Per-shaft predicted clustering (so predicted electrodes also carry shaft IDs) | Closes the loop | Documented as future work | Would let two-stage shaft-to-shaft matching work even on datasets where the GT doesn't already split shafts |

**Justification.** Shaft-aware matching is the cheapest method that
uses anatomical information already present in the GT (the clinical
name prefix) without depending on the predicted side carrying any
extra structure. The implementation falls back to plain Hungarian on
GT formats that don't expose shaft names, so the API surface is
unchanged for the MNE sample dataset and any future integer-only GT.

---

## Phase 5 — Execution, BIDS Compliance, and Outputs

### 5.1 BIDS-aware ground-truth loading

**Rationale.** ds004473 and other OpenNeuro electrophysiology
datasets ship GT as BIDS TSV files with sidecar JSON declaring units
and coordinate frame. The constraint is that the pipeline must not
silently consume a TSV in metres as if it were millimetres, nor a
scanner-RAS file as if it were ACPC.

| Method | Criterion | Result | Why |
|---|---|---|---|
| BIDS TSV reader + `_detect_tsv_units` + `_detect_tsv_frame` (chosen) | Honour BIDS metadata | Tested, shipped | Inspects the companion `*_coordsystem.json` and falls back to coordinate-magnitude heuristic |
| TSV only, assume mm | Simplest | Conceptually discarded | Silent failure when a BIDS sidecar declares units in `m` |
| JSON only (custom format) | Smaller surface | Conceptually discarded | Non-portable; BIDS is the dataset standard |
| External BIDS validator | Schema-strict | Conceptually discarded | Heavy dep for one TSV read |

**Justification.** Reading the sidecars and converting units at the
boundary keeps the rest of the pipeline in a single coordinate frame
(mm in T1w ScanRAS), which is the only frame in which everything
downstream — segmentation, labelling, validation — agrees.

### 5.2 Report export (CSV + Excel)

**Rationale.** Clinicians consume tables, not JSON. The constraint
is that the report must be openable in Excel or LibreOffice without
extra tooling, and reproducible from the same in-memory data
structure that drives the viewer.

| Method | Criterion | Result | Why |
|---|---|---|---|
| pandas DataFrame → CSV / XLSX (chosen) | Clinical-friendly | Tested, shipped | One write step covers both formats; column schema lives in `export_report` |
| JSON only | Programmatic friendliness | Conceptually discarded | Excel-hostile; viewer already has the JSON |
| HTML | Browser-friendly | Conceptually discarded | Not editable in spreadsheets |
| PDF | Print-ready | Conceptually discarded | Overkill; users can print Excel themselves |

**Justification.** CSV/XLSX through pandas is the standard pair for
clinician handoff and we already depend on pandas for tabular work,
so no new dep is introduced.

---

## Phase 6 — Interactive Viewer

### 6.1 React + Plotly.js, no build step

**Rationale.** The viewer must run from a directory that can be
served by a one-line HTTP server or opened locally without
installation, and must render an interactive 3D mesh with
sub-100 ms hover. The constraint is zero clinical-IT friction.

| Method | Criterion | Result | Why |
|---|---|---|---|
| React + Babel-standalone + Plotly (chosen) | No build step | Tested, shipped | JSX is transpiled in the browser; `make viewer` serves a static folder |
| Vite/Webpack React | Production-grade tooling | Conceptually discarded | Adds a Node/npm dependency for a single-purpose viewer |
| Pure JS + DOM | No bundler nor JSX runtime | Conceptually discarded | State management for the side-panel + selection model would be verbose |
| Streamlit | Python-only | Conceptually discarded | Server-bound; rendering perf insufficient for 30 k-vertex mesh interaction |

**Justification.** Babel-standalone + Plotly gets us React component
ergonomics without committing to a Node toolchain. Performance is
adequate (Plotly Mesh3d handles the decimated meshes interactively)
and the bundle is self-contained.

### 6.2 2D schematic colouring by lobe / sub-region

**Rationale.** The 2D view is an at-a-glance anatomical reference:
clinicians need to identify regions even when no electrode is mapped
into them. The constraint is that every schematic region must carry
a recognisable colour regardless of which BAs the patient happens to
have.

| Method | Criterion | Result | Why |
|---|---|---|---|
| SVG paths with `default_color` per region (chosen) | Always-readable atlas | Tested, shipped | Each schematic region has a hex fallback even when no BA is present in this patient |
| Colour only regions with electrodes | "Show what we have" | Conceptually discarded | Schematic would be mostly transparent on patients with sparse coverage |
| Brodmann-only colouring | Match labels | Conceptually discarded | Lobes themselves would lose colour identity; users have to learn 28 BA colours instead of 4 lobes |
| No atlas, pure scatter | Simpler | Conceptually discarded | Loses the entire educational/navigational value of the 2D view |

**Justification.** A static atlas-style colouring makes the 2D view
useful as a reference even when no electrodes land in a given lobe.
The same hex palette is shared with the Python export (`BA_GROUPS`
in `scripts/export_for_viewer.py`) so the data path and the static
schematic cannot drift apart.

### 6.3 3D colouring with lobe fallback via `aparc.annot`

**Rationale.** Until this iteration, the 3D mesh coloured each
vertex by its BA only — BA_exvivo only labels about 10 % of the
cortex, so most of the 3D brain rendered as the neutral cortex
fallback and the 3D view felt visually disconnected from the 2D
schematic.

| Method | Criterion | Result | Why |
|---|---|---|---|
| BA-only colouring (original) | Matches BA atlas exactly | Tested, replaced | Most vertices fell to the grey fallback; visually inconsistent with the 2D schematic |
| **BA + Desikan-Killiany lobe fallback** (chosen) | Anatomical atlas feel | Tested, shipped | Each vertex gets BA if known, else the lobe colour from `lh.aparc.annot`; ~93–95 % cortex coverage on sub-12 |
| Full per-parcel palette | Most colours | Conceptually discarded | 34 DK parcels per hemisphere produces a busy view; the four-lobe rollup matches the 2D legend |
| Switchable palette themes | UX flexibility | Documented as future work | One-line addition once the lobe scheme stabilises |

**Justification.** Falling back through `aparc.annot` reuses
FreeSurfer data the pipeline already needs for the volumetric
labelling, so the only cost is one extra annot read in the export
script and one extra label array in the per-hemisphere JSON. The
viewer code path stays a single switch (`ba ?? lobe ?? fallback`),
backwards-compatible with bundles produced before this change (older
JSON simply lacks `lobe_codes` and the code falls through to the
neutral cortex colour).

### 6.4 Multi-patient manifest

**Rationale.** The clinical workflow expects the viewer to host
several patients on the same machine without rebuilds. The
constraint is that adding a patient must not require editing source
code.

| Method | Criterion | Result | Why |
|---|---|---|---|
| Auto-scanned `manifest.js` (chosen) | Drop-in patient bundles | Tested, shipped | The export script rebuilds the manifest each time a bundle lands in `outputs/viewer/<id>/data.json` |
| Hardcoded patient list | Simpler | Conceptually discarded | Editing source for each patient is the friction we explicitly want to avoid |
| Server-side index | Live discovery | Conceptually discarded | Requires a backend; viewer is static |
| File-listing fetch (`/index.html` directory listing) | Server-feature-dependent | Conceptually discarded | Behaviour varies by web server |

**Justification.** The manifest is regenerated by the same
`export_for_viewer.py` step that already writes the per-patient
bundle, so it is impossible to forget to refresh.

---

## Cross-phase trade-offs that did not fit any single section

### A. The registration metric is the leverage point, not the matcher

VALIDATION_FINDINGS §2–§7 show that the matcher rewrites in §4.4
expose, but do not cure, the registration residual. The shaft-aware
matcher is the right validation tool because it is honest about which
contacts the registration places near their true position and which
it places far away. The next-iteration work to close the loop is the
boundary-based registration path (bbregister / ANTs) documented in
VALIDATION_FINDINGS §9.1.

### B. Patient-native labels are preferred to template-warped labels

Phase 4 picks the FreeSurfer-recon-derived atlases (BA_exvivo,
aparc+aseg, `talairach.xfm`) over MNI-warped templates everywhere it
has the option. This single decision propagates a single rule: the
viewer always shows what the patient's anatomy *is*, not what the
MNI-template would project onto it.

### C. Zero-extra-dep defaults, optional escape hatches

Wherever a heavier method exists (ANTs registration, FSL reorient,
nilearn web fetches, FreeSurfer bbregister, antspyx ANTs), the
default is the lighter pure-Python path and the heavier option is
documented as a future improvement with the install cost called out.
This keeps the entry barrier low while leaving the upgrade paths
explicit for future iterations.
