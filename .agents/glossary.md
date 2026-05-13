# NeuroElectroMap — Glossary

---

## Affine Matrix
A 4×4 matrix that encodes a linear transformation (rotation, scaling, translation) in homogeneous coordinates. Used throughout the pipeline to convert between coordinate spaces: voxel → scanner RAS, scanner RAS → tkRAS, tkRAS → MNI. Every coordinate transform follows `P_target = M_affine · P_source`.

---

## Atlas
A labelled reference brain volume where every voxel or surface vertex is annotated with an anatomical or functional region name. Used to answer "what brain region is this coordinate in?" Two atlases are used in this project:
- **MNI152** — a standard coordinate space (average of 152 healthy brains) enabling cross-patient comparison.
- **Brodmann Atlas** — divides the cortex into ~52 numbered areas by cytoarchitecture (see *Brodmann Area* and *Brodmann Lookup*).

---

## Brain Masking
A preprocessing step that removes non-brain tissue (skull, scalp, eyes, neck) from an MRI volume by multiplying the image against a binary mask (1 = brain, 0 = non-brain). Implemented via `nilearn.masking.compute_brain_mask`. Improves registration accuracy by restricting the optimisation to brain tissue only.

---

## Brodmann Area (BA)
One of ~52 numbered cortical regions defined by Korbinian Brodmann (1909) based on the microscopic layering patterns of neurons (cytoarchitecture). Brodmann areas correlate strongly with function — e.g. BA4 = Primary Motor Cortex, BA17 = Primary Visual Cortex (V1), BA22 = Wernicke's Area, BA44/45 = Broca's Area.

---

## Brodmann Lookup
The process of querying the Brodmann atlas to assign a functional label to each electrode's coordinate. In this project, implemented via `lookup_brodmann_surface()` using FreeSurfer's `lh/rh.BA_exvivo.annot` surface annotation files — no network access required. Each of the 331,486 pial surface vertices carries a BA label; the nearest vertex to each electrode is used.

---

## Connected Component Analysis (CCA)
An algorithm that groups connected voxels sharing a property (e.g. HU > 3000) into labelled clusters. Used in electrode segmentation to separate individual electrode contacts from each other and from large metal artefacts, by size-filtering clusters (3–500 voxels). Implemented via `scipy.ndimage.label` + `skimage.measure.regionprops`.

---

## CT (Computed Tomography)
An imaging modality that fires X-rays through the body from many angles and reconstructs a 3D volume based on tissue X-ray absorption. Density is measured in Hounsfield Units (HU). CT has excellent contrast for bone and metal but poor contrast for soft brain tissue. In this project, a **post-operative CT** is used to detect implanted electrodes (HU > 3000).

---

## Cytoarchitecture
The microscopic organisation and layering pattern of neurons in a cortical region. The basis for Brodmann's original parcellation of the cortex into numbered areas — regions with distinct cell layering patterns tend to have distinct functions.

---

## ECoG (ElectroCorticoGraphy)
An intracranial recording technique where a flat grid or strip of electrodes is placed **on the cortical surface** (pial surface) via craniotomy (large skull opening). Provides high spatial resolution over one hemisphere surface. Brain-shift correction (snapping centroids to the nearest pial vertex) is designed for ECoG electrodes, as they sit directly on the surface.

---

## Electrode Segmentation
The process of isolating individual electrode contacts from a post-operative CT scan. The pipeline uses two steps: (1) global HU threshold (>3000) to create a binary mask of metal voxels, (2) 3D Connected Component Analysis to label and size-filter individual clusters, extracting each centroid as one electrode contact position.

---

## Fusion (CT + MRI)
The alignment of two images from different modalities into a shared coordinate space, so structures visible in one can be localised against the other. In this project: CT shows electrode positions (metal) while MRI shows brain anatomy (soft tissue). The pipeline uses **rigid-body registration** — 6 degrees of freedom (3 translations + 3 rotations) — optimised via Mutual Information, producing a 4×4 affine matrix that maps any CT coordinate into MRI space.

---

## Hounsfield Unit (HU)
The unit of radiodensity in CT imaging. Air = −1000 HU, water = 0 HU, soft tissue ≈ 20–80 HU, bone ≈ 400–1000 HU, metal implants ≈ 3000+ HU. The electrode detection threshold in this project is HU > 3000.

---

