"""Tests for the Python → browser-viewer bridge (scripts/export_for_viewer.py).

Covers the helpers the viewer relies on (BA name parsing, DK→schematic remap,
per-vertex BA arrays) plus a full smoke run of `export_viewer_data` with a
small synthetic mesh and annotation. No real FreeSurfer subject required.
"""

from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from scripts.export_for_viewer import (
    _UNLABELED,
    BA_GROUPS,
    _annot_name_to_ba,
    _decimate_with_labels,
    _schematic_id_from_aseg_label,
    annot_to_ba_array,
    export_viewer_data,
)


# ──────────────────────────────────────────────────────────────────────────
# BA name parsing (FreeSurfer BA_exvivo conventions)
# ──────────────────────────────────────────────────────────────────────────

class TestAnnotNameToBA:
    @pytest.mark.parametrize("name,expected", [
        ("BA1_exvivo",  1),
        ("BA22_exvivo", 22),
        ("BA45_exvivo", 45),
        # The "V<n>" / "MT" prefixes are FreeSurfer's non-numeric BA aliases.
        ("V1_exvivo",   17),
        ("V2_exvivo",   18),
        ("V3_exvivo",   19),
        ("MT_exvivo",   21),
        # Things that don't match any pattern should resolve to 0 (unlabelled).
        ("unknown",     0),
        ("",            0),
        ("random",      0),
    ])
    def test_known_patterns(self, name, expected):
        assert _annot_name_to_ba(name) == expected


# ──────────────────────────────────────────────────────────────────────────
# Per-vertex BA array
# ──────────────────────────────────────────────────────────────────────────

def test_annot_to_ba_array_basic():
    # Three names, four vertices — last vertex uses the unlabelled name.
    names = [b"unknown", b"BA22_exvivo", b"V1_exvivo"]
    labels = np.array([1, 2, 0, 1])
    out = annot_to_ba_array(labels, names)
    np.testing.assert_array_equal(out, [22, 17, 0, 22])


def test_annot_to_ba_array_out_of_range_label():
    """A label index outside `names` must not crash — clamps to 0."""
    names = [b"unknown", b"BA4_exvivo"]
    labels = np.array([0, 1, 99])  # index 99 is out of range
    out = annot_to_ba_array(labels, names)
    np.testing.assert_array_equal(out, [0, 4, 0])


# ──────────────────────────────────────────────────────────────────────────
# Desikan-Killiany → schematic remap (used by the 2D viewer)
# ──────────────────────────────────────────────────────────────────────────

class TestDKToSchematic:
    @pytest.mark.parametrize("aseg_label,expected", [
        ("ctx-lh-precentral",       "precentral"),
        ("ctx-rh-precentral",       "precentral"),
        ("ctx-lh-postcentral",      "postcentral"),
        ("ctx-rh-superiortemporal", "superior-temporal"),
        ("ctx-lh-parsopercularis",  "broca"),
        ("ctx-rh-supramarginal",    "supramarginal"),
        ("ctx-lh-lateraloccipital", "occipital"),
        ("ctx-rh-superiorfrontal",  "frontal"),
    ])
    def test_known_mappings(self, aseg_label, expected):
        assert _schematic_id_from_aseg_label(aseg_label) == expected

    @pytest.mark.parametrize("aseg_label", [
        "ctx-lh-insula",       # medial — explicitly excluded from lateral schematic
        "Left-Hippocampus",    # subcortical — no cortical schematic match
        "Left-Cerebral-White-Matter",
        "Brain-Stem",
        "",
        "garbage",
    ])
    def test_returns_none_when_no_schematic_match(self, aseg_label):
        assert _schematic_id_from_aseg_label(aseg_label) is None


# ──────────────────────────────────────────────────────────────────────────
# BA_GROUPS shape contract (the JS viewer reads these)
# ──────────────────────────────────────────────────────────────────────────

def test_ba_groups_shape():
    assert len(BA_GROUPS) > 0
    for ba, triple in BA_GROUPS.items():
        assert isinstance(ba, int)
        assert len(triple) == 3, f"BA {ba} must be (group, schematic_id, color)"
        group, schematic_id, color = triple
        assert isinstance(group, str) and group
        assert isinstance(schematic_id, str) and schematic_id
        assert color.startswith("#") and len(color) == 7


