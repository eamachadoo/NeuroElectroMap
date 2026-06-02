"""Phase 4 – Task 4.3: CLI Entry Point

Usage:
    python main.py --mri path/to/mri.nii.gz --ct path/to/ct.nii.gz [options]

Options:
    --mri            Path to pre-operative MRI (NIfTI).
    --ct             Path to post-operative CT  (NIfTI).
    --output-dir     Directory for outputs [default: outputs/].
    --format         Report format: csv or xlsx [default: csv].
    --plot           Save a 3D render of the result.
    --validate       Path to ground-truth JSON for error computation.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from src.loader import load_nifti, reorient_to_ras, apply_brain_mask, save_nifti
from src.registration import register_ct_to_mri
from src.segmentation import segment_electrodes, correct_brain_shift
from src.labeling import (
    normalize_to_mni,
    lookup_brodmann_surface,
    lookup_aseg,
    compute_euclidean_error,
    export_report,
)
from src.visualization import plot_electrodes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="3D Intracranial Electrode Localization Pipeline (CT + MRI Fusion)"
    )
    parser.add_argument("--mri", required=True, help="Pre-operative MRI (.nii/.nii.gz)")
    parser.add_argument("--ct",  required=False, default=None,
                        help="Post-operative CT (.nii/.nii.gz). Optional when "
                             "--use-ground-truth is given — the GT positions "
                             "replace CT segmentation entirely.")
    parser.add_argument("--output-dir", default="outputs", help="Output directory")
    parser.add_argument("--format", choices=["csv", "xlsx"], default="csv",
                        help="Report file format")
    parser.add_argument("--plot", action="store_true",
                        help="Save a 3D render to outputs/figures/")
    parser.add_argument("--validate", default=None,
                        help="Path to ground-truth JSON/TSV for error validation "
                             "(comparison only — does not affect the electrode list)")
    parser.add_argument("--use-ground-truth", default=None,
                        help="Path to a BIDS *_electrodes.tsv (or compatible JSON) "
                             "to use as the SOURCE of electrode positions. When set, "
                             "CT segmentation is skipped entirely and every output "
                             "(coords, BA, ASEG, viewer) is computed at the GT "
                             "positions with their clinical names. Recommended for "
                             "any dataset that ships a verified GT.")
    parser.add_argument("--subject-dir", default=None,
                        help="FreeSurfer subject directory (contains surf/, mri/). "
                             "Required for pial surface loading and MNI normalization.")
    parser.add_argument("--export-viewer", action="store_true",
                        help="Export pipeline outputs to outputs/viewer/data.json "
                             "so the browser viewer (viewer/index.html) can render them.")
    return parser.parse_args()


def _parse_talairach_xfm(xfm_path: Path) -> np.ndarray:
    """Parse a FreeSurfer talairach.xfm into a 4x4 affine (tkRAS → MNI)."""
    lines = Path(xfm_path).read_text().splitlines()
    rows = []
    capture = False
    for line in lines:
        if "Linear_Transform" in line:
            capture = True
            continue
        if capture:
            rows.append(list(map(float, line.strip().rstrip(";").split())))
            if len(rows) == 3:
                break
    M = np.eye(4)
    M[:3, :] = rows
    return M


def _detect_tsv_units(tsv_path: Path) -> str:
    """Find out whether a BIDS *_electrodes.tsv is in metres or millimetres.

    Order of resolution:
      1. The companion `<base>_coordsystem.json` next to the TSV (BIDS spec
         field `iEEGCoordinateUnits`).
      2. Heuristic on the first row: if |x|, |y|, |z| are all < 1, assume
         metres (BIDS default); otherwise millimetres.
    """
    import csv as _csv

    # 1) Companion JSON
    base = tsv_path.name.replace("_electrodes.tsv", "")
    cs_path = tsv_path.parent / f"{base}_coordsystem.json"
    if cs_path.is_file():
        try:
            with open(cs_path) as f:
                cs = json.load(f)
            units = cs.get("iEEGCoordinateUnits")
            if units in ("m", "mm"):
                return units
        except Exception:
            pass

    # 2) Heuristic on first row
    with open(tsv_path) as f:
        reader = _csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                v = max(abs(float(row["x"])),
                        abs(float(row["y"])),
                        abs(float(row["z"])))
            except (KeyError, ValueError):
                break
            return "m" if v < 1.0 else "mm"
    return "mm"


def load_ground_truth(path: str, units: str | None = None) -> list[dict]:
    """Load ground-truth electrode positions from a JSON or BIDS TSV file.

    JSON format:
        [{"id": 1, "gt_mm": [x, y, z]}, ...]

    BIDS TSV format (e.g. sub-12_space-ScanRAS_electrodes.tsv):
        Tab-separated with columns: name, x, y, z  (plus optional extras).
        Units are auto-detected from the companion `*_coordsystem.json`
        (`iEEGCoordinateUnits` field) or, failing that, via the magnitude of
        the first row. Pass `units` explicitly to override.

    Returns entries with `gt_mm` always in millimetres, in the file's
    declared coordinate space (typically T1w ScanRAS or ACPC — the caller is
    responsible for using the right space).
    """
    import csv
    p = Path(path)
    if p.suffix == ".tsv":
        if units is None:
            units = _detect_tsv_units(p)
        scale = 1000.0 if units == "m" else 1.0
        entries = []
        with open(p) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for i, row in enumerate(reader, start=1):
                entries.append({
                    "id": row.get("name", str(i)),
                    "gt_mm": np.array([float(row["x"]),
                                       float(row["y"]),
                                       float(row["z"])]) * scale,
                })
        print(f"Loaded {len(entries)} ground-truth electrodes from {p.name} "
              f"(units detected: {units})")
        return entries
    # default: JSON (always assumed in mm)
    with open(p) as f:
        data = json.load(f)
    for entry in data:
        entry["gt_mm"] = np.array(entry["gt_mm"])
    print(f"Loaded {len(data)} ground-truth electrodes from {p.name}")
    return data


def run_pipeline(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    figures_dir = out_dir / "figures"
    reports_dir = out_dir / "reports"
    figures_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    use_gt = bool(args.use_ground_truth)

    # ── Phase 1: Data Preparation ─────────────────────────────────────────────
    print("\n=== Phase 1: Data Preparation ===")
    mri_img = load_nifti(args.mri)
    mri_img = reorient_to_ras(mri_img)

    if use_gt:
        print(f"Ground-truth mode: skipping CT phase, using {args.use_ground_truth}")
    else:
        if not args.ct:
            print("[ERROR] --ct is required when --use-ground-truth is not given.")
            sys.exit(1)
        ct_img = load_nifti(args.ct)
        ct_img = reorient_to_ras(ct_img)
        mri_masked = apply_brain_mask(mri_img)
        save_nifti(mri_masked, out_dir / "processed" / "mri_masked.nii.gz")

    # ── Phase 2: Fusion Engine (or GT load) ───────────────────────────────────
    if use_gt:
        print("\n=== Phase 2: Ground-truth electrodes ===")
        # GT is in the MRI (T1w) scanner RAS — exactly the frame the rest of
        # the pipeline expects after CT→MRI registration. We pour them into the
        # same electrode dict shape as the segmentation produces.
        gt_entries = load_ground_truth(args.use_ground_truth)
        electrodes = [
            {
                "id":           str(e["id"]),
                "centroid_mm":  np.asarray(e["gt_mm"], dtype=float),
                "centroid_vox": None,
                "n_voxels":     None,
                "elongation":   None,
                "source":       "ground-truth",
            }
            for e in gt_entries
        ]
    else:
        print("\n=== Phase 2: Fusion Engine ===")
        # Use the original (non-masked) MRI for registration — brain masking
        # zeros out valid tissue outside the brain and confuses Mutual Information.
        transformed_ct, ct_to_mri_matrix = register_ct_to_mri(mri_img, ct_img)
        save_nifti(transformed_ct, out_dir / "processed" / "ct_registered.nii.gz")

        # Segment on the ORIGINAL CT — resampling destroys HU values via interpolation,
        # dropping metal contacts from 3000+ HU to blurred averages. Detected centroids
        # (in CT world space) are then moved into MRI space via the registration transform.
        electrodes = segment_electrodes(ct_img)
        from src.registration import apply_affine_to_points
        ct_centroids = np.array([e["centroid_mm"] for e in electrodes])
        mri_centroids = apply_affine_to_points(ct_centroids, ct_to_mri_matrix)
        for e, mri_c in zip(electrodes, mri_centroids):
            e["centroid_mm"] = mri_c
            e["source"] = "ct-segmentation"

    if not electrodes:
        print("[ERROR] No electrodes available. "
              f"{'GT file empty?' if use_gt else 'Check HU threshold or CT quality.'}")
        sys.exit(1)

    # Pial surface: combine left + right hemispheres from FreeSurfer output
    import mne
    import nibabel as _nib
    if not args.subject_dir:
        print("[ERROR] --subject-dir is required. Point it to the FreeSurfer subject folder.")
        sys.exit(1)
    subj_dir = Path(args.subject_dir)
    lh_verts, lh_faces = mne.read_surface(str(subj_dir / "surf" / "lh.pial"))
    rh_verts, rh_faces = mne.read_surface(str(subj_dir / "surf" / "rh.pial"))
    rh_faces_offset = rh_faces + len(lh_verts)
    pial_vertices = np.vstack([lh_verts, rh_verts])
    pial_faces    = np.vstack([lh_faces, rh_faces_offset])
    print(f"Pial surface loaded: {len(pial_vertices)} vertices")

    # Electrode centroids are in scanner RAS (NIfTI affine space).
    # Pial surface vertices are in FreeSurfer tkRAS. Convert before snapping.
    t1_mgz = _nib.load(str(subj_dir / "mri" / "T1.mgz"))
    scanner_to_tkr = t1_mgz.header.get_vox2ras_tkr() @ np.linalg.inv(t1_mgz.header.get_vox2ras())
    for e in electrodes:
        e["centroid_scanner_mm"] = e["centroid_mm"].copy()   # keep scanner RAS for validation
        c = np.append(e["centroid_mm"], 1.0)
        e["centroid_mm"] = (scanner_to_tkr @ c)[:3]

    if use_gt:
        # GT positions are verified — no surface snap. Initialise the keys the
        # downstream stages expect (corrected_mm = centroid_mm, shift = 0).
        for e in electrodes:
            e["corrected_mm"] = e["centroid_mm"].copy()
            e["shift_mm"]     = 0.0
    else:
        electrodes = correct_brain_shift(electrodes, pial_vertices)

    # ── Phase 3: Labeling & Atlas ─────────────────────────────────────────────
    print("\n=== Phase 3: Anatomical Labeling ===")
    # MNI normalization via FreeSurfer talairach.xfm (tkRAS → MNI Talairach)
    patient_to_mni = _parse_talairach_xfm(subj_dir / "mri" / "transforms" / "talairach.xfm")
    electrodes = normalize_to_mni(electrodes, patient_to_mni)

    electrodes = lookup_brodmann_surface(
        electrodes,
        pial_vertices,
        lh_annot_path=str(subj_dir / "label" / "lh.BA_exvivo.annot"),
        rh_annot_path=str(subj_dir / "label" / "rh.BA_exvivo.annot"),
        n_lh_vertices=len(lh_verts),
    )

    # Volumetric labeling (Desikan-Killiany + subcortical) — fills in every
    # electrode, including deep / non-cortical contacts that BA_exvivo misses.
    aseg_path = subj_dir / "mri" / "aparc+aseg.mgz"
    if aseg_path.exists():
        electrodes = lookup_aseg(electrodes, str(aseg_path))
        n_labeled = sum(1 for e in electrodes if e.get("aseg_code", 0) != 0)
        print(f"ASEG labels assigned: {n_labeled}/{len(electrodes)} electrodes")
    else:
        print(f"[WARNING] aparc+aseg.mgz not found at {aseg_path} — "
              "skipping volumetric labeling.")

    for e in electrodes:
        # `id` can be either a sequential int (CT-segmentation) or a clinical
        # name string (ground-truth) — format accordingly.
        eid = str(e['id'])
        print(f"  Electrode {eid:>6s} | "
              f"({e['corrected_mm'][0]:.1f}, {e['corrected_mm'][1]:.1f}, {e['corrected_mm'][2]:.1f}) mm | "
              f"BA {e['brodmann_area']} – {e['anatomy_label']}")

    # ── Validation (optional) ─────────────────────────────────────────────────
    if args.validate:
        print("\n=== Validation ===")
        ground_truth = load_ground_truth(args.validate)
        # Compare in scanner RAS (same space as the GT file).
        # corrected_mm is in tkRAS (post surface-snap) — not appropriate for depth electrodes.
        compute_euclidean_error(electrodes, ground_truth, pred_key="centroid_scanner_mm")

    # ── Phase 4: Outputs ──────────────────────────────────────────────────────
    print("\n=== Phase 4: Outputs ===")
    report_path = str(reports_dir / f"electrode_report.{args.format}")
    export_report(electrodes, report_path)

    if args.plot:
        render_path = str(figures_dir / "electrodes_3d.png")
        plot_electrodes(pial_vertices, electrodes, pial_faces,
                        output_path=render_path)

    if args.export_viewer:
        from scripts.export_for_viewer import export_viewer_data
        viewer_dir = out_dir / "viewer"
        export_viewer_data(
            electrodes=electrodes,
            lh_verts=lh_verts, lh_faces=lh_faces,
            rh_verts=rh_verts, rh_faces=rh_faces,
            lh_annot_path=str(subj_dir / "label" / "lh.BA_exvivo.annot"),
            rh_annot_path=str(subj_dir / "label" / "rh.BA_exvivo.annot"),
            output_path=viewer_dir / "data.json",
            patient_id=subj_dir.name,
        )

    print("\nPipeline complete.")


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(args)
