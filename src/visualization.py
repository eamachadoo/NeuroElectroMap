"""Phase 4 – Task 4.1: Visualization

3D rotatable render of the cortical surface mesh with color-coded electrode spheres.
Falls back to matplotlib scatter if pyvista is unavailable.
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Primary: pyvista interactive render
# ──────────────────────────────────────────────────────────────────────────────

def plot_3d_pyvista(
    pial_vertices: np.ndarray,
    pial_faces: np.ndarray,
    electrodes: list[dict],
    coord_key: str = "corrected_mm",
    output_path: str | None = None,
) -> None:
    """
    Render the pial surface mesh with electrode spheres using pyvista.

    Args:
        pial_vertices: (V, 3) surface vertices.
        pial_faces:    (F, 3) triangle face indices.
        electrodes:    List of electrode dicts.
        coord_key:     Which coordinate to plot.
        output_path:   If given, save a screenshot (.png) instead of showing.
    """
    try:
        import pyvista as pv
    except ImportError:
        print("[WARNING] pyvista not installed. Falling back to matplotlib.")
        plot_3d_matplotlib(pial_vertices, electrodes, coord_key, output_path)
        return

    # Build surface mesh
    faces_pv = np.hstack([np.full((len(pial_faces), 1), 3), pial_faces])
    mesh = pv.PolyData(pial_vertices, faces_pv)

    plotter = pv.Plotter(off_screen=output_path is not None)
    plotter.add_mesh(mesh, color="bisque", opacity=0.4, smooth_shading=True)

    # Color electrodes by Brodmann area
    ba_ids = np.array([e.get("brodmann_area", 0) for e in electrodes], dtype=float)
    coords = np.array([e[coord_key] for e in electrodes])

    for i, (elec, coord) in enumerate(zip(electrodes, coords)):
        sphere = pv.Sphere(radius=2.0, center=coord)
        plotter.add_mesh(sphere, color="crimson", label=f"E{elec['id']}")
        plotter.add_point_labels(
            [coord],
            [f"E{elec['id']} BA{elec.get('brodmann_area', '?')}"],
            font_size=8,
            text_color="white",
        )

    plotter.add_legend()
    plotter.set_background("black")
    plotter.add_axes()

    if output_path:
        plotter.screenshot(output_path)
        print(f"3D render saved: {output_path}")
    else:
        plotter.show(title="Electrode Localization")


# ──────────────────────────────────────────────────────────────────────────────
# Fallback: matplotlib 3D scatter
# ──────────────────────────────────────────────────────────────────────────────

def plot_3d_matplotlib(
    pial_vertices: np.ndarray,
    electrodes: list[dict],
    coord_key: str = "corrected_mm",
    output_path: str | None = None,
) -> None:
    """
    Lightweight fallback: 3D scatter plot of pial surface points + electrodes.
    """
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    # Subsample surface for speed
    step = max(1, len(pial_vertices) // 5000)
    surf = pial_vertices[::step]
    ax.scatter(surf[:, 0], surf[:, 1], surf[:, 2],
               c="lightgray", s=0.3, alpha=0.2, label="Pial surface")

    coords = np.array([e[coord_key] for e in electrodes])
    labels = [f"E{e['id']} BA{e.get('brodmann_area', '?')}" for e in electrodes]

    sc = ax.scatter(coords[:, 0], coords[:, 1], coords[:, 2],
                    c="red", s=80, zorder=5, label="Electrodes")

    for coord, lbl in zip(coords, labels):
        ax.text(coord[0], coord[1], coord[2], lbl, fontsize=7)

    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title("Intracranial Electrode Localization")
    ax.legend()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved: {output_path}")
    else:
        plt.show()


# ──────────────────────────────────────────────────────────────────────────────
# Convenience wrapper
# ──────────────────────────────────────────────────────────────────────────────

def plot_electrodes(
    pial_vertices: np.ndarray,
    electrodes: list[dict],
    pial_faces: np.ndarray | None = None,
    coord_key: str = "corrected_mm",
    output_path: str | None = None,
) -> None:
    """
    Auto-select pyvista (interactive) or matplotlib (fallback) render.
    """
    if pial_faces is not None:
        plot_3d_pyvista(pial_vertices, pial_faces, electrodes, coord_key, output_path)
    else:
        plot_3d_matplotlib(pial_vertices, electrodes, coord_key, output_path)
