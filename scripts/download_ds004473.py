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


def files_for_subject(sub: str) -> list[str]:
    """Return the relative paths the pipeline needs for one subject."""
    fs = f"derivatives/freesurfer-7.3.2/{sub}"
    return [
        f"{sub}/anat/{sub}_T1w.nii.gz",
        f"{sub}/anat/{sub}_ct.nii.gz",
        # Ground-truth electrode positions. The ACPC file is preferred — it
        # lives in the same coordinate frame as T1.mgz (and the pial surface)
        # so the pipeline can use the coordinates directly without a buggy
        # scanner→tkRAS step. The ScanRAS file is kept for compatibility.
        f"{sub}/ieeg/{sub}_space-ACPC_electrodes.tsv",
        f"{sub}/ieeg/{sub}_space-ACPC_coordsystem.json",
        f"{sub}/ieeg/{sub}_space-ScanRAS_electrodes.tsv",
        f"{sub}/ieeg/{sub}_space-ScanRAS_coordsystem.json",
        f"{fs}/mri/T1.mgz",
        f"{fs}/mri/transforms/talairach.xfm",
        f"{fs}/surf/lh.pial",
        f"{fs}/surf/rh.pial",
        f"{fs}/label/lh.BA_exvivo.annot",
        f"{fs}/label/rh.BA_exvivo.annot",
        # Desikan-Killiany + ASEG — labels every electrode, including deep /
        # subcortical / white-matter contacts that BA_exvivo misses.
        f"{fs}/mri/aparc+aseg.mgz",
    ]


# Default subject for the original `python download_ds004473.py` invocation.
# Override with: python download_ds004473.py sub-1 sub-2 ...
DEFAULT_SUBJECTS = ["sub-12"]


def _progress(count, block_size, total_size):
    pct = min(int(count * block_size * 100 / total_size), 100) if total_size > 0 else 0
    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
    print(f"\r  [{bar}] {pct:3d}%", end="", flush=True)


def _download_one(rel_path: str) -> None:
    """Download `rel_path` from OpenNeuro S3 into `DEST/rel_path`.

    The write is **atomic**: bytes go to `<dest>.partial` and are only renamed
    to the final name after the transfer completes. If the transfer is
    interrupted (Ctrl+C, network drop, OOM), the partial file is removed and
    the next invocation will retry — there is no risk of `pipeline corrupted
    data masquerading as a complete download`.
    """
    dest_file = DEST / rel_path
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    # The OpenNeuro dataset ships as git-annex symlinks. If the symlink
    # was never resolved (broken) we need to drop it before writing the
    # downloaded blob — urllib.urlretrieve can't write through a dangling link.
    if dest_file.is_symlink() and not dest_file.exists():
        dest_file.unlink()
    # Same for an empty placeholder left behind by an earlier failed run.
    if dest_file.exists() and dest_file.stat().st_size == 0:
        dest_file.unlink()

    if dest_file.exists() and dest_file.stat().st_size > 1000:
        print(f"  ✓  {rel_path}  (already present, skipping)")
        return

    url = f"{BASE_URL}/{urllib.parse.quote(rel_path)}"
    partial = dest_file.with_name(dest_file.name + ".partial")
    # Always start from a clean slate — leftover .partial from a previous
    # crashed run is meaningless and would only confuse the progress bar.
    if partial.exists():
        partial.unlink()

    print(f"  ↓  {rel_path}")
    try:
        urllib.request.urlretrieve(url, partial, reporthook=_progress)
        # Atomic rename: either the file shows up complete, or not at all.
        partial.replace(dest_file)
        size_mb = dest_file.stat().st_size / (1024 * 1024)
        print(f"\r  ✓  {rel_path}  ({size_mb:.1f} MB)")
    except Exception as exc:
        # Tidy up the half-written file so the user isn't tricked into
        # thinking a partial download is a complete one.
        if partial.exists():
            partial.unlink()
        print(f"\r  ✗  {rel_path}  FAILED: {exc}", file=sys.stderr)
        sys.exit(1)


def main():
    # Subjects can be passed as CLI args (`python download_ds004473.py sub-1 sub-2`).
    # No args → fall back to DEFAULT_SUBJECTS for backwards compatibility.
    subjects = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SUBJECTS
    print(f"Downloading ds004473 {', '.join(subjects)} from OpenNeuro S3...")
    print(f"Destination: {DEST.resolve()}\n")

    for sub in subjects:
        print(f"── {sub} ──")
        for rel_path in files_for_subject(sub):
            _download_one(rel_path)
        print()

    print("All files downloaded.\n")
    print("Run the pipeline with:")
    for sub in subjects:
        print(f"  make run \\")
        print(f"    MRI=data/raw/ds004473/{sub}/anat/{sub}_T1w.nii.gz \\")
        print(f"    CT=data/raw/ds004473/{sub}/anat/{sub}_ct.nii.gz \\")
        print(f"    SUBJECT_DIR=data/raw/ds004473/derivatives/freesurfer-7.3.2/{sub}")


if __name__ == "__main__":
    main()
