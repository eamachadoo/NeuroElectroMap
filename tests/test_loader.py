"""Tests for Phase 1: loader.py"""

import numpy as np
import nibabel as nib
import pytest
from src.loader import get_affine, describe_orientation, reorient_to_ras


def _make_nifti(affine: np.ndarray, shape=(16, 16, 16)) -> nib.Nifti1Image:
    data = np.random.rand(*shape).astype(np.float32)
    return nib.Nifti1Image(data, affine)


def test_get_affine_returns_4x4():
    img = _make_nifti(np.eye(4))
    affine = get_affine(img)
    assert affine.shape == (4, 4)


def test_describe_orientation_ras():
    # Standard RAS affine
    img = _make_nifti(np.diag([1, 1, 1, 1]))
    orientation = describe_orientation(img)
    assert orientation == "RAS"


def test_reorient_to_ras_is_idempotent():
    img = _make_nifti(np.eye(4))
    reoriented = reorient_to_ras(img)
    assert reoriented.shape == img.shape
