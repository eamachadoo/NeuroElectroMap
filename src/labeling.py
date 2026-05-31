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
