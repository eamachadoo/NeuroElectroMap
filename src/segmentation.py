"""Phase 2 – Tasks 2.2 & 2.3: Electrode Segmentation & Brain-Shift Correction

Task 2.2: Isolate electrodes from CT via HU thresholding + 3D Connected Component Analysis.
Task 2.3: Project CT centroids onto the nearest pial surface vertex (brain-shift correction).
"""

import numpy as np
import nibabel as nib
from scipy import ndimage
from skimage.measure import label, regionprops


# ──────────────────────────────────────────────────────────────────────────────
# Task 2.2 – Electrode Segmentation
# ──────────────────────────────────────────────────────────────────────────────

def segment_electrodes(
    ct_img: nib.Nifti1Image,
    hu_threshold: float = 3000.0,
    min_voxels: int = 3,
    max_voxels: int = 500,
) -> list[dict]:
    """
    Detect electrode centroids from a CT image using:
      1. Global HU threshold (metallic implants > 3000 HU).
      2. 3D Connected Component Analysis to isolate individual contacts.

    Returns:
        List of dicts: {id, centroid_vox, centroid_mm, n_voxels}
    """
    ct_data = ct_img.get_fdata()
    affine = ct_img.affine

    binary_mask = ct_data > hu_threshold
    print(f"Voxels above {hu_threshold} HU: {binary_mask.sum()}")

    labeled_array, num_features = ndimage.label(binary_mask)
    print(f"Connected components found: {num_features}")

    regions = regionprops(labeled_array)
    electrodes = []

    for region in regions:
        n_vox = region.area
        if not (min_voxels <= n_vox <= max_voxels):
            continue  # Filter noise and large metal artifacts

        centroid_vox = np.array(region.centroid)

        # Ptarget = M_affine · Psource  (voxel → world mm)
        centroid_hom = np.append(centroid_vox, 1.0)
        centroid_mm = (affine @ centroid_hom)[:3]

        electrodes.append({
            "id": len(electrodes) + 1,
            "centroid_vox": centroid_vox,
            "centroid_mm": centroid_mm,
            "n_voxels": n_vox,
        })

    print(f"Electrodes detected after size filter: {len(electrodes)}")
    return electrodes


# ──────────────────────────────────────────────────────────────────────────────
# Task 2.3 – Brain-Shift Correction
# ──────────────────────────────────────────────────────────────────────────────

def correct_brain_shift(
    electrodes: list[dict],
    pial_vertices: np.ndarray,
    max_shift_mm: float = 10.0,
) -> list[dict]:
    """
    Project each electrode centroid to the nearest vertex on the pial surface.

    Args:
        electrodes:    List of electrode dicts (must contain 'centroid_mm').
        pial_vertices: (V, 3) array of pial surface vertices in the same world space.
        max_shift_mm:  Warn if the correction exceeds this distance.

    Returns:
        Updated electrode list with added 'corrected_mm' and 'shift_mm' keys.
    """
    corrected = []
    for elec in electrodes:
        c = elec["centroid_mm"]
        dists = np.linalg.norm(pial_vertices - c, axis=1)
        nearest_idx = np.argmin(dists)
        nearest_vertex = pial_vertices[nearest_idx]
        shift = float(dists[nearest_idx])

        if shift > max_shift_mm:
            print(f"[WARNING] Electrode {elec['id']}: large brain-shift correction {shift:.2f} mm")

        corrected.append({
            **elec,
            "corrected_mm": nearest_vertex,
            "shift_mm": shift,
        })

    return corrected
