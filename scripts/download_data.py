"""Download and prepare the MNE sample sEEG dataset (MRI + CT)."""

import shutil
import nibabel as nib
import mne
from pathlib import Path

misc_path = mne.datasets.misc.data_path()
src = Path(misc_path) / "seeg"
dst = Path("data/raw/mne_seeg_sample")
dst.mkdir(parents=True, exist_ok=True)

for f in src.iterdir():
    target = dst / f.name
    if f.is_dir():
        shutil.copytree(f, target, dirs_exist_ok=True)
    else:
        shutil.copy2(f, target)
    print(f"  Copied: {f.name}")

print("Converting .mgz to .nii.gz ...")
conversions = [
    (dst / "sample_seeg" / "mri" / "T1.mgz", dst / "T1.nii.gz"),
    (dst / "sample_seeg_CT.mgz",              dst / "CT.nii.gz"),
]
for src_mgz, out in conversions:
    nib.save(nib.load(str(src_mgz)), str(out))
    print(f"  {src_mgz.name} -> {out.name}")

print("\nDataset ready.")
print("  MRI : data/raw/mne_seeg_sample/T1.nii.gz")
print("  CT  : data/raw/mne_seeg_sample/CT.nii.gz")
