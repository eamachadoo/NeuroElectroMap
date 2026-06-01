"""Tests for Phase 3: labeling.py"""

import numpy as np
import nibabel as nib
import pytest
from src.labeling import (
    normalize_to_mni,
    compute_euclidean_error,
    export_report,
    lookup_aseg,
    _aseg_code_to_name,
    _aseg_group,
    _find_nearest_labeled_voxel,
)
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


def test_compute_euclidean_error_mismatched_counts():
    """NN matching: 5 predicted, 3 GT — must return 3 errors and not crash."""
    predicted = _make_electrodes(5)
    ground_truth = [
        {"id": 1, "gt_mm": np.array([0.0, 0.0, 0.0])},
        {"id": 2, "gt_mm": np.array([1.0, 1.0, 1.0])},
        {"id": 3, "gt_mm": np.array([2.0, 2.0, 2.0])},
    ]
    stats = compute_euclidean_error(predicted, ground_truth)
    assert len(stats["per_electrode"]) == 3
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


# ──────────────────────────────────────────────────────────────────────────
# ASEG / Desikan-Killiany volumetric labelling
# ──────────────────────────────────────────────────────────────────────────

class TestAsegCodeMapping:
    """The static LUT must classify FreeSurfer codes into clinical groups."""

    @pytest.mark.parametrize("code,expected_name", [
        (17,   "Left-Hippocampus"),
        (53,   "Right-Hippocampus"),
        (18,   "Left-Amygdala"),
        (10,   "Left-Thalamus-Proper"),
        (2,    "Left-Cerebral-White-Matter"),
        (0,    "Unknown"),
        (1024, "ctx-lh-precentral"),
        (2030, "ctx-rh-superiortemporal"),
        (2035, "ctx-rh-insula"),
        (16,   "Brain-Stem"),
    ])
    def test_aseg_code_to_name_known(self, code, expected_name):
        assert _aseg_code_to_name(code) == expected_name

    def test_aseg_code_to_name_unknown_code_passthrough(self):
        # Codes outside the LUT should produce a stable "Unknown (<code>)" sentinel
        assert _aseg_code_to_name(99999) == "Unknown (99999)"

    @pytest.mark.parametrize("code,expected_group", [
        (17,   "subcortical-limbic"),     # hippocampus
        (54,   "subcortical-limbic"),     # amygdala
        (10,   "thalamus"),
        (11,   "basal-ganglia"),          # caudate
        (12,   "basal-ganglia"),          # putamen
        (2,    "white-matter"),
        (4,    "ventricle-csf"),
        (16,   "brain-stem"),
        (8,    "cerebellum"),
        (1024, "cortical"),               # ctx-lh-precentral
        (2024, "cortical"),               # ctx-rh-precentral
    ])
    def test_aseg_group(self, code, expected_group):
        assert _aseg_group(code) == expected_group


class TestFindNearestLabeledVoxel:
    """Boundary-rescue helper used by lookup_aseg when the centroid voxel is 0."""

    def test_returns_zero_when_neighbourhood_all_unlabelled(self):
        data = np.zeros((10, 10, 10), dtype=int)
        code = _find_nearest_labeled_voxel(data, np.array([5, 5, 5]), radius=2)
        assert code == 0

    def test_finds_adjacent_label(self):
        data = np.zeros((10, 10, 10), dtype=int)
        data[5, 5, 6] = 17  # Hippocampus directly next door
        code = _find_nearest_labeled_voxel(data, np.array([5, 5, 5]), radius=2)
        assert code == 17

    def test_prefers_closest_over_distant_label(self):
        data = np.zeros((10, 10, 10), dtype=int)
        data[5, 5, 7] = 17    # 2 voxels away
        data[5, 5, 8] = 18    # 3 voxels away
        code = _find_nearest_labeled_voxel(data, np.array([5, 5, 5]), radius=4)
        assert code == 17, "must pick the geometrically nearest non-zero voxel"

    def test_respects_radius(self):
        data = np.zeros((10, 10, 10), dtype=int)
        data[5, 5, 9] = 17  # 4 voxels away
        # radius=2 should NOT see this label
        assert _find_nearest_labeled_voxel(data, np.array([5, 5, 5]), radius=2) == 0
        # radius=4 should
        assert _find_nearest_labeled_voxel(data, np.array([5, 5, 5]), radius=4) == 17


