"""Tests for Phase 2: segmentation.py"""

import numpy as np
import nibabel as nib
import pytest
from src.segmentation import segment_electrodes, correct_brain_shift, _region_elongation


def _ct_with_blob(hu_value: float = 4000.0, shape=(32, 32, 32)) -> nib.Nifti1Image:
    """Synthetic CT: single high-HU blob at the center."""
    data = np.zeros(shape, dtype=np.float32)
    c = shape[0] // 2
    data[c-1:c+2, c-1:c+2, c-1:c+2] = hu_value   # 3x3x3 = 27 voxels
    return nib.Nifti1Image(data, np.eye(4))


def _ct_with_rod(hu_value: float = 4000.0, length: int = 20,
                 cross_section: int = 2, shape=(32, 32, 32)) -> nib.Nifti1Image:
    """Synthetic CT: thin elongated bright object — mimics a cable.

    `cross_section` is the side length of the square cross-section. The
    default (2) gives a 2×2×length rod, which has a finite inertia ratio
    (long axis = 0 width, short axes = length²/12) so it's a realistic
    cable shape rather than a degenerate single-voxel line.
    """
    data = np.zeros(shape, dtype=np.float32)
    c = shape[0] // 2
    start = c - length // 2
    half_cs = cross_section // 2
    data[start:start + length,
         c - half_cs:c - half_cs + cross_section,
         c - half_cs:c - half_cs + cross_section] = hu_value
    return nib.Nifti1Image(data, np.eye(4))


def test_segment_electrodes_detects_blob():
    ct = _ct_with_blob(hu_value=4000.0)
    electrodes = segment_electrodes(ct, hu_threshold=3000.0, min_voxels=3, max_voxels=500)
    assert len(electrodes) == 1


def test_segment_electrodes_below_threshold():
    ct = _ct_with_blob(hu_value=1000.0)   # below threshold
    electrodes = segment_electrodes(ct, hu_threshold=3000.0)
    assert len(electrodes) == 0


def test_segment_electrodes_rejects_elongated_cable():
    """A long thin rod (cable-like) must be filtered out by the shape check."""
    ct = _ct_with_rod(hu_value=4000.0, length=20)
    electrodes = segment_electrodes(
        ct, hu_threshold=3000.0,
        min_voxels=3, max_voxels=500,
        max_elongation=5.0,
    )
    assert electrodes == [], "20-voxel rod should be rejected by the shape filter"


def test_segment_electrodes_keeps_elongated_when_filter_disabled():
    """High `max_elongation` lets the rod through — used for debug runs."""
    ct = _ct_with_rod(hu_value=4000.0, length=20)
    electrodes = segment_electrodes(
        ct, hu_threshold=3000.0,
        min_voxels=3, max_voxels=500,
        max_elongation=1000.0,
    )
    assert len(electrodes) == 1


def test_segment_electrodes_blob_passes_shape_filter():
    """A roughly spherical blob must be kept by the default shape filter."""
    ct = _ct_with_blob(hu_value=4000.0)
    electrodes = segment_electrodes(ct, hu_threshold=3000.0)
    assert len(electrodes) == 1
    # 3x3x3 cube has near-isotropic eigenvalues → low elongation
    assert electrodes[0]["elongation"] < 2.0


def test_region_elongation_handles_degenerate_eigvals():
    """A region whose smallest eigenvalue is 0 (single voxel slab) should
    report +∞ rather than crash on division by zero."""
    class _Fake:
        inertia_tensor_eigvals = (1.0, 0.5, 0.0)
    assert _region_elongation(_Fake()) == float("inf")


def test_correct_brain_shift_reduces_distance():
    electrodes = [{"id": 1, "centroid_mm": np.array([5.0, 5.0, 5.0])}]
    # Pial surface vertex sitting at the centroid — shift should be zero
    pial_vertices = np.array([[5.0, 5.0, 5.0], [10.0, 10.0, 10.0]])
    result = correct_brain_shift(electrodes, pial_vertices)
    assert result[0]["shift_mm"] == pytest.approx(0.0)


def test_correct_brain_shift_output_keys():
    electrodes = [{"id": 1, "centroid_mm": np.array([0.0, 0.0, 0.0])}]
    pial_vertices = np.array([[1.0, 0.0, 0.0]])
    result = correct_brain_shift(electrodes, pial_vertices)
    assert "corrected_mm" in result[0]
    assert "shift_mm" in result[0]
