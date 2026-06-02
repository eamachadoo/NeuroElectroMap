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

def _region_elongation(region) -> float:
    """Approximate aspect ratio of a 3D connected component.

    Uses sqrt(λ_max / λ_min) of the inertia-tensor eigenvalues:
      • A perfect sphere has λ_max = λ_min ⇒ elongation = 1.0
      • A cable / rod has λ_max ≫ λ_min ⇒ elongation > 5
      • A flat disc-like artifact has one eigval ≪ others ⇒ also large

    Returns +∞ for degenerate components whose smallest eigenvalue is 0
    (single-voxel slabs etc.) so the caller can safely filter them out.
    """
    eigs = sorted(region.inertia_tensor_eigvals, reverse=True)
    if eigs[-1] <= 0:
        return float("inf")
    return float(np.sqrt(eigs[0] / eigs[-1]))


def segment_electrodes(
    ct_img: nib.Nifti1Image,
    hu_threshold: float = 3000.0,
    min_voxels: int = 3,
    max_voxels: int = 500,
    max_elongation: float = 5.0,
) -> list[dict]:
    """Detect electrode centroids from a CT image.

    Pipeline:
      1. Global HU threshold (metallic implants > 3000 HU).
      2. 3D Connected Component Analysis to isolate individual contacts.
      3. Size filter (`min_voxels` ≤ voxels ≤ `max_voxels`) drops noise
         (tiny salt-and-pepper artefacts) and very large blobs (skull
         hardware, scanner table mounts).
      4. **Shape filter** (`max_elongation`) drops thin elongated
         components — typically the cable/wire segments that run from the
         implanted contacts up through the scalp to the external connectors.
         These metal cables read just as bright as the contacts in CT and
         end up in the same size range as a real depth contact (~3-50 vox).
         Without this filter every patient ends up with a long tail of
         non-anatomical "electrodes" that mostly fall outside the brain
         in the viewer's "Unknown" pool.

    The default `max_elongation=5.0` was tuned against ds004473 sub-12:
    it removes the ~15 most obvious cable components while leaving all
    contacts that have a plausibly-spherical shape intact. Pass a larger
    value (e.g. 10) to disable the shape filter for a debug run.

    Returns:
        List of dicts: {id, centroid_vox, centroid_mm, n_voxels, elongation}
    """
    ct_data = ct_img.get_fdata()
    affine = ct_img.affine

    binary_mask = ct_data > hu_threshold
    print(f"Voxels above {hu_threshold} HU: {binary_mask.sum()}")

    labeled_array, num_features = ndimage.label(binary_mask)
    print(f"Connected components found: {num_features}")

    regions = regionprops(labeled_array)
    electrodes = []
    dropped_size  = 0
    dropped_shape = 0

    for region in regions:
        n_vox = region.area
        if not (min_voxels <= n_vox <= max_voxels):
            dropped_size += 1
            continue
        elongation = _region_elongation(region)
        if elongation > max_elongation:
            dropped_shape += 1
            continue

        centroid_vox = np.array(region.centroid)
        # Ptarget = M_affine · Psource  (voxel → world mm)
        centroid_hom = np.append(centroid_vox, 1.0)
        centroid_mm = (affine @ centroid_hom)[:3]

        electrodes.append({
            "id": len(electrodes) + 1,
            "centroid_vox": centroid_vox,
            "centroid_mm": centroid_mm,
            "n_voxels": n_vox,
            "elongation": elongation,
        })

    print(
        f"Electrodes detected: {len(electrodes)}  "
        f"(dropped {dropped_size} by size, {dropped_shape} by shape)"
    )
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
