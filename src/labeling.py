"""Phase 3: Anatomical Labeling & Atlas Integration (Weeks 6-8)

Task 3.1: MNI Normalization – transform patient coordinates → MNI152 space.
Task 3.2: Brodmann Lookup – query atlas for each electrode.
Task 3.3: Validation – compute Mean Euclidean Error vs. ground truth.
Task 4.2: Report export (CSV / Excel).
"""

import numpy as np
import pandas as pd
import nibabel as nib
from nilearn import datasets


# ──────────────────────────────────────────────────────────────────────────────
# Task 3.1 – MNI Normalization
# ──────────────────────────────────────────────────────────────────────────────

def normalize_to_mni(
    electrodes: list[dict],
    patient_to_mni_affine: np.ndarray,
    coord_key: str = "corrected_mm",
) -> list[dict]:
    """
    Transform electrode coordinates from patient space to MNI152 space.

    Args:
        electrodes:            List of electrode dicts.
        patient_to_mni_affine: 4x4 affine (patient world → MNI152).
        coord_key:             Which coordinate field to transform.

    Returns:
        Electrode list with added 'mni_mm' key.
    """
    normalized = []
    for elec in electrodes:
        pt = np.append(elec[coord_key], 1.0)
        mni_pt = (patient_to_mni_affine @ pt)[:3]
        normalized.append({**elec, "mni_mm": mni_pt})
    return normalized


# ──────────────────────────────────────────────────────────────────────────────
# Task 3.2 – Brodmann Atlas Lookup
# ──────────────────────────────────────────────────────────────────────────────

BRODMANN_LABELS: dict[int, str] = {
    1:  "Primary Somatosensory Cortex – tactile discrimination",
    2:  "Primary Somatosensory Cortex – somatosensory integration",
    3:  "Primary Somatosensory Cortex – tactile reception",
    4:  "Primary Motor Cortex (M1)",
    5:  "Somatosensory Association Cortex",
    6:  "Premotor & Supplementary Motor Cortex",
    7:  "Superior Parietal Lobule",
    8:  "Frontal Eye Fields",
    9:  "Dorsolateral Prefrontal Cortex",
    10: "Anterior Prefrontal Cortex",
    11: "Orbitofrontal Cortex",
    17: "Primary Visual Cortex (V1)",
    18: "Secondary Visual Cortex (V2)",
    19: "Associative Visual Cortex",
    21: "Middle Temporal Gyrus",
    22: "Superior Temporal Gyrus / Wernicke's Area",
    37: "Fusiform / Inferior Temporal Gyrus",
    39: "Angular Gyrus",
    40: "Supramarginal Gyrus",
    41: "Primary Auditory Cortex",
    42: "Secondary Auditory Cortex",
    44: "Pars Opercularis – Broca's Area",
    45: "Pars Triangularis – Broca's Area",
    46: "Dorsolateral Prefrontal Cortex",
    47: "Inferior Prefrontal Cortex",
}


def load_brodmann_atlas() -> nib.Nifti1Image:
    """
    Fetch the Brodmann area atlas in MNI space via nilearn (Talairach BA map).
    Returns the parcellation image (integer label per voxel).
    """
    atlas = datasets.fetch_atlas_talairach(level_name="ba")
    atlas_img = nib.load(atlas.maps)
    print("Brodmann atlas loaded.")
    return atlas_img


def lookup_brodmann(
    electrodes: list[dict],
    atlas_img: nib.Nifti1Image,
    coord_key: str = "mni_mm",
) -> list[dict]:
    """
    Sample the Brodmann atlas at each electrode's MNI coordinate.

    Returns:
        Electrode list with 'brodmann_area' (int) and 'anatomy_label' (str) added.
    """
    atlas_data = atlas_img.get_fdata()
    inv_affine = np.linalg.inv(atlas_img.affine)

    labeled = []
    for elec in electrodes:
        mni = np.append(elec[coord_key], 1.0)
        vox = (inv_affine @ mni)[:3].astype(int)
        vox = np.clip(vox, 0, np.array(atlas_data.shape) - 1)
        ba_id = int(atlas_data[tuple(vox)])

        labeled.append({
            **elec,
            "brodmann_area": ba_id,
            "anatomy_label": BRODMANN_LABELS.get(ba_id, f"BA {ba_id} (unlabeled)"),
        })

    return labeled