def test_unlabeled_sentinel_shape():
    assert len(_UNLABELED) == 3
    assert _UNLABELED[0] == "Unlabeled"
    assert _UNLABELED[1] == "unknown"


# ──────────────────────────────────────────────────────────────────────────
# Mesh decimation (label-preserving)
# ──────────────────────────────────────────────────────────────────────────

def test_decimate_with_labels_zero_reduction_returns_inputs():
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    faces = np.array([[0, 1, 2], [1, 3, 2]])
    labels = np.array([10, 20, 30, 40])
    v, f, l = _decimate_with_labels(verts, faces, labels, target_reduction=0)
    np.testing.assert_array_equal(v, verts)
    np.testing.assert_array_equal(f, faces)
    np.testing.assert_array_equal(l, labels)


# ──────────────────────────────────────────────────────────────────────────
# End-to-end export with a synthetic mesh + annot
# ──────────────────────────────────────────────────────────────────────────

def _write_synthetic_annot(path: Path, n_vertices: int = 4) -> None:
    """Write a tiny BA_exvivo-style annotation file.

    Vertices alternate between "unknown" (ctab row 0) and "BA22_exvivo"
    (ctab row 1). We let nibabel compute the per-row colour codes
    (`fill_ctab=True`) — manual code construction is brittle and not what
    our pipeline ever needs to do.
    """
    names = [b"unknown", b"BA22_exvivo"]
    # 4-column ctab; nibabel will fill the 5th (code) column itself.
    ctab = np.array([
        [200, 200, 200, 0],   # unknown
        [180, 100, 150, 0],   # BA22
    ], dtype=np.int32)
    annot_labels = np.array(
        [(i % 2) for i in range(n_vertices)], dtype=np.int32
    )
    from nibabel.freesurfer.io import write_annot
    write_annot(str(path), annot_labels, ctab, names, fill_ctab=True)


@pytest.fixture
def synthetic_subject(tmp_path):
    """Build a 4-vertex pial mesh + matching BA_exvivo annotation."""
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], float)
    faces = np.array([[0, 1, 2], [1, 3, 2]])
    lh_annot = tmp_path / "lh.BA_exvivo.annot"
    rh_annot = tmp_path / "rh.BA_exvivo.annot"
    _write_synthetic_annot(lh_annot, n_vertices=len(verts))
    _write_synthetic_annot(rh_annot, n_vertices=len(verts))
    return verts, faces, lh_annot, rh_annot


def test_export_viewer_data_end_to_end(synthetic_subject, tmp_path):
    verts, faces, lh_annot, rh_annot = synthetic_subject

    electrodes = [
        {
            "id": 1,
            "centroid_mm":   np.array([0.0, 0.0, 0.0]),
            "corrected_mm":  np.array([0.5, 0.5, 0.0]),
            "mni_mm":        np.array([-55.0, -42.0, 18.0]),
            "shift_mm":      1.2,
            "brodmann_area": 22,
            "anatomy_label": "Superior Temporal Gyrus / Wernicke's Area",
            "aseg_code":     2030,
            "aseg_label":    "ctx-lh-superiortemporal",
            "aseg_group":    "cortical",
        },
        # Deep electrode with no BA — exercises the aseg fallback path
        {
            "id": 2,
            "centroid_mm":   np.array([0.5, 0.5, 0.5]),
            "corrected_mm":  np.array([0.5, 0.5, 0.5]),
            "mni_mm":        None,
            "shift_mm":      12.0,
            "brodmann_area": 0,
            "anatomy_label": "",
            "aseg_code":     17,
            "aseg_label":    "Left-Hippocampus",
            "aseg_group":    "subcortical-limbic",
        },
    ]

    out_path = tmp_path / "data.json"
    export_viewer_data(
        electrodes=electrodes,
        lh_verts=verts, lh_faces=faces,
        rh_verts=verts, rh_faces=faces,
        lh_annot_path=str(lh_annot),
        rh_annot_path=str(rh_annot),
        output_path=out_path,
        patient_id="test-sub",
        target_reduction=0,  # 4 verts is already small — don't decimate
    )

    # Both files must exist
    assert out_path.exists()
    js_path = out_path.with_suffix(".js")
    assert js_path.exists()

    # data.js starts with the window-bind sentinel so the viewer can load it
    js_head = js_path.read_text()[:40]
    assert js_head.startswith("window.NEM_DATA = "), js_head

    data = json.loads(out_path.read_text())

    # ── top-level shape
    assert set(data.keys()) == {"patient_id", "mesh", "electrodes", "regions"}
    assert data["patient_id"] == "test-sub"

    # ── mesh per hemisphere
    for hemi in ("lh", "rh"):
        m = data["mesh"][hemi]
        assert {"vertices", "faces", "ba_labels"} <= set(m.keys())
        assert len(m["vertices"]) == 4
        assert len(m["faces"])    == 2
        assert len(m["ba_labels"]) == 4

    # ── electrodes carry the BA + aseg + coord fields the viewer needs
    e1, e2 = data["electrodes"]
    assert e1["id"] == "1"
    assert e1["brodmann_area"] == 22
    assert e1["schematic_id"]  == "superior-temporal"
    assert e1["mni_mm"] == [-55.0, -42.0, 18.0]
    assert e1["aseg_group"] == "cortical"

    # E2: BA=0 but aseg-cortical → schematic stays "unknown" because aseg_group
    # is subcortical-limbic (DK→schematic only promotes cortical labels).
    assert e2["brodmann_area"] == 0
    assert e2["aseg_label"]    == "Left-Hippocampus"
    assert e2["schematic_id"]  == "unknown"
    assert e2["mni_mm"] is None

    # ── regions metadata covers every BA that appears (electrodes + mesh)
    assert "22" in data["regions"]
    region22 = data["regions"]["22"]
    assert region22["ba"] == 22
    assert region22["schematic_id"] == "superior-temporal"
    assert region22["color"].startswith("#")


