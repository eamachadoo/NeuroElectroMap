"""Phase 2 – Task 2.1: Rigid Registration (Weeks 3-5)

Align CT to MRI space using Mutual Information-based optimization (dipy).
Produces a 4x4 affine transform matrix: CT_vox → MRI_world.
"""

import numpy as np
import nibabel as nib
from dipy.align.imaffine import (
    AffineMap,
    AffineRegistration,
    MutualInformationMetric,
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

    Returns:
        transformed_ct: CT image resampled into MRI space.
        transform_matrix: 4x4 affine (CT world → MRI world).
    """
    mri_data = mri_img.get_fdata().astype(np.float64)
    ct_data = ct_img.get_fdata().astype(np.float64)

    mri_affine = mri_img.affine
    ct_affine = ct_img.affine

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
    mapping = affreg.optimize(
        static=mri_data,
        moving=ct_data,
        transform=transform,
        params0=None,
        static_grid2world=mri_affine,
        moving_grid2world=ct_affine,
    )

    transformed_ct_data = mapping.transform(ct_data)
    transformed_ct = nib.Nifti1Image(transformed_ct_data, mri_affine)

    # Ptarget = M_affine · Psource
    transform_matrix = mapping.affine
    print(f"Registration complete. Transform matrix:\n{transform_matrix}")

    return transformed_ct, transform_matrix


def apply_affine_to_points(points_vox: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """
    Apply a 4x4 affine to N points using homogeneous coordinates.

    Args:
        points_vox: (N, 3) array of source coordinates.
        affine:     (4, 4) transform matrix.

    Returns:
        (N, 3) array in target coordinates.
    """
    ones = np.ones((points_vox.shape[0], 1))
    homogeneous = np.hstack([points_vox, ones])   # (N, 4)
    world = (affine @ homogeneous.T).T            # (N, 4)
    return world[:, :3]
