"""Diagnostic: compare MI registration started from
  (A) the image centre-of-mass (baseline behaviour), versus
  (B) an "oracle" landmark start built from the GT electrode centroid
      mapped to the CT bright-voxel centroid.

If (B) converges to <2mm mean error → MI is fundamentally working but
gets trapped in a local minimum from the COM start, and the fix is to
seed it better. If (B) still sits at ≈20mm → MI/rigid-dipy can't model
this CT/T1 pair and we need a different registration backend.

Both runs use the same CT clip window so the comparison is apples-to-apples.

Usage: python -m scripts.oracle_start_registration
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

# Use the window that gave the best baseline (bone-only).
CT_CLIP = (100.0, 1500.0)


def load_gt_mm(path: Path):
    names, coords = [], []
    with open(path) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            names.append(row["name"])
            coords.append([float(row["x"]), float(row["y"]), float(row["z"])])
    arr = np.array(coords)
    scale = 1000.0 if np.max(np.abs(arr)) < 1.0 else 1.0
    return names, arr * scale


def bright_voxels_world(img: nib.Nifti1Image, hu_thresh=3000.0) -> np.ndarray:
    data = img.get_fdata()
    vox = np.argwhere(data > hu_thresh)
    if len(vox) == 0:
        return np.empty((0, 3))
    homo = np.column_stack([vox, np.ones(len(vox))])
    return (img.affine @ homo.T).T[:, :3]


def nearest_distances(gt_mm, points_mm):
    if len(points_mm) == 0:
        return np.full(len(gt_mm), np.inf)
    out = np.full(len(gt_mm), np.inf)
    chunk = 4096
    for s in range(0, len(points_mm), chunk):
        sub = points_mm[s:s+chunk]
        d = np.linalg.norm(gt_mm[:, None, :] - sub[None, :, :], axis=2).min(axis=1)
        out = np.minimum(out, d)
    return out


def report(label: str, gt_mm: np.ndarray, ct_reg_img: nib.Nifti1Image,
           is_right: np.ndarray) -> None:
    bright_mm = bright_voxels_world(ct_reg_img)
    d = nearest_distances(gt_mm, bright_mm)
    d_L, d_R = d[~is_right], d[is_right]
    print(
        f"  {label:25s}  mean={d.mean():6.2f}  median={np.median(d):6.2f}  "
        f"p90={np.percentile(d, 90):6.2f}  L={d_L.mean():5.2f}  R={d_R.mean():5.2f}  "
        f"≤5mm={int(np.sum(d <= 5)):3d}  ≤10mm={int(np.sum(d <= 10)):3d}"
    )


def main() -> None:
    mri_img = reorient_to_ras(load_nifti(str(MRI)))
    ct_img  = reorient_to_ras(load_nifti(str(CT)))
    names, gt_mm = load_gt_mm(GT)
    is_right = np.array([n[0].upper() == "R" for n in names])

    # ── Compute oracle starting affine ────────────────────────────────────
    # Identity rotation; translation chosen so that the GT centroid maps to
    # the CT bright-voxel centroid in CT world space.
    bright_ct_mm = bright_voxels_world(ct_img)           # in CT native world
    gt_centroid     = gt_mm.mean(axis=0)
    bright_centroid = bright_ct_mm.mean(axis=0)
    # register_ct_to_mri expects starting_affine to map STATIC (MRI) world
    # → MOVING (CT) world, matching `mapping.affine` direction.
    oracle_start = np.eye(4)
    oracle_start[:3, 3] = bright_centroid - gt_centroid

    print("Oracle landmark summary:")
    print(f"  GT centroid (T1w world):       {gt_centroid.round(2)}")
    print(f"  Bright centroid (CT world):    {bright_centroid.round(2)}")
    print(f"  Translation (MRI→CT) for start: {oracle_start[:3, 3].round(2)}")
    print()

    print(f"Running BASELINE (COM start) with clip {CT_CLIP}...")
    ct_reg_base, _ = register_ct_to_mri(mri_img, ct_img, ct_clip=CT_CLIP)

    print(f"\nRunning ORACLE-START with clip {CT_CLIP}...")
    ct_reg_oracle, _ = register_ct_to_mri(
        mri_img, ct_img, ct_clip=CT_CLIP, starting_affine=oracle_start
    )

    print("\n── Results (lower is better) ──────────────────────────────────")
    report("BASELINE (COM start)",        gt_mm, ct_reg_base,   is_right)
    report("ORACLE start (GT centroid)",  gt_mm, ct_reg_oracle, is_right)


if __name__ == "__main__":
    main()
