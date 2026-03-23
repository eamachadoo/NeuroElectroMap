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
    load_brodmann_atlas,
    lookup_brodmann,
    compute_euclidean_error,
    export_report,
)
from src.visualization import plot_electrodes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="3D Intracranial Electrode Localization Pipeline (CT + MRI Fusion)"
    )
    parser.add_argument("--mri", required=True, help="Pre-operative MRI (.nii/.nii.gz)")
    parser.add_argument("--ct",  required=True, help="Post-operative CT  (.nii/.nii.gz)")
    parser.add_argument("--output-dir", default="outputs", help="Output directory")
    parser.add_argument("--format", choices=["csv", "xlsx"], default="csv",
                        help="Report file format")
    parser.add_argument("--plot", action="store_true",
                        help="Save a 3D render to outputs/figures/")
    parser.add_argument("--validate", default=None,
                        help="Path to ground-truth JSON for error validation")
    return parser.parse_args()


def load_ground_truth(path: str) -> list[dict]:
    """Load ground-truth electrode positions from a JSON file.

    Expected format:
        [{"id": 1, "gt_mm": [x, y, z]}, ...]
    """
    with open(path) as f:
        data = json.load(f)
    for entry in data:
        entry["gt_mm"] = np.array(entry["gt_mm"])
    return data


def run_pipeline(args: argparse.Namespace) -> None:
    out_dir = Path(args.output_dir)
    figures_dir = out_dir / "figures"
    reports_dir = out_dir / "reports"
    figures_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Data Preparation ─────────────────────────────────────────────
    print("\n=== Phase 1: Data Preparation ===")
    mri_img = load_nifti(args.mri)
    ct_img  = load_nifti(args.ct)

    mri_img = reorient_to_ras(mri_img)
    ct_img  = reorient_to_ras(ct_img)

    mri_masked = apply_brain_mask(mri_img)
    save_nifti(mri_masked, out_dir / "processed" / "mri_masked.nii.gz")

    # ── Phase 2: Fusion Engine ────────────────────────────────────────────────
    print("\n=== Phase 2: Fusion Engine ===")
    transformed_ct, ct_to_mri_matrix = register_ct_to_mri(mri_masked, ct_img)
    save_nifti(transformed_ct, out_dir / "processed" / "ct_registered.nii.gz")

    electrodes = segment_electrodes(transformed_ct)

    if not electrodes:
        print("[ERROR] No electrodes detected. Check HU threshold or CT quality.")
        sys.exit(1)

    # Pial surface: placeholder — replace with actual surface extraction via MNE/FreeSurfer
    # e.g., mne.read_surface('lh.pial') returns (vertices, faces)
    pial_vertices = np.zeros((1, 3))  # TODO: load real pial surface
    pial_faces    = None

    electrodes = correct_brain_shift(electrodes, pial_vertices)

    # ── Phase 3: Labeling & Atlas ─────────────────────────────────────────────
    print("\n=== Phase 3: Anatomical Labeling ===")
    # MNI normalization: identity placeholder — replace with ANTs/dipy nonlinear warp
    patient_to_mni = np.eye(4)  # TODO: compute actual MNI warp
    electrodes = normalize_to_mni(electrodes, patient_to_mni)

    atlas_img  = load_brodmann_atlas()
    electrodes = lookup_brodmann(electrodes, atlas_img)

    for e in electrodes:
        print(f"  Electrode {e['id']:>2d} | "
              f"({e['corrected_mm'][0]:.1f}, {e['corrected_mm'][1]:.1f}, {e['corrected_mm'][2]:.1f}) mm | "
              f"BA {e['brodmann_area']} – {e['anatomy_label']}")

    # ── Validation (optional) ─────────────────────────────────────────────────
    if args.validate:
        print("\n=== Validation ===")
        ground_truth = load_ground_truth(args.validate)
        compute_euclidean_error(electrodes, ground_truth)

    # ── Phase 4: Outputs ──────────────────────────────────────────────────────
    print("\n=== Phase 4: Outputs ===")
    report_path = str(reports_dir / f"electrode_report.{args.format}")
    export_report(electrodes, report_path)

    if args.plot:
        render_path = str(figures_dir / "electrodes_3d.png")
        plot_electrodes(pial_vertices, electrodes, pial_faces,
                        output_path=render_path)

    print("\nPipeline complete.")


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(args)
