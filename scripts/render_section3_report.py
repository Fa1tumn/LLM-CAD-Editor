"""Render grammar.md §3 from the real FreeCAD kernel as a visual HTML report."""

from __future__ import annotations

import html
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dsl.compiler import compile_program  # noqa: E402
from dsl.parser import parse  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "artifacts" / "section3_visual"
BASE = """sk1 = sketch(plane=XY, circle=[center=origin, r=20]);
body = extrude(profile=sk1, length=200);"""
POCKET = BASE + "\nhole1 = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);"
FULL = POCKET + "\nedge1 = fillet(on=body.edge_top, radius=2);"
TEST_COMMAND = [
    sys.executable,
    "-m",
    "pytest",
    "-q",
    "tests/test_kernel_geometry.py::test_section_3_pocket_removes_the_requested_axial_volume",
    "tests/test_kernel_geometry.py::test_section_3_example_runs_through_fillet_on_the_pocketed_body",
]
TEST_CODE = """def test_section_3_geometry():
    pocket = build(POCKET)
    assert pocket.ShapeType == "Solid"
    assert pocket.isValid()
    assert pocket.Volume == approx(pi * 20**2 * 200 - pi * 6**2 * 180)

    fillet = build(FULL)
    assert fillet.ShapeType == "Solid"
    assert fillet.isValid()
    assert len(fillet.Solids) == 1
    assert 0 < fillet.Volume < pocket.Volume"""


def _build(source: str):
    return compile_program(parse(source))


def _render(
    shape,
    path: Path,
    *,
    elev: float = 19,
    azim: float = -55,
    color: tuple[float, float, float] = (0.35, 0.62, 0.88),
) -> None:
    vertices, faces = shape.tessellate(0.18)
    points = np.array([[vertex.x, vertex.y, vertex.z] for vertex in vertices])
    triangles = np.array([[points[index] for index in face] for face in faces])
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1
    light = np.array([0.45, -0.75, 0.5])
    light /= np.linalg.norm(light)
    intensity = np.abs((normals / lengths) @ light)
    colors = np.clip((0.35 + 0.65 * intensity)[:, None] * np.array(color), 0, 1)

    figure = plt.figure(figsize=(5, 5), dpi=180)
    axis = figure.add_subplot(111, projection="3d")
    axis.add_collection3d(Poly3DCollection(triangles, facecolors=colors, edgecolors=colors))
    centre = (points.min(axis=0) + points.max(axis=0)) / 2
    radius = np.max(points.max(axis=0) - points.min(axis=0)) * 0.58
    axis.set_xlim(centre[0] - radius, centre[0] + radius)
    axis.set_ylim(centre[1] - radius, centre[1] + radius)
    axis.set_zlim(centre[2] - radius, centre[2] + radius)
    axis.set_box_aspect((1, 1, 1))
    axis.view_init(elev=elev, azim=azim)
    axis.set_axis_off()
    figure.patch.set_alpha(0)
    figure.savefig(path, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(figure)


def main() -> None:
    # Import order is load-bearing for FreeCAD's extension modules.
    import FreeCAD  # type: ignore
    import Part  # type: ignore

    OUT.mkdir(parents=True, exist_ok=True)
    stages = [("01-extrude", BASE), ("02-pocket", POCKET), ("03-fillet", FULL)]
    rows = []
    for name, source in stages:
        shape = _build(source)
        _render(shape, OUT / f"{name}.png")
        top_detail = shape.common(Part.makeBox(60, 60, 42, FreeCAD.Vector(-30, -30, 168)))
        _render(top_detail, OUT / f"{name}-top.png", elev=35, azim=-55)
        section = shape.common(Part.makeBox(60, 30, 220, FreeCAD.Vector(-30, 0, -10)))
        _render(section, OUT / f"{name}-section.png", elev=12, azim=-62, color=(0.88, 0.52, 0.24))
        shape.exportStl(str(OUT / f"{name}.stl"))
        rows.append((name, shape, source))

    cards = "\n".join(
        f"""<article><h2>{name.replace('-', ' · ')}</h2>
        <div class="views"><figure><img src="{name}.png" alt="{name} full model"><figcaption>Full model</figcaption></figure>
        <figure><img src="{name}-top.png" alt="{name} enlarged top"><figcaption>Top 32 mm enlarged</figcaption></figure>
        <figure><img src="{name}-section.png" alt="{name} longitudinal section"><figcaption>Longitudinal section</figcaption></figure></div>
        <dl><dt>Type</dt><dd>{shape.ShapeType}</dd><dt>Valid</dt><dd>{shape.isValid()}</dd>
        <dt>Solids</dt><dd>{len(shape.Solids)}</dd><dt>Volume</dt><dd>{shape.Volume:.3f} mm³</dd></dl></article>"""
        for name, shape, _ in rows
    )
    source = html.escape(FULL)
    test_run = subprocess.run(TEST_COMMAND, cwd=OUT.parent.parent, capture_output=True, text=True, check=False)
    test_output = html.escape((test_run.stdout + test_run.stderr).strip())
    test_code = html.escape(TEST_CODE)
    test_status = "PASS" if test_run.returncode == 0 else "FAIL"
    test_class = "pass" if test_run.returncode == 0 else "fail"
    report = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width"><title>DSL §3 FreeCAD Visual Test</title>
    <style>
    :root{{--ink:#172033;--muted:#697386;--blue:#1769e0;--paper:#f4f7fb}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui}}
    main{{max-width:1500px;margin:auto;padding:48px 28px}} h1{{font-size:clamp(30px,5vw,56px);margin:0}}
    .status{{display:inline-block;margin:18px 0 30px;padding:8px 14px;border-radius:99px;font-weight:700}}
    .pass{{background:#dff7e9;color:#17633a}} .fail{{background:#ffe1e1;color:#9d2525}}
    .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}} article{{background:white;border-radius:18px;padding:20px;box-shadow:0 8px 28px #1d355710}}
    .views{{display:grid;grid-template-columns:1fr 1fr;gap:8px}} figure{{margin:0;background:#f7f9fc;border-radius:12px;padding:8px}}
    figure:first-child{{grid-column:1/-1}} img{{width:100%;aspect-ratio:1;object-fit:contain}} figcaption{{text-align:center;color:var(--muted);font-size:12px}}
    h2{{font-size:18px}} dl{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:14px 0 0}}
    dt{{color:var(--muted)}} dd{{margin:0;text-align:right;font-family:ui-monospace;font-weight:700}}
    pre{{overflow:auto;background:#172033;color:#dce8ff;padding:22px;border-radius:16px;white-space:pre-wrap}}
    @media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
    </style></head><body><main><h1>DSL §3 → FreeCAD</h1>
    <p>This page runs the real pytest cases and renders the OCCT geometry they verify.</p>
    <div class="status {test_class}">{test_status} · FreeCAD kernel test</div>
    <section class="grid">{cards}</section>
    <h2>Test code</h2><pre>{test_code}</pre>
    <h2>Live pytest output</h2><pre>{test_output}</pre>
    <h2>DSL input</h2><pre>{source}</pre>
    <p>Each stage is also exported as STL for independent inspection in FreeCAD or another CAD viewer.</p>
    </main></body></html>"""
    (OUT / "index.html").write_text(report, encoding="utf-8")
    print(f"wrote visual report to {OUT / 'index.html'}")
    if test_run.returncode != 0:
        raise SystemExit(test_run.returncode)


if __name__ == "__main__":
    main()
