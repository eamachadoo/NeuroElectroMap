"""Tests for Phase 2: registration.py"""

import numpy as np
import pytest
from src.registration import apply_affine_to_points


def test_apply_affine_identity():
    points = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    result = apply_affine_to_points(points, np.eye(4))
    np.testing.assert_allclose(result, points)


def test_apply_affine_translation():
    points = np.array([[0.0, 0.0, 0.0]])
    affine = np.eye(4)
    affine[:3, 3] = [10.0, 20.0, 30.0]   # pure translation
    result = apply_affine_to_points(points, affine)
    np.testing.assert_allclose(result, [[10.0, 20.0, 30.0]])


def test_apply_affine_output_shape():
    points = np.random.rand(50, 3)
    result = apply_affine_to_points(points, np.eye(4))
    assert result.shape == (50, 3)
