"""Export pipeline outputs as a single JSON for the browser viewer.

Called from `main.py` when `--export-viewer` is set. Produces
`outputs/viewer/data.json` containing:

    - patient_id        identifier shown in the viewer top bar
    - mesh.lh / mesh.rh decimated pial vertices, faces, per-vertex BA labels (tkRAS)
    - electrodes        per-electrode dict (id, coords, BA, anatomy, shift)
    - regions           BA -> {name, group, schematic_id, color} for the legend
                        and 2D schematic mapping

Mesh decimation (default 80 %) keeps the JSON file under ~5 MB and the
browser-side rendering interactive.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import nibabel.freesurfer as fs
import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Brodmann area metadata
# Maps each BA integer to (anatomical_group, schematic_region_id, color_hex).
# `schematic_region_id` matches the IDs used by the 2D SVG view in
# `viewer/brain2d.jsx`. Colors are inspired by the design hand-off palette.
# ──────────────────────────────────────────────────────────────────────────────

BA_GROUPS: dict[int, tuple[str, str, str]] = {
    1:  ("Somatosensory", "postcentral",       "#5FA86F"),
    2:  ("Somatosensory", "postcentral",       "#5FA86F"),
    3:  ("Somatosensory", "postcentral",       "#5FA86F"),
    4:  ("Motor",         "precentral",        "#3FA39A"),
    5:  ("Parietal",      "parietal",          "#E0A94E"),
    6:  ("Motor",         "precentral",        "#3FA39A"),
    7:  ("Parietal",      "parietal",          "#E0A94E"),
    8:  ("Frontal",       "frontal",           "#6E93C8"),
    9:  ("Frontal",       "frontal",           "#6E93C8"),
    10: ("Frontal",       "frontal",           "#6E93C8"),
    11: ("Frontal",       "frontal",           "#6E93C8"),
    17: ("Occipital",     "occipital",         "#D86C5A"),
    18: ("Occipital",     "occipital",         "#D86C5A"),
    19: ("Occipital",     "occipital",         "#D86C5A"),
    20: ("Temporal",      "temporal",          "#9B7BC4"),
    21: ("Temporal",      "temporal",          "#9B7BC4"),
    22: ("Temporal",      "superior-temporal", "#B79AD6"),
    37: ("Temporal",      "temporal",          "#9B7BC4"),
    39: ("Parietal",      "angular",           "#C98A5A"),
    40: ("Parietal",      "supramarginal",     "#E8B96B"),
    41: ("Auditory",      "superior-temporal", "#B79AD6"),
    42: ("Auditory",      "superior-temporal", "#B79AD6"),
    44: ("Language",      "broca",             "#E0789B"),
    45: ("Language",      "broca",             "#E0789B"),
    46: ("Frontal",       "frontal",           "#6E93C8"),
    47: ("Frontal",       "frontal",           "#6E93C8"),
}

_UNLABELED = ("Unlabeled", "unknown", "#555a66")

# Non-numeric FreeSurfer exvivo label prefixes that map to a BA integer
# (kept consistent with `src/labeling.lookup_brodmann_surface`).
_EXVIVO_MAP: dict[str, int] = {"V1": 17, "V2": 18, "V3": 19, "MT": 21}

# Desikan-Killiany cortical sub-region name → schematic region id.
# Lets aseg-cortical electrodes (no BA mapping) still appear on the 2D schematic
# in their best-matching anatomical area instead of being banished to the pool.
# `None` means "no schematic match — keep in the pool" (e.g. insula is medial,
# not on a lateral schematic).
_DK_TO_SCHEMATIC: dict[str, str | None] = {
    # Motor / somatosensory
    "precentral":               "precentral",
    "paracentral":              "precentral",
    "postcentral":              "postcentral",
    # Frontal
    "superiorfrontal":          "frontal",
    "rostralmiddlefrontal":     "frontal",
    "caudalmiddlefrontal":      "frontal",
    "lateralorbitofrontal":     "frontal",
    "medialorbitofrontal":      "frontal",
    "frontalpole":              "frontal",
    "rostralanteriorcingulate": "frontal",
    "caudalanteriorcingulate":  "frontal",
    # Broca's
    "parsopercularis":          "broca",
    "parstriangularis":         "broca",
    "parsorbitalis":            "broca",
    # Parietal
    "superiorparietal":         "parietal",
    "inferiorparietal":         "parietal",
    "precuneus":                "parietal",
    "posteriorcingulate":       "parietal",
    "isthmuscingulate":         "parietal",
    "supramarginal":            "supramarginal",
    "bankssts":                 "supramarginal",
    # Temporal
    "superiortemporal":         "superior-temporal",
    "transversetemporal":       "superior-temporal",
    "middletemporal":           "temporal",
    "inferiortemporal":         "temporal",
    "temporalpole":             "temporal",
    "fusiform":                 "temporal",
    "entorhinal":               "temporal",
    "parahippocampal":          "temporal",
    # Occipital
    "lateraloccipital":         "occipital",
    "cuneus":                   "occipital",
    "lingual":                  "occipital",
    "pericalcarine":            "occipital",
    # Insula is medial-deep — no good lateral-schematic location, stays in pool
    "insula":                   None,
}


def _schematic_id_from_aseg_label(aseg_label: str) -> str | None:
    """Derive a schematic region id from a Desikan-Killiany label like
    'ctx-lh-precentral' or 'ctx-rh-superiortemporal'. Returns None when no
    good schematic match exists (electrode stays in the pool)."""
    if not aseg_label.startswith(("ctx-lh-", "ctx-rh-")):
        return None
    sub = aseg_label[len("ctx-lh-"):]  # same length for both hemispheres
    return _DK_TO_SCHEMATIC.get(sub)


# ──────────────────────────────────────────────────────────────────────────────
# Annotation parsing
# ──────────────────────────────────────────────────────────────────────────────

def _annot_name_to_ba(name: str) -> int:
    """Convert a FreeSurfer BA_exvivo label name (e.g. 'BA4_exvivo') to a BA int."""
    m = re.match(r"BA(\d+)", name)
    if m:
        return int(m.group(1))
    prefix = re.match(r"([A-Za-z0-9]+)_?exvivo", name)
    return _EXVIVO_MAP.get(prefix.group(1) if prefix else "", 0)


def annot_to_ba_array(annot_labels: np.ndarray, annot_names: list) -> np.ndarray:
    """Convert an array of per-vertex annotation indices to per-vertex BA integers.

    Args:
        annot_labels: (V,) int array of annotation indices from `fs.read_annot`.
        annot_names:  list of bytes/str names indexed by annotation index.

    Returns:
        (V,) int array where each entry is the BA number (0 if unlabeled).
    """
    name_to_ba: dict[int, int] = {}
    for i, name in enumerate(annot_names):
        nm = name.decode() if isinstance(name, bytes) else name
        name_to_ba[i] = _annot_name_to_ba(nm)

    out = np.zeros(len(annot_labels), dtype=int)
    for i, lbl in enumerate(annot_labels):
        if 0 <= int(lbl) < len(annot_names):
            out[i] = name_to_ba.get(int(lbl), 0)
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Mesh decimation with label preservation
# ──────────────────────────────────────────────────────────────────────────────

def _decimate_with_labels(
    verts: np.ndarray,
    faces: np.ndarray,
    labels: np.ndarray,
    target_reduction: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decimate a triangular mesh while preserving per-vertex categorical labels.

    Decimation merges vertices, which would average BA integer labels and break
    the parcellation. We instead re-attach labels to the decimated mesh via
    nearest-neighbour lookup on the original vertices.

    Falls back to the original mesh if `pyvista` is not installed.
    """
    if target_reduction <= 0:
        return verts, faces, labels

    try:
        import pyvista as pv
    except ImportError:
        print("[WARNING] pyvista not installed — skipping mesh decimation.")
        return verts, faces, labels

    faces_pv = np.hstack(
        [np.full((len(faces), 1), 3, dtype=np.int64), faces.astype(np.int64)]
    ).ravel()
    mesh = pv.PolyData(verts.astype(np.float64), faces_pv)
    decimated = mesh.decimate(target_reduction)

    new_verts = np.asarray(decimated.points)
    new_faces = np.asarray(decimated.faces).reshape(-1, 4)[:, 1:]

    from scipy.spatial import cKDTree
    _, nn_idx = cKDTree(verts).query(new_verts)
    new_labels = labels[nn_idx]
    return new_verts, new_faces, new_labels


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def export_viewer_data(
    electrodes: list[dict],
    lh_verts: np.ndarray,
    lh_faces: np.ndarray,
    rh_verts: np.ndarray,
    rh_faces: np.ndarray,
    lh_annot_path: str,
    rh_annot_path: str,
    output_path: str | Path,
    patient_id: str = "unknown",
    target_reduction: float = 0.8,
) -> Path:
    """Bundle pipeline outputs into a single JSON for the browser viewer.

    Args:
        electrodes:        Pipeline electrode list (output of `lookup_brodmann_surface`).
                           Required keys: id, brodmann_area. Optional: centroid_mm,
                           corrected_mm, shift_mm, anatomy_label.
        lh_verts, lh_faces: Left-hemisphere pial mesh in tkRAS (from `mne.read_surface`).
        rh_verts, rh_faces: Right-hemisphere pial mesh in tkRAS.
        lh_annot_path:     Path to `lh.BA_exvivo.annot`.
        rh_annot_path:     Path to `rh.BA_exvivo.annot`.
        output_path:       Destination path for `data.json`.
        patient_id:        Identifier shown in the viewer top bar.
        target_reduction:  Mesh decimation factor in [0.0, 1.0). 0.8 = keep 20 %
                           of triangles (~30k verts per hemisphere from MNE sample).

    Returns:
        Path to the written JSON file.
    """
    from src.labeling import BRODMANN_LABELS  # imported here to avoid hard dep at import time

    # ── Per-vertex BA labels ────────────────────────────────────────────────
    lh_idx, _, lh_names = fs.read_annot(lh_annot_path)
    rh_idx, _, rh_names = fs.read_annot(rh_annot_path)
    lh_ba = annot_to_ba_array(lh_idx, lh_names)
    rh_ba = annot_to_ba_array(rh_idx, rh_names)

    # The annot files index the same pial vertices as `mne.read_surface`.
    # If counts disagree the caller passed mismatched files — refuse early.
    if len(lh_ba) != len(lh_verts):
        raise ValueError(
            f"LH annot has {len(lh_ba)} labels but mesh has {len(lh_verts)} vertices. "
            "Pass the lh.pial and lh.BA_exvivo.annot from the same subject."
        )
    if len(rh_ba) != len(rh_verts):
        raise ValueError(
            f"RH annot has {len(rh_ba)} labels but mesh has {len(rh_verts)} vertices. "
            "Pass the rh.pial and rh.BA_exvivo.annot from the same subject."
        )

    # ── Decimate each hemisphere (labels preserved via NN lookup) ───────────
    print(f"Decimating LH ({len(lh_verts)} verts → ~{int(len(lh_verts)*(1-target_reduction))} verts)...")
    lh_verts, lh_faces, lh_ba = _decimate_with_labels(
        lh_verts, lh_faces, lh_ba, target_reduction)

    print(f"Decimating RH ({len(rh_verts)} verts → ~{int(len(rh_verts)*(1-target_reduction))} verts)...")
    rh_verts, rh_faces, rh_ba = _decimate_with_labels(
        rh_verts, rh_faces, rh_ba, target_reduction)

    # ── Electrodes (only the fields the viewer needs) ───────────────────────
    # `mni_mm` is exported even though the current single-patient UI doesn't
    # use it — it's the common frame needed for the future multi-patient
    # comparison view (F-1 in sprint_plan.md).
    elec_out: list[dict] = []
    for e in electrodes:
        ba = int(e.get("brodmann_area", 0))
        group, schematic_id, _ = BA_GROUPS.get(ba, _UNLABELED)
        # When BA didn't yield a schematic match, try the volumetric atlas:
        # a cortical aseg label (e.g. ctx-lh-precentral) can place the
        # electrode in the matching schematic region.
        if schematic_id == "unknown":
            aseg_label = str(e.get("aseg_label", ""))
            sch_from_aseg = _schematic_id_from_aseg_label(aseg_label)
            if sch_from_aseg:
                schematic_id = sch_from_aseg
                # Keep `group` as "Unlabeled" so the UI knows there's no BA,
                # but the electrode now lives on the schematic.
        centroid = np.asarray(e.get("centroid_mm", [0.0, 0.0, 0.0]))
        corrected = np.asarray(e.get("corrected_mm", centroid))
        mni = e.get("mni_mm")
        elec_out.append({
            "id":            str(e["id"]),
            "centroid_mm":   [round(float(c), 3) for c in centroid],
            "corrected_mm":  [round(float(c), 3) for c in corrected],
            "mni_mm":        [round(float(c), 3) for c in np.asarray(mni)] if mni is not None else None,
            "shift_mm":      round(float(e.get("shift_mm", 0.0)), 3),
            "brodmann_area": ba,
            "anatomy_label": str(e.get("anatomy_label", "")),
            "group":         group,
            "schematic_id":  schematic_id,
            # Volumetric Desikan-Killiany / ASEG labels (filled in by lookup_aseg
            # in src/labeling.py — present when the pipeline ran with aparc+aseg.mgz)
            "aseg_code":     int(e.get("aseg_code", 0)),
            "aseg_label":    str(e.get("aseg_label", "")),
            "aseg_group":    str(e.get("aseg_group", "unknown")),
        })

    # ── Region metadata for the legend + 2D schematic ───────────────────────
    present_bas: set[int] = set()
    present_bas.update(int(b) for b in np.unique(lh_ba))
    present_bas.update(int(b) for b in np.unique(rh_ba))
    present_bas.update(e["brodmann_area"] for e in elec_out)
    present_bas.discard(0)

    regions_out: dict[str, dict] = {}
    for ba in sorted(present_bas):
        group, schematic_id, color = BA_GROUPS.get(ba, _UNLABELED)
        regions_out[str(ba)] = {
            "ba":           ba,
            "name":         BRODMANN_LABELS.get(ba, f"BA {ba}"),
            "group":        group,
            "schematic_id": schematic_id,
            "color":        color,
        }

    # ── Assemble + write ────────────────────────────────────────────────────
    data = {
        "patient_id": patient_id,
        "mesh": {
            "lh": {
                "vertices":  [[round(float(v), 2) for v in row] for row in lh_verts],
                "faces":     [[int(i) for i in row] for row in lh_faces],
                "ba_labels": [int(b) for b in lh_ba],
            },
            "rh": {
                "vertices":  [[round(float(v), 2) for v in row] for row in rh_verts],
                "faces":     [[int(i) for i in row] for row in rh_faces],
                "ba_labels": [int(b) for b in rh_ba],
            },
        },
        "electrodes": elec_out,
        "regions":    regions_out,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f)

    # Multi-patient layout (Switch mode):
    #   outputs/viewer/                        ← root the viewer is served from
    #   ├── <patient_id>/data.json             ← per-patient bundle (fetched on demand)
    #   ├── manifest.js                        ← lists all known patients
    #   ├── data.json, data.js                 ← legacy "default patient" copy (kept
    #   └── ...                                  for backwards compat; new viewer
    #                                            prefers the manifest path)
    viewer_root = output_path.parent
    per_patient_dir = viewer_root / patient_id
    per_patient_dir.mkdir(parents=True, exist_ok=True)
    per_patient_path = per_patient_dir / "data.json"
    with open(per_patient_path, "w") as f:
        json.dump(data, f)

    # Legacy fallback: viewer/index.html still works without the manifest,
    # in single-patient mode, when only outputs/viewer/data.js exists.
    js_path = output_path.with_suffix(".js")
    with open(js_path, "w") as f:
        f.write("window.NEM_DATA = ")
        json.dump(data, f)
        f.write(";\n")

    _refresh_manifest(viewer_root)

    size_mb = output_path.stat().st_size / 1e6
    print(f"Viewer data exported: {per_patient_path}  ({size_mb:.2f} MB)")
    print(f"Viewer data (legacy): {output_path} / {js_path.name}")
    print(f"Manifest refreshed:   {viewer_root / 'manifest.js'}")
    return per_patient_path