def test_export_viewer_data_promotes_aseg_cortical_to_schematic(synthetic_subject, tmp_path):
    """An aseg-cortical electrode with BA=0 should be placed on the matching
    schematic region (ctx-lh-precentral → schematic_id "precentral")."""
    verts, faces, lh_annot, rh_annot = synthetic_subject
    electrodes = [{
        "id": 99,
        "centroid_mm":  np.array([0.0, 0.0, 0.0]),
        "corrected_mm": np.array([0.0, 0.0, 0.0]),
        "shift_mm":     0.5,
        "brodmann_area": 0,                  # no BA hit from BA_exvivo
        "anatomy_label": "",
        "aseg_code":  1024,
        "aseg_label": "ctx-lh-precentral",   # cortical via DK
        "aseg_group": "cortical",
    }]
    out_path = tmp_path / "data.json"
    export_viewer_data(
        electrodes=electrodes,
        lh_verts=verts, lh_faces=faces,
        rh_verts=verts, rh_faces=faces,
        lh_annot_path=str(lh_annot),
        rh_annot_path=str(rh_annot),
        output_path=out_path,
        patient_id="test",
        target_reduction=0,
    )
    data = json.loads(out_path.read_text())
    assert data["electrodes"][0]["schematic_id"] == "precentral", \
        "DK label should route the electrode to the precentral schematic region"


def test_export_viewer_data_rejects_mesh_annot_mismatch(synthetic_subject, tmp_path):
    """If the caller passes a mesh that doesn't match the annot, refuse early
    with a clear error rather than producing a corrupt JSON."""
    verts, faces, lh_annot, rh_annot = synthetic_subject

    # 5-vertex mesh, annot only knows 4 — counts disagree
    bad_verts = np.vstack([verts, [[2.0, 2.0, 0.0]]])
    bad_faces = np.array([[0, 1, 2]])

    out_path = tmp_path / "data.json"
    with pytest.raises(ValueError, match="LH annot has"):
        export_viewer_data(
            electrodes=[],
            lh_verts=bad_verts, lh_faces=bad_faces,
            rh_verts=verts,     rh_faces=faces,
            lh_annot_path=str(lh_annot),
            rh_annot_path=str(rh_annot),
            output_path=out_path,
            patient_id="test",
            target_reduction=0,
        )


# ──────────────────────────────────────────────────────────────────────────
# Multi-patient manifest (Switch mode)
# ──────────────────────────────────────────────────────────────────────────

