"""Regenerate the project-page figures from DSL source (grammar.md §3, §4.1).

Every figure on the page is the actual solid `dsl/compiler.py` produces, so the
figures stay honest: change the compiler and re-run this, and the page follows.

    .venv/bin/pip install matplotlib          # not a project dependency
    .venv/bin/python research_page/render_figures.py

Requires the FreeCAD-backed venv described in CLAUDE.md — the figures are
tessellated OCCT solids, not mock-ups.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsl.compiler import FreeCADBackend, compile_program  # noqa: E402
from dsl.parser import parse  # noqa: E402

OUT = Path(__file__).resolve().parent / "figures"

STEEL = (0.36, 0.52, 0.78)
COPPER = (0.83, 0.52, 0.32)
GREEN = (0.36, 0.68, 0.52)

# Fixed light direction, so shading is comparable across figures.
LIGHT = np.array([0.45, -0.75, 0.5])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def _triangles(shape, deflection: float = 0.12):
    verts, faces = shape.tessellate(deflection)
    points = np.array([[v.x, v.y, v.z] for v in verts])
    return np.array([[points[i] for i in tri] for tri in faces])


def _shade(tris, base_rgb):
    """Flat shading: face normal against the light, plus ambient."""
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    lambert = np.abs((normals / lengths) @ LIGHT)
    return np.clip((0.42 + 0.58 * lambert)[:, None] * np.array(base_rgb)[None, :], 0, 1)


def _crop_to_content(path: Path, margin: int = 6) -> None:
    """Trim the transparent border mplot3d leaves, so the page controls the spacing."""
    image = Image.open(path)
    box = image.getchannel("A").getbbox()
    if box is None:
        return
    left, top, right, bottom = box
    image.crop(
        (
            max(0, left - margin),
            max(0, top - margin),
            min(image.width, right + margin),
            min(image.height, bottom + margin),
        )
    ).save(path)


def crop_pair_to_union(paths, margin: int = 10) -> None:
    """Crop a compared pair to one shared box, so they stay at a common scale.

    Cropping each to its own content would let the page scale them differently and
    silently break the comparison; cropping to the union keeps one frame and still
    removes the dead space mplot3d leaves around a 3-D axes.
    """
    images = [Image.open(path) for path in paths]
    boxes = [im.getchannel("A").getbbox() for im in images]
    if any(b is None for b in boxes):
        return
    union = (
        max(0, min(b[0] for b in boxes) - margin),
        max(0, min(b[1] for b in boxes) - margin),
        min(images[0].width, max(b[2] for b in boxes) + margin),
        min(images[0].height, max(b[3] for b in boxes) + margin),
    )
    for image, path in zip(images, paths, strict=True):
        image.crop(union).save(path)


def render(
    shapes,
    name,
    *,
    size=(6.2, 5.0),
    elev=24,
    azim=-58,
    colors=None,
    zoom=0.92,
    radius=None,
    tight=True,
):
    """Render shapes into one transparent PNG, so the page can theme around it."""
    colors = colors or [STEEL] * len(shapes)
    fig = plt.figure(figsize=size, dpi=180)
    ax = fig.add_subplot(111, projection="3d")

    all_pts = []
    for shape, rgb in zip(shapes, colors, strict=False):
        tris = _triangles(shape)
        all_pts.append(tris.reshape(-1, 3))
        shaded = _shade(tris, rgb)
        # Edges matched to faces, antialiasing off: coplanar tessellation triangles
        # would otherwise show hairline seams across flat faces.
        ax.add_collection3d(
            Poly3DCollection(tris, facecolors=shaded, edgecolors=shaded, linewidths=0.35, antialiased=False)
        )

    pts = np.vstack(all_pts)
    centre = (pts.max(axis=0) + pts.min(axis=0)) / 2
    # An explicit radius keeps a pair of figures at one scale while each stays centred.
    if radius is None:
        radius = float(np.max(pts.max(axis=0) - pts.min(axis=0))) / 2
    radius = radius / zoom
    for setter, c in ((ax.set_xlim, centre[0]), (ax.set_ylim, centre[1]), (ax.set_zlim, centre[2])):
        setter(c - radius, c + radius)

    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    path = OUT / f"{name}.png"
    # Figures compared side by side must keep one identical canvas: the page scales
    # every image to the same width, so trimming each to its own content would
    # silently rescale them and destroy the comparison.
    if tight:
        fig.savefig(path, transparent=True, bbox_inches="tight", pad_inches=0.02)
        _crop_to_content(path)
    else:
        fig.savefig(path, transparent=True)
    plt.close(fig)
    return path


def build(source: str):
    """Compile DSL text; return the fused model and the per-feature shapes."""
    backend = FreeCADBackend()
    model = compile_program(parse(source), backend)
    parts = {n: o.Shape for n, o in backend.objects.items() if hasattr(o, "Shape")}
    return model, parts


def plate_and_boss(width: int) -> str:
    """The boss is anchored on `plate.axis`, so it tracks the plate instead of a coordinate."""
    return f"""base = sketch(plane=XY, rect=[w={width}, h={width}]);