def _refresh_manifest(viewer_root: Path) -> None:
    """Scan `viewer_root/<id>/data.json` and rebuild `manifest.js`.

    The viewer loads `manifest.js` synchronously and then fetches the
    selected patient's `data.json` on demand. The manifest only carries
    cheap summary info — the full mesh stays in each per-patient bundle.

    Each patient entry also carries an ISO-8601 `processed_at` timestamp
    (taken from `data.json`'s mtime) so the viewer can sort patients by
    freshness, surface stale runs, and the user can tell at a glance
    whether a patient still reflects the current pipeline.
    """
    from datetime import datetime, timezone

    patients: list[dict] = []
    for sub in sorted(viewer_root.iterdir()):
        if not sub.is_dir():
            continue
        data_file = sub / "data.json"
        if not data_file.exists():
            continue
        try:
            with open(data_file) as f:
                pdata = json.load(f)
        except Exception:
            continue
        processed_at = datetime.fromtimestamp(
            data_file.stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds")
        patients.append({
            "id":           sub.name,
            "patient_id":   pdata.get("patient_id", sub.name),
            "n_electrodes": len(pdata.get("electrodes", [])),
            "n_regions":    len(pdata.get("regions", {})),
            "data_url":     f"{sub.name}/data.json",
            "processed_at": processed_at,
        })

    manifest = {
        "version":   1,
        "patients":  patients,
        # Manifest-level timestamp records when the scan was last refreshed.
        # Useful for diagnostics when something looks stale on disk.
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }
    with open(viewer_root / "manifest.js", "w") as f:
        f.write("window.NEM_MANIFEST = ")
        json.dump(manifest, f, indent=2)
        f.write(";\n")