class TestManifest:
    """Each per-patient export must update outputs/viewer/manifest.js so the
    case selector lists every patient that has been processed."""

    def test_single_patient_manifest(self, synthetic_subject, tmp_path):
        verts, faces, lh_annot, rh_annot = synthetic_subject
        out_path = tmp_path / "data.json"
        export_viewer_data(
            electrodes=[],
            lh_verts=verts, lh_faces=faces,
            rh_verts=verts, rh_faces=faces,
            lh_annot_path=str(lh_annot),
            rh_annot_path=str(rh_annot),
            output_path=out_path,
            patient_id="sub-12",
            target_reduction=0,
        )

        # Files we promise the viewer can load
        assert (tmp_path / "sub-12" / "data.json").exists()
        assert (tmp_path / "manifest.js").exists()
        assert (tmp_path / "data.json").exists()  # legacy single-patient copy

        # Manifest is a JS file with a window-bind sentinel — strip it to JSON
        raw = (tmp_path / "manifest.js").read_text()
        assert raw.startswith("window.NEM_MANIFEST = ")
        manifest = json.loads(
            raw[len("window.NEM_MANIFEST = "):].rstrip(";\n ")
        )

        assert manifest["version"] == 1
        assert len(manifest["patients"]) == 1
        sub12 = manifest["patients"][0]
        assert sub12["id"]        == "sub-12"
        assert sub12["data_url"]  == "sub-12/data.json"
        assert "n_electrodes" in sub12
        assert "n_regions"    in sub12

        # Timestamps — ISO-8601 with timezone, format: 2026-06-02T17:30:00+00:00
        assert "processed_at" in sub12
        assert sub12["processed_at"].endswith("+00:00")
        assert "T" in sub12["processed_at"]
        assert "refreshed_at" in manifest
        assert manifest["refreshed_at"].endswith("+00:00")

    def test_multi_patient_manifest_accumulates(self, synthetic_subject, tmp_path):
        """Running the export for a second patient must keep the first one
        listed in the manifest."""
        verts, faces, lh_annot, rh_annot = synthetic_subject

        # First patient
        export_viewer_data(
            electrodes=[], lh_verts=verts, lh_faces=faces,
            rh_verts=verts, rh_faces=faces,
            lh_annot_path=str(lh_annot), rh_annot_path=str(rh_annot),
            output_path=tmp_path / "data.json",
            patient_id="sub-1", target_reduction=0,
        )
        # Second patient — same viewer root, different id
        export_viewer_data(
            electrodes=[], lh_verts=verts, lh_faces=faces,
            rh_verts=verts, rh_faces=faces,
            lh_annot_path=str(lh_annot), rh_annot_path=str(rh_annot),
            output_path=tmp_path / "data.json",
            patient_id="sub-2", target_reduction=0,
        )

        raw = (tmp_path / "manifest.js").read_text()
        manifest = json.loads(
            raw[len("window.NEM_MANIFEST = "):].rstrip(";\n ")
        )
        ids = sorted(p["id"] for p in manifest["patients"])
        assert ids == ["sub-1", "sub-2"]
        for p in manifest["patients"]:
            assert p["data_url"] == f"{p['id']}/data.json"

    def test_manifest_skips_non_directory_entries(self, synthetic_subject, tmp_path):
        """Stray files at the viewer root must not crash the scan."""
        verts, faces, lh_annot, rh_annot = synthetic_subject
        export_viewer_data(
            electrodes=[], lh_verts=verts, lh_faces=faces,
            rh_verts=verts, rh_faces=faces,
            lh_annot_path=str(lh_annot), rh_annot_path=str(rh_annot),
            output_path=tmp_path / "data.json",
            patient_id="sub-12", target_reduction=0,
        )
        # Add some noise next to the patient subdirs
        (tmp_path / "stray.txt").write_text("nothing to see here")
        (tmp_path / "broken-subdir").mkdir()  # no data.json inside

        # Re-export — manifest scan should still produce a single valid entry
        export_viewer_data(
            electrodes=[], lh_verts=verts, lh_faces=faces,
            rh_verts=verts, rh_faces=faces,
            lh_annot_path=str(lh_annot), rh_annot_path=str(rh_annot),
            output_path=tmp_path / "data.json",
            patient_id="sub-12", target_reduction=0,
        )
        raw = (tmp_path / "manifest.js").read_text()
        manifest = json.loads(
            raw[len("window.NEM_MANIFEST = "):].rstrip(";\n ")
        )
        ids = [p["id"] for p in manifest["patients"]]
        assert ids == ["sub-12"], f"got {ids}"
