"""Smoke tests for Phase 4 – Task 4.1: src/visualization.py

These tests use the matplotlib fallback path so no display or pyvista
installation is required in CI / headless environments.
"""

import os
import tempfile

import numpy as np
import pytest

from src.visualization import plot_3d_matplotlib, plot_electrodes


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_test_data():
    rng = np.random.default_rng(42)
    verts = rng.random((200, 3)) * 100.0
    faces = np.array([[0, 1, 2], [3, 4, 5]])
    electrodes = [
        {
            "id": 1,
            "corrected_mm": np.array([10.0, 20.0, 30.0]),
            "brodmann_area": 4,
            "anatomy_label": "Primary Motor Cortex (M1)",
        },
        {
            "id": 2,
            "corrected_mm": np.array([15.0, 25.0, 35.0]),
            "brodmann_area": 6,
            "anatomy_label": "Premotor & Supplementary Motor Cortex",
        },
    ]
    return verts, faces, electrodes


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_plot_3d_matplotlib_saves_png():
    """plot_3d_matplotlib must write a non-empty PNG file."""
    verts, _, electrodes = _make_test_data()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        plot_3d_matplotlib(verts, electrodes, output_path=path)
        assert os.path.exists(path), "Output PNG was not created"
        assert os.path.getsize(path) > 0, "Output PNG is empty"
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_plot_electrodes_no_faces_uses_matplotlib():
    """plot_electrodes with pial_faces=None falls back to matplotlib and saves a PNG."""
    verts, _, electrodes = _make_test_data()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        plot_electrodes(verts, electrodes, pial_faces=None, output_path=path)
        assert os.path.exists(path), "Output PNG was not created"
        assert os.path.getsize(path) > 0, "Output PNG is empty"
    finally:
        if os.path.exists(path):
            os.unlink(path)