def lookup_brodmann_surface(
    electrodes: list[dict],
    pial_vertices: np.ndarray,
    lh_annot_path: str,
    rh_annot_path: str,
    n_lh_vertices: int,
    coord_key: str = "corrected_mm",
) -> list[dict]:
    """
    Look up Brodmann areas using FreeSurfer BA_exvivo surface annotations.
    Finds the nearest pial vertex for each electrode and reads its BA label.
    No network access required — uses local annotation files.

    Args:
        pial_vertices: (V, 3) combined LH+RH pial surface vertices (tkRAS).
        lh_annot_path: path to lh.BA_exvivo.annot
        rh_annot_path: path to rh.BA_exvivo.annot
        n_lh_vertices: number of LH vertices (offset for RH indexing).
        coord_key:     electrode coordinate to use for nearest-vertex lookup.
    """
    import nibabel.freesurfer as fs

    lh_labels, _, lh_names = fs.read_annot(lh_annot_path)
    rh_labels, _, rh_names = fs.read_annot(rh_annot_path)
    all_labels = np.concatenate([lh_labels, rh_labels])

    labeled = []
    for elec in electrodes:
        coord = elec.get(coord_key, elec.get("centroid_mm"))
        nearest_idx = int(np.argmin(np.linalg.norm(pial_vertices - coord, axis=1)))

        if nearest_idx < n_lh_vertices:
            raw_name = lh_names[lh_labels[nearest_idx]].decode()
        else:
            raw_name = rh_names[rh_labels[nearest_idx - n_lh_vertices]].decode()

        # FreeSurfer exvivo labels: "BA1_exvivo", "V1_exvivo" (=BA17), "V2_exvivo" (=BA18)
        import re
        _EXVIVO_MAP = {"V1": 17, "V2": 18, "V3": 19, "MT": 21}
        m = re.match(r"BA(\d+)", raw_name)
        if m:
            ba_id = int(m.group(1))
        else:
            prefix = re.match(r"([A-Za-z0-9]+)_?exvivo", raw_name)
            ba_id = _EXVIVO_MAP.get(prefix.group(1) if prefix else "", 0)

        labeled.append({
            **elec,
            "brodmann_area": ba_id,
            "anatomy_label": BRODMANN_LABELS.get(ba_id, raw_name or f"BA {ba_id} (unlabeled)"),
        })

    return labeled


# ──────────────────────────────────────────────────────────────────────────────
# Task 3.4 – Volumetric ASEG labeling (Desikan-Killiany + subcortical)
# ──────────────────────────────────────────────────────────────────────────────
#
# BA_exvivo only covers a handful of cortical Brodmann areas, leaving most
# electrodes (especially deep sEEG contacts) labeled as BA 0. Sampling the
# volumetric `aparc+aseg.mgz` atlas gives every electrode a meaningful
# anatomical name — cortical (Desikan-Killiany) or subcortical
# (Hippocampus, Amygdala, Thalamus, white matter, etc.).

# FreeSurfer ASEG label codes (subcortical, ventricles, brain-stem, etc.).
# Stable across FreeSurfer versions. Source: FreeSurferColorLUT.txt.
_ASEG_SUBCORTICAL: dict[int, str] = {
    0:  "Unknown",
    2:  "Left-Cerebral-White-Matter",
    4:  "Left-Lateral-Ventricle",
    5:  "Left-Inf-Lat-Vent",
    7:  "Left-Cerebellum-White-Matter",
    8:  "Left-Cerebellum-Cortex",
    10: "Left-Thalamus-Proper",
    11: "Left-Caudate",
    12: "Left-Putamen",
    13: "Left-Pallidum",
    14: "3rd-Ventricle",
    15: "4th-Ventricle",
    16: "Brain-Stem",
    17: "Left-Hippocampus",
    18: "Left-Amygdala",
    24: "CSF",
    26: "Left-Accumbens-area",
    28: "Left-VentralDC",
    30: "Left-vessel",
    31: "Left-choroid-plexus",
    41: "Right-Cerebral-White-Matter",
    43: "Right-Lateral-Ventricle",
    44: "Right-Inf-Lat-Vent",
    46: "Right-Cerebellum-White-Matter",
    47: "Right-Cerebellum-Cortex",
    49: "Right-Thalamus-Proper",
    50: "Right-Caudate",
    51: "Right-Putamen",
    52: "Right-Pallidum",
    53: "Right-Hippocampus",
    54: "Right-Amygdala",
    58: "Right-Accumbens-area",
    60: "Right-VentralDC",
    62: "Right-vessel",
    63: "Right-choroid-plexus",
    72: "5th-Ventricle",
    77: "WM-hypointensities",
    85: "Optic-Chiasm",
    251: "CC_Posterior",
    252: "CC_Mid_Posterior",
    253: "CC_Central",
    254: "CC_Mid_Anterior",
    255: "CC_Anterior",
}

