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
    ct_clip: tuple[float, float] = (-100.0, 200.0),
    starting_affine: np.ndarray | None = None,
) -> tuple[nib.Nifti1Image, np.ndarray]:
    """
    Rigid-body registration of CT onto MRI using Mutual Information.

    Args:
        mri_img:  Pre-operative T1w MRI (full image — not brain-masked;
                  masking zeros out valid tissue and confuses MI).
        ct_img:   Post-operative CT (full HU range).
        ct_clip:  (lo, hi) HU window applied to the CT before MI. Defaults
                  to a soft-tissue window. Widen towards bone (e.g.
                  (-100, 1500)) if the residual rigid error is too large —
                  the skull outline is the most informative CT/MRI common
                  feature.

    Returns:
        transformed_ct:   CT resampled into MRI space (NIfTI, same grid).
        transform_matrix: 4x4 affine (CT world → MRI world).
    """
    mri_data   = mri_img.get_fdata().astype(np.float64)
    ct_data    = ct_img.get_fdata().astype(np.float64)
    mri_affine = mri_img.affine
    ct_affine  = ct_img.affine

    ct_reg = np.clip(ct_data, ct_clip[0], ct_clip[1])
    print(f"  CT clipped to HU window {ct_clip} for MI")

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

    # ── Step 1: Determine starting affine ─────────────────────────────────
    # By default we use a centres-of-mass pre-alignment (CT and MRI scanner
    # origins often differ by ~100 mm; starting from identity diverges).
    # Callers may inject a better-informed start (e.g. an electrode-cloud
    # landmark alignment) to escape MI local minima.
    if starting_affine is None:
        c_of_mass = transform_centers_of_mass(
            static=mri_data,
            static_grid2world=mri_affine,
            moving=ct_reg,
            moving_grid2world=ct_affine,
        )
        starting_affine = c_of_mass.affine
        print(f"  COM pre-alignment translation: {starting_affine[:3, 3].round(1)} mm")
    else:
        print(f"  Caller-supplied starting affine, translation: {starting_affine[:3, 3].round(1)} mm")

    # ── Step 2: Rigid MI registration from chosen starting point ──────────
    mapping = affreg.optimize(
        static=mri_data,
        moving=ct_reg,
        transform=transform,
        params0=None,
        static_grid2world=mri_affine,
        moving_grid2world=ct_affine,
        starting_affine=starting_affine,
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
