"""Tests for Phase 3: labeling.py"""

import numpy as np
import pytest
from src.labeling import normalize_to_mni, compute_euclidean_error, export_report
import tempfile, os


def _make_electrodes(n: int = 3) -> list[dict]:
    return [
        {
            "id": i + 1,
            "corrected_mm": np.array([float(i), float(i), float(i)]),
            "brodmann_area": 4,
            "anatomy_label": "Primary Motor Cortex (M1)",
            "shift_mm": 0.5,
        }
        for i in range(n)
    ]


def test_normalize_to_mni_identity():
    electrodes = _make_electrodes(2)
    result = normalize_to_mni(electrodes, np.eye(4), coord_key="corrected_mm")
    for orig, norm in zip(electrodes, result):
        np.testing.assert_allclose(norm["mni_mm"], orig["corrected_mm"])


def test_compute_euclidean_error_zero():
    electrodes = _make_electrodes(3)
    ground_truth = [{"id": e["id"], "gt_mm": e["corrected_mm"].copy()} for e in electrodes]
    stats = compute_euclidean_error(electrodes, ground_truth)
    assert stats["mean_error_mm"] == pytest.approx(0.0)


def test_export_report_csv():
    electrodes = _make_electrodes(2)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        path = f.name
    try:
        df = export_report(electrodes, path)
        assert len(df) == 2
        assert "Electrode_ID" in df.columns
        assert "Brodmann_Area" in df.columns
    finally:
        os.unlink(path)