# Cortical labels (Desikan-Killiany). Codes 1000-1035 = left, 2000-2035 = right.
_DK_CORTICAL: dict[int, str] = {
     1: "bankssts",                  2: "caudalanteriorcingulate",
     3: "caudalmiddlefrontal",       5: "cuneus",
     6: "entorhinal",                7: "fusiform",
     8: "inferiorparietal",          9: "inferiortemporal",
    10: "isthmuscingulate",         11: "lateraloccipital",
    12: "lateralorbitofrontal",     13: "lingual",
    14: "medialorbitofrontal",      15: "middletemporal",
    16: "parahippocampal",          17: "paracentral",
    18: "parsopercularis",          19: "parsorbitalis",
    20: "parstriangularis",         21: "pericalcarine",
    22: "postcentral",              23: "posteriorcingulate",
    24: "precentral",               25: "precuneus",
    26: "rostralanteriorcingulate", 27: "rostralmiddlefrontal",
    28: "superiorfrontal",          29: "superiorparietal",
    30: "superiortemporal",         31: "supramarginal",
    32: "frontalpole",              33: "temporalpole",
    34: "transversetemporal",       35: "insula",
}


def _aseg_code_to_name(code: int) -> str:
    """Translate any FreeSurfer ASEG/DK code to a human-readable name."""
    if 1000 <= code <= 1099:
        return f"ctx-lh-{_DK_CORTICAL.get(code - 1000, f'unknown-{code-1000}')}"
    if 2000 <= code <= 2099:
        return f"ctx-rh-{_DK_CORTICAL.get(code - 2000, f'unknown-{code-2000}')}"
    return _ASEG_SUBCORTICAL.get(int(code), f"Unknown ({int(code)})")


def _aseg_group(code: int) -> str:
    """Classify an ASEG label code into a clinical group for the UI."""
    if 1000 <= code <= 2099:
        return "cortical"
    if code in (17, 53):
        return "subcortical-limbic"   # hippocampus
    if code in (18, 54):
        return "subcortical-limbic"   # amygdala
    if code in (10, 49):
        return "thalamus"
    if code in (11, 50, 12, 51, 13, 52, 26, 58):
        return "basal-ganglia"
    if code in (2, 41, 77):
        return "white-matter"
    if code in (4, 43, 14, 15, 24, 5, 44, 72, 31, 63):
        return "ventricle-csf"
    if code in (7, 8, 46, 47):
        return "cerebellum"
    if code == 16:
        return "brain-stem"
    if code in (28, 60, 85, 30, 62) or 251 <= code <= 255:
        return "other"
    return "unknown"


def _find_nearest_labeled_voxel(
    aseg_data: np.ndarray,
    vox: np.ndarray,
    radius: int = 3,
) -> int:
    """Search a cubic neighbourhood for the nearest non-zero label.

    Returns the label code at the nearest non-zero voxel within `radius`,
    or 0 if everything in the neighbourhood is unlabelled. This rescues
    electrodes whose centroid falls on a boundary voxel (e.g. between
    grey matter and the pial surface) where the volumetric atlas isn't
    defined but a labelled voxel sits 1–2 mm away.
    """
    shape = np.array(aseg_data.shape)
    best_code, best_dist2 = 0, None
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                v = np.clip(vox + np.array([dx, dy, dz]), 0, shape - 1)
                code = int(aseg_data[tuple(v)])
                if code == 0:
                    continue
                d2 = dx * dx + dy * dy + dz * dz
                if best_dist2 is None or d2 < best_dist2:
                    best_code, best_dist2 = code, d2
    return best_code


