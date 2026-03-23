"""Tests for Phase 2: segmentation.py"""

import numpy as np
import nibabel as nib
import pytest
from src.segmentation import segment_electrodes, correct_brain_shift


def _ct_with_blob(hu_value: float = 4000.0, shape=(32, 32, 32)) -> nib.Nifti1Image:
    """Synthetic CT: single high-HU blob at the center."""
    data = np.zeros(shape, dtype=np.float32)
    c = shape[0] // 2
    data[c-1:c+2, c-1:c+2, c-1:c+2] = hu_value   # 3x3x3 = 27 voxels
    return nib.Nifti1Image(data, np.eye(4))


def test_segment_electrodes_detects_blob():
    ct = _ct_with_blob(hu_value=4000.0)
    electrodes = segment_electrodes(ct, hu_threshold=3000.0, min_voxels=3, max_voxels=500)
    assert len(electrodes) == 1


def test_segment_electrodes_below_threshold():
    ct = _ct_with_blob(hu_value=1000.0)   # below threshold
    electrodes = segment_electrodes(ct, hu_threshold=3000.0)
    assert len(electrodes) == 0


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
