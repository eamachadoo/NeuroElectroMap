"""Tests for the ground-truth loader in main.py.

Covers:
  • BIDS *_electrodes.tsv parsing, including auto-detection of metres-vs-mm
    units (via the companion `*_coordsystem.json` and a magnitude heuristic).
  • JSON ground-truth (the older `[{"id", "gt_mm"}, ...]` shape).
  • The fallback behaviour when units cannot be inferred.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from main import _detect_tsv_units, load_ground_truth


# ──────────────────────────────────────────────────────────────────────────
# Helpers — build minimal BIDS-shaped fixtures in tmp_path
# ──────────────────────────────────────────────────────────────────────────

def _write_tsv(path: Path, rows: list[tuple[str, float, float, float]]) -> None:
    lines = ["name\tx\ty\tz"]
    for name, x, y, z in rows:
        lines.append(f"{name}\t{x}\t{y}\t{z}")
    path.write_text("\n".join(lines))


def _write_coordsystem(path: Path, units: str) -> None:
    path.write_text(json.dumps({
        "iEEGCoordinateSystem": "ScanRAS",
        "iEEGCoordinateUnits":  units,
    }))


# ──────────────────────────────────────────────────────────────────────────
# Unit detection
# ──────────────────────────────────────────────────────────────────────────

class TestDetectUnits:
    def test_explicit_meters_in_coordsystem_json(self, tmp_path):
        tsv = tmp_path / "sub-01_space-ScanRAS_electrodes.tsv"
        cs  = tmp_path / "sub-01_space-ScanRAS_coordsystem.json"
        _write_tsv(tsv, [("E1", 0.05, -0.03, 0.01)])
        _write_coordsystem(cs, "m")
        assert _detect_tsv_units(tsv) == "m"

    def test_explicit_millimetres_in_coordsystem_json(self, tmp_path):
        tsv = tmp_path / "sub-01_space-ScanRAS_electrodes.tsv"
        cs  = tmp_path / "sub-01_space-ScanRAS_coordsystem.json"
        _write_tsv(tsv, [("E1", 50.0, -30.0, 10.0)])
        _write_coordsystem(cs, "mm")
        assert _detect_tsv_units(tsv) == "mm"

    def test_heuristic_metres_when_no_coordsystem(self, tmp_path):
        tsv = tmp_path / "electrodes.tsv"
        _write_tsv(tsv, [("E1", -0.035, 0.029, -0.010)])
        assert _detect_tsv_units(tsv) == "m"

    def test_heuristic_millimetres_when_no_coordsystem(self, tmp_path):
        tsv = tmp_path / "electrodes.tsv"
        _write_tsv(tsv, [("E1", -35.0, 29.0, -10.0)])
        assert _detect_tsv_units(tsv) == "mm"


# ──────────────────────────────────────────────────────────────────────────
# load_ground_truth
# ──────────────────────────────────────────────────────────────────────────

class TestLoadGroundTruth:
    def test_bids_tsv_meters_converts_to_mm(self, tmp_path):
        tsv = tmp_path / "sub-01_space-ScanRAS_electrodes.tsv"
        cs  = tmp_path / "sub-01_space-ScanRAS_coordsystem.json"
        _write_tsv(tsv, [
            ("LTP1", -0.0354, 0.0296, -0.0103),
            ("LTP2", -0.0376, 0.0309, -0.0099),
        ])
        _write_coordsystem(cs, "m")

        out = load_ground_truth(str(tsv))
        assert len(out) == 2
        # First electrode: -0.0354 m → -35.4 mm
        np.testing.assert_allclose(out[0]["gt_mm"], [-35.4, 29.6, -10.3], atol=0.5)
        assert out[0]["id"] == "LTP1"
        assert out[1]["id"] == "LTP2"

    def test_bids_tsv_already_in_mm_passes_through(self, tmp_path):
        tsv = tmp_path / "elec.tsv"
        _write_tsv(tsv, [("E1", -35.4, 29.6, -10.3)])
        out = load_ground_truth(str(tsv))
        np.testing.assert_allclose(out[0]["gt_mm"], [-35.4, 29.6, -10.3])

    def test_json_format_passthrough_in_mm(self, tmp_path):
        path = tmp_path / "gt.json"
        path.write_text(json.dumps([
            {"id": 1, "gt_mm": [-35.4, 29.6, -10.3]},
            {"id": 2, "gt_mm": [-37.6, 30.9, -9.9]},
        ]))
        out = load_ground_truth(str(path))
        assert len(out) == 2
        np.testing.assert_allclose(out[0]["gt_mm"], [-35.4, 29.6, -10.3])
        assert out[0]["id"] == 1

    def test_explicit_units_override_detection(self, tmp_path):
        """Caller can force interpretation when the file is mislabelled."""
        tsv = tmp_path / "elec.tsv"
        # Values that would auto-detect as mm
        _write_tsv(tsv, [("E1", 35.4, 29.6, 10.3)])
        out = load_ground_truth(str(tsv), units="m")
        # Forced m → multiplied by 1000
        np.testing.assert_allclose(out[0]["gt_mm"], [35400.0, 29600.0, 10300.0])