class TestLookupAseg:
    """Volumetric labelling end-to-end on a synthetic MGZ-like volume."""

    @pytest.fixture
    def synthetic_aseg(self, tmp_path):
        """Tiny 32³ atlas: hippocampus at one voxel, white matter elsewhere."""
        shape = (32, 32, 32)
        data = np.full(shape, 2, dtype=np.int32)  # Left-Cerebral-White-Matter
        data[16, 16, 16] = 17                     # Left-Hippocampus at the centre
        data[4,  4,  4]  = 0                      # an unlabelled boundary voxel
        # Use an identity-shifted affine so that world (0,0,0) → voxel (16,16,16).
        affine = np.eye(4)
        affine[:3, 3] = [-16, -16, -16]
        img = nib.Nifti1Image(data, affine)
        # Persist; tests pass the path to lookup_aseg.
        path = tmp_path / "aseg.nii.gz"
        nib.save(img, path)
        return path

    def test_direct_hit_hippocampus(self, synthetic_aseg, monkeypatch):
        # Use scanner frame because our fixture only sets `affine` (not vox2ras_tkr)
        electrodes = [{"id": 1, "centroid_mm": np.array([0.0, 0.0, 0.0])}]
        out = lookup_aseg(electrodes, str(synthetic_aseg),
                          coord_key="centroid_mm", frame="scanner",
                          search_radius=0)
        assert out[0]["aseg_code"]  == 17
        assert out[0]["aseg_label"] == "Left-Hippocampus"
        assert out[0]["aseg_group"] == "subcortical-limbic"

    def test_white_matter_default(self, synthetic_aseg):
        # Pick a coord that lands in the white-matter background
        electrodes = [{"id": 1, "centroid_mm": np.array([5.0, 5.0, 5.0])}]
        out = lookup_aseg(electrodes, str(synthetic_aseg),
                          coord_key="centroid_mm", frame="scanner",
                          search_radius=0)
        assert out[0]["aseg_label"] == "Left-Cerebral-White-Matter"
        assert out[0]["aseg_group"] == "white-matter"

    def test_boundary_rescue_with_radius(self, synthetic_aseg):
        # World (-12,-12,-12) → voxel (4,4,4) which we set to 0 in the fixture.
        # With search_radius=0 we should get 0/Unknown; with radius=2 we should
        # find the surrounding white matter.
        electrodes = [{"id": 1, "centroid_mm": np.array([-12.0, -12.0, -12.0])}]

        out0 = lookup_aseg(electrodes, str(synthetic_aseg),
                           coord_key="centroid_mm", frame="scanner",
                           search_radius=0)
        assert out0[0]["aseg_code"]  == 0
        assert out0[0]["aseg_label"] == "Unknown"
        assert out0[0]["aseg_group"] == "unknown"

        out2 = lookup_aseg(electrodes, str(synthetic_aseg),
                           coord_key="centroid_mm", frame="scanner",
                           search_radius=2)
        assert out2[0]["aseg_code"]  == 2
        assert out2[0]["aseg_label"] == "Left-Cerebral-White-Matter"

    def test_missing_coord_returns_unknown(self, synthetic_aseg):
        electrodes = [{"id": 1}]  # no centroid_mm key
        out = lookup_aseg(electrodes, str(synthetic_aseg),
                          coord_key="centroid_mm", frame="scanner")
        assert out[0]["aseg_code"]  == 0
        assert out[0]["aseg_label"] == "Unknown"

    def test_invalid_frame_raises(self, synthetic_aseg):
        with pytest.raises(ValueError, match="frame must be"):
            lookup_aseg([], str(synthetic_aseg), frame="nope")