## MNI152
The Montreal Neurological Institute standard brain template, built from an average of 152 healthy adult brains. Defines a standard coordinate space (MNI space) so that coordinates from different patients can be directly compared. The origin sits roughly at the anterior commissure.

---

## MNI Normalisation
The transformation of patient-specific coordinates into the MNI152 standard space, enabling cross-patient and cross-study comparison. This project uses the FreeSurfer **Talairach transform** (a linear 12-parameter affine, stored in `talairach.xfm`) to map from patient tkRAS space to MNI Talairach space. A full nonlinear warp (ANTs, FSL FNIRT) would be more accurate but requires significantly more computation.

---

## MRI (Magnetic Resonance Imaging)
An imaging modality that uses strong magnetic fields and radio waves to measure how hydrogen atoms in water respond. Different tissues have different water content, producing excellent soft-tissue contrast (grey matter, white matter, CSF are clearly distinguishable). Cannot visualise metal well. In this project, a **pre-operative T1-weighted MRI** provides the anatomical reference onto which the post-op CT is registered.

---

## Mutual Information
A metric from information theory measuring the statistical dependency between two variables. Used as the registration objective function: the 4×4 affine transform is optimised to maximise the Mutual Information between MRI and CT intensities. Unlike sum-of-squared differences, Mutual Information works across modalities because it does not require the images to look alike — only that their intensity distributions are statistically related.

---

## NIfTI (Neuroimaging Informatics Technology Initiative)
The standard file format for brain imaging data (`.nii` or `.nii.gz`). Each file stores: (1) a 3D/4D voxel intensity array and (2) a header containing the affine matrix, voxel size, dimensions, and orientation. The affine is what converts a voxel index `(i, j, k)` into a real-world millimetre coordinate.

---

## Pial Surface
The outermost surface of the cortex — the boundary between grey matter and CSF. Represented as a 3D mesh of vertices and triangular faces, extracted from a T1 MRI by FreeSurfer. Used in this project for brain-shift correction (snapping ECoG electrode positions to the nearest surface vertex) and for surface-based Brodmann area lookup.

---

## RAS+ / LPS Orientation
A convention describing which direction the X, Y, Z axes of a brain image point. **RAS+**: X = Right, Y = Anterior, Z = Superior. **LPS**: X = Left, Y = Posterior, Z = Superior. Scanners from different vendors may produce images in different orientations. The pipeline reorients all inputs to RAS+ before processing to prevent mirroring artefacts in registration.

---

## Rigid-Body Registration
A type of image registration that uses only 6 degrees of freedom: 3 translations (X, Y, Z shifts) and 3 rotations (pitch, yaw, roll). No scaling or warping. Appropriate for CT-to-MRI alignment because the skull is a rigid structure — the brain's position relative to the skull does not change meaningfully between the pre-op MRI and post-op CT.

---

## sEEG (Stereo-EEG)
An intracranial recording technique where thin needle electrodes are implanted **deep inside the brain** along stereotactic trajectories via small burr holes. Can reach deep structures inaccessible to ECoG (hippocampus, amygdala, insula). Each shaft carries multiple contacts spaced a few mm apart. In this project, the MNE sample dataset contains sEEG electrodes — brain-shift distances of 30–120 mm are expected because the electrodes are deep inside the brain, far from the pial surface.

---

## Talairach Transform
A linear 12-parameter affine transform (rotation, translation, scaling per axis) that maps a patient's brain from its native space into the Talairach/MNI standard space. Stored by FreeSurfer as `mri/transforms/talairach.xfm`. Less accurate than a nonlinear warp but computationally cheap and standard for electrode localisation workflows.

---

## tkRAS (FreeSurfer Surface RAS)
A coordinate system used internally by FreeSurfer where the origin is placed at the centre of the field of view of the T1 MRI volume. Distinct from **scanner RAS** (where the origin is the MRI scanner isocentre). FreeSurfer pial surface vertices and atlas annotations are in tkRAS. Electrode centroids from NIfTI-based segmentation are in scanner RAS. Converting between them (via `vox2ras_tkr @ inv(vox2ras)`) is required before brain-shift correction — omitting this step causes apparent errors of 50–150 mm.

---

## Voxel
A **vol**umetric pi**xel** — the 3D equivalent of a pixel. In brain imaging, each voxel represents a small cube of tissue (typically 0.4–1.0 mm per side) and stores a single intensity value. Electrode positions are first detected as voxel coordinates `(i, j, k)` and then converted to millimetre world coordinates using the affine matrix.