plate = extrude(profile=base, length=10);
sk = sketch(plane=XY, circle=[center=plate.axis, r=20]);
boss = extrude(profile=sk, length=52);"""


def three_planes(plane_of) -> str:
    return "\n".join(
        f"s{i} = sketch(plane={plane_of(i)}, rect=[w=14, h=14]);\nb{i} = extrude(profile=s{i}, length=70);"
        for i in range(3)
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)

    model, _ = build(plate_and_boss(110))
    render([model], "hero", size=(7.2, 5.4), elev=27, azim=-56, zoom=0.94)
    print(f"hero            volume {model.Volume:10.1f}")

    # §03 — one edit, and geometry anchored on plate.axis follows. Shared radius so
    # the plate visibly grows rather than each figure being auto-fitted to itself.
    pair = []
    for width, name in ((80, "stab-a"), (128, "stab-b")):
        model, parts = build(plate_and_boss(width))
        pair.append(
            render([model], name, size=(5.0, 4.4), elev=38, azim=-55, zoom=0.95, radius=72, tight=False)
        )
        box = parts["boss"].BoundBox
        centre = ((box.XMin + box.XMax) / 2, (box.YMin + box.YMax) / 2)
        print(f"{name:<15} w={width:<4} boss centre ({centre[0]:.0f}, {centre[1]:.0f})")
    crop_pair_to_union(pair)

    # §04 — `plane` is honoured. Before the placement fix every body was built on XY,
    # so the three coincided; passing XY three times reproduces exactly that output.
    planes = ("XY", "XZ", "YZ")
    pair = []
    for source, name in (
        (three_planes(lambda i: planes[i]), "planes"),
        (three_planes(lambda _: "XY"), "planes-before"),
    ):
        _, parts = build(source)
        bodies = [parts[f"b{i}"] for i in range(3)]
        pair.append(
            render(
                bodies,
                name,
                size=(5.0, 4.4),
                elev=22,
                azim=-52,
                colors=[STEEL, COPPER, GREEN],
                zoom=0.80,
                radius=42,
                tight=False,
            )
        )
        extents = " ".join(
            f"({b.BoundBox.XMin:.0f},{b.BoundBox.YMin:.0f},{b.BoundBox.ZMin:.0f})"
            f"-({b.BoundBox.XMax:.0f},{b.BoundBox.YMax:.0f},{b.BoundBox.ZMax:.0f})"
            for b in bodies
        )
        print(f"{name:<15} {extents}")
    crop_pair_to_union(pair)

    print(f"\nwrote {len(list(OUT.glob('*.png')))} figures to {OUT}")


if __name__ == "__main__":
    main()
