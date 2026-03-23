"""Phase 1: Data Preparation & Header Alignment (Weeks 1-2)

Task 1.1: NIfTI data loader
Task 1.2: Affine matrix extraction and orientation check
Task 1.3: Brain masking via nilearn
"""

import nibabel as nib
import numpy as np
from pathlib import Path
from nilearn import masking, image


def load_nifti(path: str | Path) -> nib.Nifti1Image:
    """Load a NIfTI file (.nii or .nii.gz) and return the image object."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"NIfTI file not found: {path}")
    img = nib.load(str(path))
    print(f"Loaded: {path.name} | Shape: {img.shape} | Voxel size: {img.header.get_zooms()}")
    return img


def get_affine(img: nib.Nifti1Image) -> np.ndarray:
    """Extract the 4x4 affine matrix (voxel → world RAS+ coordinates)."""
    return img.affine


def describe_orientation(img: nib.Nifti1Image) -> str:
    """Return the axis orientation string (e.g., 'RAS', 'LPS')."""
    codes = nib.orientations.aff2axcodes(img.affine)
    orientation = "".join(codes)
    print(f"Orientation: {orientation}")
    return orientation


def reorient_to_ras(img: nib.Nifti1Image) -> nib.Nifti1Image:
    """Reorient image to standard RAS+ orientation."""
    return nib.as_closest_canonical(img)


def apply_brain_mask(mri_img: nib.Nifti1Image) -> nib.Nifti1Image:
    """
    Task 1.3: Remove non-brain tissue (skull/neck) from MRI using nilearn.
    Returns a masked NIfTI image in the same space.
    """
    mask_img = masking.compute_brain_mask(mri_img)
    masked = image.math_img("img * mask", img=mri_img, mask=mask_img)
    print("Brain masking applied.")
    return masked


def save_nifti(img: nib.Nifti1Image, path: str | Path) -> None:
    """Save a NIfTI image to disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(img, str(path))
    print(f"Saved: {path}")
