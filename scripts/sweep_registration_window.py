"""Diagnostic: sweep CT clip window for CT→MRI registration and measure
alignment quality against the ds004473 sub-12 ground-truth electrodes.

Metric (purely registration, independent of segmentation/matching):
  For every GT contact, find the nearest CT voxel above 3000 HU after
  applying the registration. Report mean & median distance in mm —
  this is the rigid-registration residual error as seen by the electrodes.

Usage: python -m scripts.sweep_registration_window
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import numpy as np
import nibabel as nib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import certifi  # noqa: E402

os.environ.setdefault("SSL_CERT_FILE",    certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

from src.loader        import load_nifti, reorient_to_ras  # noqa: E402
from src.registration  import register_ct_to_mri           # noqa: E402

MRI = ROOT / "data/raw/ds004473/sub-12/anat/sub-12_T1w.nii.gz"
CT  = ROOT / "data/raw/ds004473/sub-12/anat/sub-12_ct.nii.gz"
GT  = ROOT / "data/raw/ds004473/sub-12/ieeg/sub-12_space-ScanRAS_electrodes.tsv"

WINDOWS: list[tuple[float, float]] = [
    (-100.0,  200.0),   # baseline (current default)
    (-100.0, 1500.0),   # soft-tissue + bone
    ( 100.0, 1500.0),   # bone only
    (-1024.0, 3071.0),  # full HU range, no clip
]


def load_gt_mm(path: Path) -> tuple[list[str], np.ndarray]:
    names, coords = [], []
    with open(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            names.append(row["name"])
            coords.append([float(row["x"]), float(row["y"]), float(row["z"])])
    coords_m = np.array(coords)
    # detect units (heuristic: |coord| < 1 means metres → mm)
    scale = 1000.0 if np.max(np.abs(coords_m)) < 1.0 else 1.0
    return names, coords_m * scale


def bright_voxel_mm(ct_reg_img: nib.Nifti1Image, hu_thresh: float = 3000.0) -> np.ndarray:
    data = ct_reg_img.get_fdata()
    vox = np.argwhere(data > hu_thresh)
    if len(vox) == 0:
        return np.empty((0, 3))
    homo = np.column_stack([vox, np.ones(len(vox))])
    return (ct_reg_img.affine @ homo.T).T[:, :3]


def nearest_distances(gt_mm: np.ndarray, points_mm: np.ndarray) -> np.ndarray:
    """For each GT point, return the distance to its nearest point in `points_mm`."""
    if len(points_mm) == 0:
        return np.full(len(gt_mm), np.inf)
    # Chunked to avoid materialising a 119 × N matrix when N is huge.
    out = np.empty(len(gt_mm))
    chunk = 4096
    for start in range(0, len(points_mm), chunk):
        sub = points_mm[start:start + chunk]
        d = np.linalg.norm(gt_mm[:, None, :] - sub[None, :, :], axis=2).min(axis=1)
        if start == 0:
            out[:] = d
        else:
            out[:] = np.minimum(out, d)
    return out


def main() -> None:
    print("Loading inputs once...")
    mri_img = reorient_to_ras(load_nifti(str(MRI)))
    ct_img  = reorient_to_ras(load_nifti(str(CT)))
    names, gt_mm = load_gt_mm(GT)
    print(f"  T1w shape={mri_img.shape}, CT shape={ct_img.shape}, GT contacts={len(names)}")

    # Build per-shaft index for hemisphere split (L/R).
    is_right = np.array([n[0].upper() == "R" for n in names])
    print(f"  Hemisphere split: L={int(np.sum(~is_right))} R={int(np.sum(is_right))}")

    header = f"\n{'Window':>18}  {'mean':>7}  {'median':>7}  {'p90':>7}  " \
             f"{'mean_L':>7}  {'mean_R':>7}  {'≤5mm':>5}  {'≤10mm':>5}"
    print(header)
    print("─" * len(header))

    for window in WINDOWS:
        print(f"\n>>> Registering with CT clip {window} ...")
        ct_reg_img, _ = register_ct_to_mri(mri_img, ct_img, ct_clip=window)
        bright_mm = bright_voxel_mm(ct_reg_img, hu_thresh=3000.0)
        if len(bright_mm) == 0:
            print(f"  No bright voxels >3000HU in registered CT (window={window})")
            continue
        d = nearest_distances(gt_mm, bright_mm)
        d_L, d_R = d[~is_right], d[is_right]
        print(
            f"{str(window):>18}  "
            f"{d.mean():>7.2f}  {np.median(d):>7.2f}  {np.percentile(d, 90):>7.2f}  "
            f"{d_L.mean():>7.2f}  {d_R.mean():>7.2f}  "
            f"{int(np.sum(d <= 5)):>5}  {int(np.sum(d <= 10)):>5}"
        )


if __name__ == "__main__":
    main()
