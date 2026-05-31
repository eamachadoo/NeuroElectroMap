"""Phase 2 – Task 2.1: Rigid Registration (Weeks 3-5)

Align CT to MRI space using Mutual Information-based optimization (dipy).
Produces a 4x4 affine transform matrix: CT world → MRI world.

Registration pipeline
---------------------
1. Clip CT to soft-tissue window (-100 … 200 HU) so MI focuses on brain
   tissue rather than metal/bone artifacts.
2. Pre-align via centers of mass — critical when CT and MRI scanner
   origins differ by ~100 mm (typical for separate acquisition dates).
3. Rigid MI registration starting from the COM affine.
"""

import numpy as np
import nibabel as nib
from dipy.align.imaffine import (
    AffineMap,
    AffineRegistration,
    MutualInformationMetric,
    transform_centers_of_mass,
)
from dipy.align.transforms import RigidTransform3D


def register_ct_to_mri(
    mri_img: nib.Nifti1Image,
    ct_img: nib.Nifti1Image,
    nbins: int = 32,
    sampling_proportion: float = 0.3,
) -> tuple[nib.Nifti1Image, np.ndarray]:
    """
    Rigid-body registration of CT onto MRI using Mutual Information.

    Args:
        mri_img:  Pre-operative T1w MRI (full image — not brain-masked;
                  masking zeros out valid tissue and confuses MI).
        ct_img:   Post-operative CT (full HU range).

    Returns:
        transformed_ct:   CT resampled into MRI space (NIfTI, same grid).
        transform_matrix: 4x4 affine (CT world → MRI world).
    """
    mri_data   = mri_img.get_fdata().astype(np.float64)
    ct_data    = ct_img.get_fdata().astype(np.float64)
    mri_affine = mri_img.affine
    ct_affine  = ct_img.affine

    # Soft-tissue window for the registration step only.
    # Bone and metal (>200 HU) dominate the histogram and mislead MI;
    # electrode contacts will still be detected from the original ct_data.
    ct_reg = np.clip(ct_data, -100.0, 200.0)

    metric = MutualInformationMetric(nbins=nbins, sampling_proportion=sampling_proportion)

    affreg = AffineRegistration(
        metric=metric,
        level_iters=[10000, 1000, 100],
        sigmas=[3.0, 1.0, 0.0],
        factors=[4, 2, 1],
        verbosity=1,
    )

    transform = RigidTransform3D()

    print("Running rigid CT-to-MRI registration (Mutual Information)...")

    # ── Step 1: Centers-of-mass pre-alignment ──────────────────────────────
    # The CT and MRI scanner origins often differ by ~100 mm; starting from
    # identity with that offset makes the MI optimizer diverge.
    c_of_mass = transform_centers_of_mass(
        static=mri_data,
        static_grid2world=mri_affine,
        moving=ct_reg,
        moving_grid2world=ct_affine,
    )
    print(f"  COM pre-alignment translation: {c_of_mass.affine[:3, 3].round(1)} mm")

    # ── Step 2: Rigid MI registration from COM starting point ──────────────
    mapping = affreg.optimize(
        static=mri_data,
        moving=ct_reg,
        transform=transform,
        params0=None,
        static_grid2world=mri_affine,
        moving_grid2world=ct_affine,
        starting_affine=c_of_mass.affine,
    )

    # Resample full-range CT (not windowed) into MRI space for saving
    transformed_ct_data = mapping.transform(ct_data)
    transformed_ct = nib.Nifti1Image(transformed_ct_data, mri_affine)

    # mapping.affine  : static (MRI) world → moving (CT) world
    # mapping.affine_inv: CT world → MRI world  ← this is what we need
    transform_matrix = mapping.affine_inv
    print(f"Registration complete. Transform matrix:\n{transform_matrix}")

    return transformed_ct, transform_matrix


def apply_affine_to_points(points_vox: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """
    Apply a 4x4 affine to N points using homogeneous coordinates.

    Args:
        points_vox: (N, 3) array of source coordinates (world mm or voxel).
        affine:     (4, 4) transform matrix.

    Returns:
        (N, 3) array in target coordinates.
    """
    ones = np.ones((points_vox.shape[0], 1))
    homogeneous = np.hstack([points_vox, ones])   # (N, 4)
    world = (affine @ homogeneous.T).T            # (N, 4)
    return world[:, :3]