def lookup_aseg(
    electrodes: list[dict],
    aseg_path: str,
    coord_key: str = "centroid_mm",
    frame: str = "tkr",
    search_radius: int = 5,
) -> list[dict]:
    """
    Assign Desikan-Killiany + subcortical labels to every electrode by
    sampling the FreeSurfer `aparc+aseg.mgz` volume.

    Args:
        electrodes: Pipeline electrode list. Each entry must carry a coordinate
                    at `coord_key`. By default uses `centroid_mm` in tkRAS
                    (the frame the pial surface and BA lookup already work in).
        aseg_path:  Path to `<subject>/mri/aparc+aseg.mgz`.
        coord_key:  Which coordinate field to sample.
        frame:      Either "tkr" (FreeSurfer surface RAS, default) or "scanner"
                    (original NIfTI scanner RAS). Must match `coord_key`.

    Returns:
        Electrodes with added fields:
            - aseg_code  (int)  FreeSurfer label code (0 = Unknown)
            - aseg_label (str)  Human-readable name (e.g. "Left-Hippocampus",
                                "ctx-lh-precentral", "Left-Cerebral-White-Matter")
            - aseg_group (str)  Clinical bucket — one of: cortical, subcortical-limbic,
                                basal-ganglia, thalamus, white-matter, ventricle-csf,
                                cerebellum, brain-stem, other, unknown

    Why tkRAS by default
    --------------------
    The aparc+aseg.mgz volume lives in FreeSurfer's conformed space and exposes
    two voxel→world transforms via its header:
        - get_vox2ras()       — conformed scanner RAS
        - get_vox2ras_tkr()   — tkRAS (origin at FOV centre, used by surfaces)

    The pipeline converts electrodes to tkRAS for surface snapping (in main.py)
    and stores the result in `centroid_mm`. Using tkRAS here keeps a single
    coordinate frame end-to-end and avoids depending on whether the upstream
    `centroid_scanner_mm` field was populated.
    """
    aseg_img  = nib.load(str(aseg_path))
    aseg_data = aseg_img.get_fdata()
    if frame == "tkr":
        vox2world = aseg_img.header.get_vox2ras_tkr()
    elif frame == "scanner":
        vox2world = aseg_img.affine
    else:
        raise ValueError(f"frame must be 'tkr' or 'scanner', got {frame!r}")
    inv_aff = np.linalg.inv(vox2world)
    shape   = np.array(aseg_data.shape)

    out: list[dict] = []
    for elec in electrodes:
        coord = elec.get(coord_key)
        if coord is None:
            out.append({**elec, "aseg_code": 0, "aseg_label": "Unknown",
                        "aseg_group": "unknown"})
            continue
        vox = inv_aff @ np.append(np.asarray(coord, float), 1.0)
        vox_int = np.clip(np.round(vox[:3]).astype(int), 0, shape - 1)
        code = int(aseg_data[tuple(vox_int)])
        # Fall back to the nearest labelled voxel within search_radius if the
        # centroid landed on a code-0 boundary voxel.
        if code == 0 and search_radius > 0:
            code = _find_nearest_labeled_voxel(aseg_data, vox_int, search_radius)
        out.append({
            **elec,
            "aseg_code":  code,
            "aseg_label": _aseg_code_to_name(code),
            "aseg_group": _aseg_group(code),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Task 3.3 – Validation
# ──────────────────────────────────────────────────────────────────────────────

def compute_euclidean_error(
    predicted: list[dict],
    ground_truth: list[dict],
    pred_key: str = "corrected_mm",
    gt_key: str = "gt_mm",
) -> dict:
    """
    Compare predicted electrode positions against ground truth via
    nearest-neighbour matching.  Each GT contact is independently matched
    to the closest predicted electrode, so the lists need not have the
    same length.

    Note: pred_key and gt_key coordinates must be in the same space.
    Clinical precision target: mean error < 2.0 mm.

    Returns:
        {mean_error_mm, max_error_mm, per_electrode}
    """
    pred_coords = np.array([p[pred_key] for p in predicted])   # (N, 3)
    errors = []
    for gt in ground_truth:
        gt_coord = np.asarray(gt[gt_key])
        dists = np.linalg.norm(pred_coords - gt_coord, axis=1)
        nearest_idx = int(np.argmin(dists))
        dist = float(dists[nearest_idx])
        errors.append({
            "id": gt["id"],
            "error_mm": dist,
            "matched_pred_id": predicted[nearest_idx]["id"],
        })
        print(f"  GT {gt['id']} → pred E{predicted[nearest_idx]['id']}: {dist:.3f} mm")

    mean_err = float(np.mean([e["error_mm"] for e in errors]))
    max_err  = float(np.max([e["error_mm"] for e in errors]))
    print(f"\nMean Euclidean Error : {mean_err:.3f} mm  (target < 2.0 mm)")
    print(f"Max  Euclidean Error : {max_err:.3f} mm")

    return {"mean_error_mm": mean_err, "max_error_mm": max_err, "per_electrode": errors}


# ──────────────────────────────────────────────────────────────────────────────
# Task 4.2 – Report Export
# ──────────────────────────────────────────────────────────────────────────────

def export_report(electrodes: list[dict], output_path: str) -> pd.DataFrame:
    """
    Export results to CSV or Excel.
    Columns: Electrode_ID, X_mm, Y_mm, Z_mm, Brodmann_Area, Anatomy_Label, Shift_Correction_mm
    """
    rows = []
    for e in electrodes:
        coord = e.get("corrected_mm", e.get("centroid_mm", np.zeros(3)))
        rows.append({
            "Electrode_ID":        e["id"],
            "X_mm":                round(float(coord[0]), 3),
            "Y_mm":                round(float(coord[1]), 3),
            "Z_mm":                round(float(coord[2]), 3),
            "Brodmann_Area":       e.get("brodmann_area", "N/A"),
            "Anatomy_Label":       e.get("anatomy_label", "N/A"),
            "Shift_Correction_mm": round(e.get("shift_mm", 0.0), 3),
        })

    df = pd.DataFrame(rows)

    if output_path.endswith(".xlsx"):
        df.to_excel(output_path, index=False)
    else:
        df.to_csv(output_path, index=False)

    print(f"Report saved: {output_path}")
    return df
