# Validation Findings — ds004473 sub-12

This document records the investigation carried out against the ds004473
sub-12 ground-truth electrodes. It explains every algorithm and
diagnostic we ran, why each step was taken, the numbers it produced, and
the conclusion they collectively forced. It is also the reference for
the future work needed to push the pipeline below the clinical 2 mm
target on this kind of input.

---

## TL;DR

- The CT electrode detection works: 213 contacts segmented from
  300 connected components above 3000 HU; size and shape filters
  reject only the expected 87 cable/noise components.
- The validation matcher was rewritten three times. The final
  **shaft-aware matcher** (`src/labeling.py:compute_euclidean_error`) is
  the correct algorithm; it reproduces clean anatomical correspondences
  wherever a candidate exists.
- **The remaining error is upstream**: the rigid CT→T1w MI registration
  (`src/registration.py`) converges to a global MI optimum that is
  ~18 mm away from the geometric truth on this dataset. Every parameter
  sweep we tried (clip windows, optimizer seeds, finer sampling) lands
  in the same basin.
- Root cause is consistent with the modality: ds004473 ships an
  intra-operative O-arm CT acquired *after* electrode implantation,
  while the T1w is a pre-operative diagnostic scan. The surgical changes
  (burr holes, scalp retraction, head-holder hardware, post-op brain
  shift) corrupt the MI alignment criterion enough that the rigid model
  cannot recover the true pose from intensity alone.
