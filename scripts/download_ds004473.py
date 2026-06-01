"""Download the sub-12 files needed from OpenNeuro ds004473 (via public S3).

Files fetched
-------------
  sub-12/anat/sub-12_T1w.nii.gz           ~6 MB   pre-operative T1w MRI
  sub-12/anat/sub-12_ct.nii.gz            ~50 MB  post-operative CT
  derivatives/freesurfer-7.3.2/sub-12/
      mri/T1.mgz                           ~4 MB   FreeSurfer conformed T1
      mri/transforms/talairach.xfm         <1 MB   tkRAS → MNI transform
      surf/lh.pial                         ~5 MB   left pial surface
      surf/rh.pial                         ~6 MB   right pial surface
      label/lh.BA_exvivo.annot             ~1 MB   left Brodmann annotations
      label/rh.BA_exvivo.annot             ~1 MB   right Brodmann annotations

Total: ~74 MB
"""

import urllib.request
import urllib.parse
import sys
from pathlib import Path

BASE_URL = "https://s3.amazonaws.com/openneuro.org/ds004473"
DEST     = Path("data/raw/ds004473")
FS       = "derivatives/freesurfer-7.3.2/sub-12"

FILES = [
    "sub-12/anat/sub-12_T1w.nii.gz",
    "sub-12/anat/sub-12_ct.nii.gz",
    f"{FS}/mri/T1.mgz",
    f"{FS}/mri/transforms/talairach.xfm",
    f"{FS}/surf/lh.pial",
    f"{FS}/surf/rh.pial",
    f"{FS}/label/lh.BA_exvivo.annot",
    f"{FS}/label/rh.BA_exvivo.annot",
    # Volumetric Desikan-Killiany + ASEG atlas — labels every electrode,
    # including deep / subcortical / white-matter contacts that BA_exvivo misses.
    f"{FS}/mri/aparc+aseg.mgz",
]


def _progress(count, block_size, total_size):
    pct = min(int(count * block_size * 100 / total_size), 100) if total_size > 0 else 0
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(f"\r  [{bar}] {pct:3d}%", end="", flush=True)


def main():
    print("Downloading ds004473 sub-12 from OpenNeuro S3...")
    print(f"Destination: {DEST.resolve()}\n")

    for rel_path in FILES:
        dest_file = DEST / rel_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        if dest_file.exists() and dest_file.stat().st_size > 1000:
            print(f"  ✓  {rel_path}  (already present, skipping)")
            continue

        # Percent-encode the path so chars like '+' (in aparc+aseg.mgz) work.
        url = f"{BASE_URL}/{urllib.parse.quote(rel_path)}"
        print(f"  ↓  {rel_path}")
        try:
            urllib.request.urlretrieve(url, dest_file, reporthook=_progress)
            size_mb = dest_file.stat().st_size / (1024 * 1024)
            print(f"\r  ✓  {rel_path}  ({size_mb:.1f} MB)")
        except Exception as exc:
            print(f"\r  ✗  {rel_path}  FAILED: {exc}", file=sys.stderr)
            sys.exit(1)

    print("\nAll files downloaded.")
    print("\nRun the pipeline with:")
    print("  make run \\")
    print("    MRI=data/raw/ds004473/sub-12/anat/sub-12_T1w.nii.gz \\")
    print("    CT=data/raw/ds004473/sub-12/anat/sub-12_ct.nii.gz \\")
    print("    SUBJECT_DIR=data/raw/ds004473/derivatives/freesurfer-7.3.2/sub-12")


if __name__ == "__main__":
    main()