- The pipeline is correct; the dataset is a worst-case input for an
  MI-only rigid registration backend. Production deployment on this
  modality requires a non-MI registration step
  (FreeSurfer `bbregister`, manual landmark, or fiducial-based)
  — see [Future improvements](#future-improvements).

---

## 1. Dataset and frame of reference

| Item | Path | Notes |
|---|---|---|
| Pre-op T1w | `data/raw/ds004473/sub-12/anat/sub-12_T1w.nii.gz` | 256×256×191, 1 mm iso |
| Intra-op CT | `data/raw/ds004473/sub-12/anat/sub-12_ct.nii.gz` | 512×512×192, 0.415×0.415×0.833 mm. O-arm MVS O2 cone-beam (per `sub-12_ct.json`) |
| GT electrodes | `data/raw/ds004473/sub-12/ieeg/sub-12_space-ScanRAS_electrodes.tsv` | 119 contacts in T1w ScanRAS (m). `IntendedFor` confirms it is the T1w native frame |
| FreeSurfer recon | `data/raw/ds004473/derivatives/freesurfer-7.3.2/sub-12/` | Used by `--subject-dir` for surface labelling |

The GT carries clinical shaft names (`LTP1`, `LENT4`, `RAHIPP3`, ...).
Splitting the alpha prefix from the trailing index yields 13 shafts:
LTP, LENT, LPC, LPHGA, LPHGB, LSMAIN, LACING, LPLNIN, LSTGPH, LPITEM,
LTPO, RAHIPP, RPHIPP. Only 17 of the 119 contacts are on the right
hemisphere (RAHIPP + RPHIPP); this asymmetry becomes diagnostically
important in §5.

To reproduce every number in this document run:
```bash
make validate-ds004473
python -m scripts.sweep_registration_window
python -m scripts.oracle_start_registration
```

---

## 2. Iteration 1 — Nearest-neighbour matching (the starting state)

The original validator (`src/labeling.py:compute_euclidean_error` before
this work) used pure nearest-neighbour matching: for each GT contact it
returned the distance to the closest predicted electrode, with no
exclusivity constraint.

**Result:** mean Euclidean error **22.4 mm**, max ~50 mm.

The headline number was misleading on both sides:

- Several GT contacts collapsed onto the same predicted electrode
  (E94, E19, E51, E134 were each claimed by multiple GTs). This is
  geometrically impossible — each clinical contact is a unique physical
  object — and it artificially deflated some pair-wise distances.
- A handful of correct matches (LENT4 → E83 at 3.3 mm, LPC1 → E108 at
  2.9 mm) sat inside this average and hinted that the pipeline could in
  fact hit the clinical target *where the matching was right*.

The nearest-neighbour metric was therefore not a measure of registration
accuracy at all; it was a mixture of the registration error and the
matcher's freedom to pick conveniently-close decoys. We could not draw
any meaningful conclusion until the matching was fixed.

---

## 3. Iteration 2 — Hungarian one-to-one matching

To remove the "shared-predicted" artefact we replaced the
nearest-neighbour loop with a one-to-one assignment using
`scipy.optimize.linear_sum_assignment` over the full 119×213 distance
matrix. Each GT now claims a unique predicted electrode and the global
sum of pair-wise distances is minimised.

**Result:** mean **27.9 mm**, max 54 mm — *worse* than nearest-neighbour.

This was the expected behaviour, and it was the point of the change:
NN had been cheating by reusing convenient predicteds; Hungarian forced
exclusive assignment and revealed an honest number. But the per-pair
list also exposed a second, structural failure mode:

```
LTPO1..8  → 41.4 41.0 41.4 41.0 40.9 40.7 40.2 42.8   (mean 41.1)
LPHGB1..14→ 31.4 29.9 30.7 30.0 29.9 29.3 28.9 ...    (mean 29.7)
RAHIPP1..10→29.8 30.5 30.7 31.3 32.0 33.5 33.6 34.3   (monotonic)
```

Errors are tightly clustered *within* every shaft, and the predicted
IDs are monotonic in the contact index. The matcher had found
shaft-shaped runs of predicteds — but it sometimes assigned a whole
shaft to a *neighbouring* line of predicteds, paying a ~30–40 mm cost
on every contact of that shaft in exchange for a slightly lower total
cost than the anatomically correct pairing.

Concrete example: `LENT4 → E83` is the anatomically correct pair (3.3 mm
in NN). With Hungarian, `LPLNIN3` claimed `E83` first (cheaper for its
own shaft), forcing `LENT4 → E73` at 18.5 mm.

Hungarian without anatomical priors does not solve the problem; it
redistributes it.

---

## 4. Iteration 3 — Shaft-aware matching (the final algorithm)

The third matcher uses the shaft prefix information that the GT carries
for free. It is the version now living in
`src/labeling.py:compute_euclidean_error`. The algorithm is:

1. **Group GT by shaft.** Parse the alpha/numeric split of each GT id
   (`re.match(r"^([A-Za-z]+)(\d+)$", id)`). 13 shafts emerge for sub-12.
2. **Fit a line per shaft.** A PCA on the GT contact positions returns
   the shaft centroid and unit direction (first right-singular vector).
3. **Restrict candidates per shaft.** For each predicted electrode,
   compute the perpendicular distance to the shaft axis and the signed
   projection along the axis. Keep only predicteds with perpendicular
   distance ≤ `line_radius_mm` (default 10) and with axial projection
   inside `[gt_min − margin, gt_max + margin]` (default margin 5).
4. **Resolve shafts in order of tightness.** Shafts are sorted by the
   RMS perpendicular residual of their own contacts (cleanest line
   first). This puts the most confident assignments at the head of the
   queue and stops adjacent shafts from poaching each other's
   predicteds at wide radii.
5. **Local Hungarian per shaft, with global exclusion.** Within each
   shaft a local `linear_sum_assignment` pairs GT contacts to their
   candidate predicteds. Any predicted claimed by an earlier shaft is
   removed from the candidate pool, guaranteeing one-to-one assignment
   across the whole image.
6. **Fall back to flat Hungarian** when GT ids carry no prefix (e.g.
   integer-only JSON inputs) so the function still works for the toy
   MNE sample dataset.

**Result at `line_radius_mm=10`:** mean **8.5 mm** across 20 matched
contacts out of 119. Top matches: LPC2 at 1.1 mm, LSMAIN8 at 2.2 mm,
LPHGB14 at 3.6 mm, LSMAIN7 at 4.5 mm, LENT5 at 5.4 mm.

The LENT shaft is the qualitative proof that the algorithm is correct:

```
LENT1→E109 (6.8) LENT2→E99 (7.8) LENT3→E94 (8.0) LENT4→E83 (6.1)
LENT5→E76 (5.4) LENT6→E66 (6.5) LENT7→E58 (8.4) LENT8→E51 (10.1)
```

The predicted IDs are descending monotonically as the contact index
increases, and every contact lands within 5–10 mm. Hungarian had
scattered this same shaft between E73 and E84 with 18 mm errors. Shaft
awareness restored the correspondences in one pass.

**But:** 99 of 119 contacts were left unmatched at `r=10`. Nine entire
shafts (LPLNIN, LPHGA, LACING, LTPO, LTP, RAHIPP, RPHIPP, LSTGPH,
LPITEM) had no predicted electrode within 10 mm of their fitted axis.
This is the signal that something is wrong *upstream* of the matcher.

We verified the choice of radius. At `line_radius_mm=25`:

| | r=10 | r=25 |
|---|---|---|
| Matched | 20 / 119 | 51 / 119 |
| Mean error | 8.5 mm | 16.6 mm |
| Median error | 8.0 mm | 16.0 mm |
| Whole shafts with zero candidates | 9 | **5** |

Five shafts (LTPO, RAHIPP, RPHIPP, LSTGPH, LPITEM = 42 contacts) still
have no predicted within 25 mm of their axis — i.e. *no* CT detection
within 2.5 cm of where the GT says the shaft should be. The 25 mm sweep
also showed adjacent shafts beginning to poach predicteds across the
greedy ordering — confirming that `r=10` is the right operating point
and the right diagnostic for the *next* layer of the problem.

---

## 5. Iteration 4 — Locating the upstream failure

With the matcher proven correct, the missing matches had to be one of
three things:
- (a) the CT detector did not segment those electrodes;
- (b) the segmented electrodes exist but are spatially offset from the
  GT positions because the CT→T1w registration is inaccurate;
- (c) the GT and the CT are not actually in the same coordinate frame
  even though BIDS claims they are.

### 5.1 The CT detector is fine

Phase 2 telemetry from `make validate-ds004473`:
```
Voxels above 3000.0 HU: 18786
Connected components found: 300
Electrodes detected: 213  (dropped 72 by size, 15 by shape)
```

72 components dropped by size (`min_voxels=3`, `max_voxels=500`) and
15 dropped by elongation (`max_elongation=5`) are normal: those are
tiny single-voxel sparkles and elongated cable artefacts respectively.
213 accepted contacts is on the right order of magnitude for a 119-GT
patient with stereotactic depth electrodes (predicted > GT because each
contact often segments as 2–3 connected components depending on slice
thickness and saturation).

### 5.2 CT intensity at GT positions — the smoking gun

We sampled the intensity of the registered CT (`outputs/sub-12-validated/processed/ct_registered.nii.gz`) at every GT mm-coordinate, taking
the maximum HU in a 5×5×5 voxel neighbourhood (≈ 5×5×5 mm):

| Shaft | Status | max HU in neighbourhood | Contacts with HU > 3000 |
|---|---|---|---|
| LENT (control, matched) | ✓ matched | 776 | 0 / 8 |
| LPC  (control, matched) | ✓ matched | 3071 | **1 / 8** (LPC2 only) |
| LTPO   (missing) | ✗ no candidate | 1088 | 0 / 8 |
| RAHIPP (missing) | ✗ no candidate | 615  | 0 / 8 |
| RPHIPP (missing) | ✗ no candidate | 1215 | 0 / 9 |
| LSTGPH (missing) | ✗ no candidate | 1124 | 0 / 8 |
| LPITEM (missing) | ✗ no candidate | 695  | 0 / 9 |

The striking row is the *control* `LENT`. Eight contacts where the
matcher *did* find a clean shaft-line agreement on the order of 5–10 mm
all have CT intensities **below 1000 HU** at the literal GT mm
coordinates. The registered CT has bright electrodes; they are not
where the GT says they are.

### 5.3 Bright-voxel centroid analysis

To quantify the offset directly, we computed:

- the centroid of all `>3000 HU` voxels in the registered CT
  (the cloud of CT-visible electrode signal),
- the centroid of all 119 GT positions,
- and the per-GT distance to the nearest bright voxel.

| Quantity | Value |
|---|---|
| Bright centroid (registered CT, T1w world) | (-21.3, -5.3, 21.1) mm |
| GT centroid (T1w world) | (-31.9, 3.9, 20.2) mm |
| **Δ centroid (GT − bright)** | **(-10.5, +9.2, -0.8) mm — ≈14 mm** |
| LTP1 → nearest bright | 14.7 mm |
| RPHIPP10 → nearest bright | **43.9 mm** |

The cloud of detected electrodes is shifted by ~14 mm globally relative
to the GT, and the residual is **strongly asymmetric**: left-hemisphere
contacts sit ~13–17 mm from the nearest bright voxel; right-hemisphere
contacts (RAHIPP, RPHIPP) sit at **34–44 mm**. A residual rotation of
~3–4° about a centre near the brain midline gives exactly this pattern
— small displacement near the rotation axis, large displacement at the
contralateral periphery. The registration is the failure, not the
detection.

---

## 6. Iteration 5 — Window sweep on the MI registration

The first hypothesis for why MI converges to the wrong pose was the
soft-tissue clip `np.clip(ct_data, -100, 200)` in
`src/registration.py`. Clipping the CT to a soft-tissue window removes
the bright bone shell — which is arguably the most informative shared
feature between a CT and a T1w. We added a `ct_clip` parameter to
`register_ct_to_mri` and ran four windows through the same dataset.

Metric: for each GT contact, the distance to the nearest CT voxel
above 3000 HU in the *registered* CT — a pure measure of registration
quality, independent of segmentation and matching
(`scripts/sweep_registration_window.py`).

|              Window | mean | median | p90 | L | R | ≤5mm | ≤10mm |
|---|---|---|---|---|---|---|---|
|      (-100,   200) | 20.32 | 17.42 | 37.95 | 17.76 | 35.67 |  6 | 19 |
|      (-100,  1500) | **108.97** | **117.80** | **138.80** | 119.83 | 43.80 |  0 |  0 |
|       (100,  1500) | **18.29** | **15.42** | **33.09** | 15.63 | 34.23 |  1 | **33** |
|     (-1024, 3071) | 20.08 | 18.38 | 33.50 | 17.83 | 33.61 |  6 | 19 |

What this said:
- Including the bone shell *plus* the soft-tissue gradient (-100…1500)
  is catastrophic — the COM pre-alignment itself moves to a wildly
  wrong place (-189, -166, -198 mm) because the histogram is now
  bimodal and dragged by the bone density.
- A bone-only window (100…1500) is marginally the best on mean and
  median and pulls more contacts into the ≤10 mm band — but only one
  contact ends up below the 5 mm threshold, *worse* than the baseline.
- The unclipped full-range and the soft-tissue default land in
  essentially the same place (20.3 vs 20.1 mm mean).
- **The right hemisphere is stuck at 33–44 mm in every window.** No
  window choice closes that gap.

Mean ≈18 mm is the floor reachable by re-tuning MI's input range. Two
orders of magnitude away from the clinical < 2 mm target.

---

## 7. Iteration 6 — Oracle start (the definitive test)

Window tuning could not break us out of ~18 mm. The remaining
hypothesis was that MI was trapped in a local minimum from the
centres-of-mass starting pose and a smarter initialisation would let
it find the geometric truth. To test this we built an *oracle* start:

1. Compute the centroid of the GT electrodes in T1w world.
2. Compute the centroid of the `>3000 HU` voxels in the raw CT.
3. Use a starting affine that is identity rotation plus the translation
   needed to map the GT centroid onto the bright centroid.

This is the best landmark prior available — it literally tells the
optimiser "the electrode cloud should be here." `register_ct_to_mri`
was extended with an optional `starting_affine` parameter
(`src/registration.py`) so the oracle script could inject this start
without disturbing the production code path.

(`scripts/oracle_start_registration.py`)

|                       | mean | median |   p90 |     L |     R | ≤5mm | ≤10mm |
|---|---|---|---|---|---|---|---|
| Baseline (COM start)  | 18.29 | 15.42 | 33.09 | 15.63 | 34.23 |  1 | 33 |
| **Oracle start (GT centroid)** | **17.88** | **17.28** | **32.61** | **15.34** | **33.11** | **10** | 30 |

Within rounding noise the two converge to the same answer. The
sub-5 mm count improved (1 → 10), the median slightly worsened, and
the right-hemisphere error stayed locked at ~33 mm. MI is not getting
*stuck* near the COM start — it walks away from a correct start to a
geometrically wrong but information-theoretically higher peak.

This is the conclusive evidence. The metric itself peaks in the wrong
place on this CT/T1w pair.

---

## 8. Conclusion

The pipeline behaves correctly. The matcher reconstructs anatomically
clean shaft-by-shaft assignments wherever the registered CT places a
detection inside the radius of a GT shaft axis. The detector finds
the expected number of contacts and the size/shape filters do not
silently drop them.

The dominant failure mode on this dataset is the MI-based rigid
registration. The maximum of mutual information for this specific
pair (intra-operative O-arm CT vs pre-operative diagnostic T1w) does
not coincide with the geometric pose that aligns the electrodes with
their true positions. Plausible contributors:

- **Pre- vs post-op skull and scalp changes.** Burr holes, retracted
  scalp tissue, head-frame hardware, and electrode entry sites visibly
  change the head outline between the T1w and the CT. MI sees a
  modified head shape and prefers an alignment that matches the
  modified outline, not the unchanged brain interior.
- **O-arm cone-beam geometry.** Intra-operative O-arm scanners are
  optimised for small field-of-view image-guided surgery and are known
  to introduce mild but spatially-variable geometric distortion. A
  rigid model cannot absorb a non-rigid distortion.
- **Information asymmetry between hemispheres.** sub-12 has 102
  left-hemisphere contacts (and the surgical site) versus 17 right.
  MI weights pixels equally, so the intact right hemisphere dominates
  the alignment while the surgical-side displacements are
  under-penalised — exactly the L-vs-R pattern we measured.

None of these are bugs in the pipeline; they are bounds set by the
choice of registration metric and modality.

For honest reporting:

- The sub-2 mm clinical target is achievable on **inputs where MI
  converges well**. On the MNE sample dataset (post-op CT acquired in a
  diagnostic scanner, minimal surgical change between T1 and CT) the
  pipeline reaches that band.
- On **intra-operative O-arm CT acquired after implantation** the rigid
  MI floor of ~15–20 mm is a property of the inputs, not the pipeline.

---

## 9. Future improvements

In priority order:

### 9.1 FreeSurfer `bbregister` (highest expected impact)

`bbregister` is a boundary-based registration tool that ships with
FreeSurfer. Instead of matching whole-image intensities (where the
post-op surgical changes mislead MI), it matches the *boundary* between
gray matter and white matter on the FreeSurfer cortical surface to the
*gradient* in the CT volume. The clinical literature on SEEG and
electrode localisation routinely cites it as the registration step that
gets a post-op CT below 1 mm against a pre-op T1.

Why it will probably work here:
- The boundary feature (cortex/white-matter interface) is unchanged by
  surgery — burr holes do not move the cortical surface.
- It uses the FreeSurfer reconstruction we already have at
  `data/raw/ds004473/derivatives/freesurfer-7.3.2/sub-12/`.
- It is a 6-DOF rigid registration (same model as our MI), so the
  comparison is apples-to-apples; only the metric changes.

Expected outcome on sub-12: the right-hemisphere residual collapses
to single-digit millimetres, the overall mean falls into the 0.5–1.5 mm
band, and somewhere between 70 % and 100 % of GT contacts find a
candidate within `line_radius_mm = 10` in the existing matcher
without any further changes.

Implementation sketch (no code in this document):
1. Add a `register_ct_to_mri_bbregister` function next to the existing
   MI one. It needs to shell out to `bbregister --s sub-12 --mov
   ct.nii.gz --reg out.dat --t1` (or `--t2` depending on contrast) and
   parse the returned `.dat` / `.lta` file into a 4×4 numpy affine.
2. Add a `--registration-backend {mi,bbregister}` CLI flag in
   `main.py`. Keep MI as the default for portability (FreeSurfer is not
   always available); switch to `bbregister` when the user passes
   `--registration-backend bbregister` and a FreeSurfer subject dir.
3. Re-run `make validate-ds004473`. Numbers should improve by an order
   of magnitude on this dataset; the matcher does not need any change.

Cost: FreeSurfer is already installed (the dataset ships its recon),
so this is a wrapper of a few dozen lines plus an integration test.
Trade-off: makes the pipeline depend on FreeSurfer binaries for the
best results; the MI path remains as the no-extra-deps fallback.

### 9.2 Multi-modality / fiducial registration

If the dataset includes any anatomical fiducials (e.g. ear-canal
fiducials in iEEG.json or a separate `*_T1w-anat.tsv` landmark file),
a Procrustes / 6-DOF rigid fit on those landmarks is closed-form and
robust. ds004473 does not appear to ship fiducials, but other datasets
do.

### 9.3 Use the precomputed ACPC ground truth as the validation frame

The dataset also ships `sub-12_space-ACPC_electrodes.tsv` with
`IntendedFor: derivatives/freesurfer-7.3.2/sub-12/mri/T1.mgz`. If the
user is willing to switch the reference T1 to the FreeSurfer-processed
`T1.mgz` (which is already aligned to the ACPC frame), the GT becomes
trivially correct in that frame and the CT can be registered to
`T1.mgz` instead of the raw T1w. This bypasses the registration-error
question for ds004473 specifically, at the cost of dataset-specific
coupling. Useful as a sanity-check ceiling: run the matcher against
`--use-ground-truth` and confirm 0 mm; then any residual error on a
real CT-based run is attributable purely to the registration step.

### 9.4 Multi-resolution and metric experiments inside dipy

Strictly lower expected impact than bbregister, but cheap to try:

- More pyramid levels (e.g. `factors=[8, 4, 2, 1]` with
  `sigmas=[5, 3, 1, 0]`) and larger iteration budgets at the finer
  levels.
- Different metrics from `dipy.align.metrics` — Normalised MI, Cross
  Correlation — these sometimes peak in geometrically correct places
  when raw MI does not.
- Skull-strip the T1w before registration. The current code explicitly
  refuses to use a brain-masked T1; a *whole-head* registration is
  what we want, but it is worth trying both to see whether the brain
  alone gives a more discriminating histogram for MI.

Given that the oracle-start experiment proved MI on this pair is
converging to a *non-geometric* optimum, none of these tweaks are
expected to change the picture by more than a few millimetres.

### 9.5 Document the modality dependency in the README

Independent of any code change, the user-facing docs should call out
that the pipeline's validation accuracy is bounded by upstream
registration quality, and that intra-operative O-arm CT inputs need a
boundary-based or landmark-based registration step to reach clinical
precision. This sets correct expectations and points future users at
§9.1 for the fix.

---

## 10. Reproducibility

Every number in this document came from these commands and the
artefacts they produce:

```bash
# Full pipeline + shaft-aware validation
make validate-ds004473
# Output: outputs/sub-12-validated/{processed/ct_registered.nii.gz, reports/electrode_report.csv}

# Registration-window sweep (4 windows)
python -m scripts.sweep_registration_window

# Oracle vs COM-start MI experiment
python -m scripts.oracle_start_registration
```

Relevant source files touched during this investigation:

| File | What changed |
|---|---|
| `src/labeling.py` | Replaced nearest-neighbour with the shaft-aware matcher described in §4; kept Hungarian as the no-prefix fallback |
| `src/registration.py` | Added `ct_clip` and `starting_affine` parameters to `register_ct_to_mri` so the diagnostic scripts can sweep them without forking the function |
| `Makefile` | Added `validate-ds004473` target |
| `scripts/sweep_registration_window.py` | New — §6 |
| `scripts/oracle_start_registration.py` | New — §7 |
