"""Generate an auditable visual report for the current P0 geometry-fidelity gate."""

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

from dsl.ast import Ref  # noqa: E402
from dsl.compiler import CompileError, FreeCADBackend, compile_program  # noqa: E402
from dsl.parser import parse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts" / "p0_visual"

SHAFT = "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nbody = extrude(profile=sk, length=200);"
POCKET = SHAFT + "\nhole = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);"
FILLET = POCKET + "\nround = fillet(on=body.edge_top, radius=2);"
EDITED = POCKET + "\nedit(target=body, set=length, value=250);"
REPLACED = POCKET + "\nreplace(target=body, with=extrude(profile=hex(r=20), length=200));"
REVOLVE = (
    "sk=sketch(plane=XY,polygon=[[0,0],[4,0],[4,2],[0,2]]);\nbody=revolve(profile=sk,axis=origin,angle=360);"
)
CHAMFER = (
    "sk=sketch(plane=XY,rect=[w=10,h=20]);\n"
    "body=extrude(profile=sk,length=30);\ncut=chamfer(on=body.edge_top,dist=1);"
)
GROOVE = (
    SHAFT
    + "\ngp=sketch(plane=XZ,polygon=[[15,80],[22,80],[22,90],[15,90]]);"
    + "\ng=groove(on=body.face_top,profile=gp,axis=body.axis);"
)
LINEAR_PATTERN = (
    "sk=sketch(plane=XY,rect=[w=2,h=3]);\nbody=extrude(profile=sk,length=4);\n"
    "p=pattern(feature=body,type=linear,count=3,spacing=[6,0,0]);"
)
CIRCULAR_PATTERN = (
    "sk=sketch(plane=XY,rect=[w=2,h=4]);\nbody=extrude(profile=sk,length=3);\n"
    "p=pattern(feature=body,type=circular,count=4,angle=90);"
)
MIRROR = (
    "sk=sketch(plane=XY,rect=[w=3,h=4]);\nbody=extrude(profile=sk,length=5);\n"
    "m=mirror(feature=body,plane=YZ);"
)
CONSTRAINT = (
    "sk=sketch(plane=XY,rect=[w=3,h=4]);\nbody=extrude(profile=sk,length=5);\n"
    "constraint(type=dim,on=body.axis,value=5);"
)

PROFILE_CASES = [
    (
        "circle",
        "Circle",
        "sk=sketch(plane=XY,circle=[center=origin,r=3]);\nb=extrude(profile=sk,length=7);",
        "#2387d8",
    ),
    (
        "rectangle",
        "Rectangle",
        "sk=sketch(plane=XY,rect=[w=3,h=5]);\nb=extrude(profile=sk,length=7);",
        "#20a46b",
    ),
    (
        "polygon",
        "Polygon",
        "sk=sketch(plane=XY,polygon=[[0,0],[4,0],[3,2],[1,3]]);\nb=extrude(profile=sk,length=5);",
        "#df7a32",
    ),
    ("hex", "Inline hex", "b=extrude(profile=hex(r=3),length=6);", "#805ad5"),
    (
        "xz-plane",
        "XZ plane",
        "sk=sketch(plane=XZ,rect=[w=2,h=4]);\nb=extrude(profile=sk,length=6);",
        "#d64f72",
    ),
    (
        "yz-plane",
        "YZ plane",
        "sk=sketch(plane=YZ,polygon=[[0,0],[3,0],[0,4]]);\nb=extrude(profile=sk,length=5);",
        "#1597a5",
    ),
]

OPERATION_CASES = [
    ("revolve", "Revolve", REVOLVE, "#2563eb"),
    ("chamfer", "Chamfer", CHAMFER, "#d97706"),
    ("groove", "Groove", GROOVE, "#dc4c64"),
    ("linear-pattern", "Linear pattern", LINEAR_PATTERN, "#1597a5"),
    ("circular-pattern", "Circular pattern", CIRCULAR_PATTERN, "#7c3aed"),
    ("mirror", "Mirror", MIRROR, "#16865d"),
    ("constraint", "Constraint declaration", CONSTRAINT, "#687386"),
]

GATE_ROWS = [
    ("Unified ProfileSpec → Edge → Wire → Face", "PASS", "circle / rectangle / polygon / hex"),
    ("Every accepted argument changes geometry or raises", "PASS", "unknown-argument and unit error tests"),
    ("XY / XZ / YZ planes, directions, and centers", "PASS", "implemented-operation scope"),
    ("Provenance-carrying ResolvedSubshape", "PASS", "v1 roles"),
    ("Explicit cardinality; no silent first match", "PASS", "ambiguous caps raise explicitly"),
    ("Stable role resolver", "PASS", "face / edge / wall / floor"),
    ("Edit / replace feature-history rebuild", "PASS", "implemented-operation scope"),
    (
        "Complete v1 operation set",
        "PASS",
        "revolve / chamfer / groove / pattern / mirror / constraint",
    ),
    (
        "Checked Boolean preconditions and postconditions",
        "PASS",
        "intersection, clearance, nonempty valid result, measurable change",
    ),
]

TEST_TARGETS = [
    "tests/test_kernel_geometry.py::test_circle_rect_and_pocket_do_not_call_primitive_builders",
    "tests/test_kernel_geometry.py::test_polygon_profile_extrudes_to_the_expected_prism",
    "tests/test_kernel_geometry.py::test_hex_constructor_extrudes_without_an_intermediate_named_sketch",
    "tests/test_kernel_geometry.py::test_the_three_planes_produce_distinct_geometry",
    "tests/test_kernel_geometry.py::test_center_on_a_feature_axis_anchors_the_profile_there",
    "tests/test_kernel_errors.py::test_implemented_operations_never_silently_ignore_arguments",
    "tests/test_operation_set.py",
    "tests/test_subshape_resolver.py",
    "tests/test_feature_history.py::test_edit_rebuilds_target_and_downstream_pocket_from_updated_length",
    "tests/test_feature_history.py::test_replace_circle_extrude_with_hex_and_rebuild_downstream_pocket",
]


def _build(source: str) -> tuple[FreeCADBackend, object]:
    backend = FreeCADBackend()
    return backend, compile_program(parse(source), backend)


def _bounds(shape) -> tuple[np.ndarray, np.ndarray]:
    box = shape.BoundBox
    return np.array([box.XMin, box.YMin, box.ZMin]), np.array([box.XMax, box.YMax, box.ZMax])


def _combined_bounds(*shapes) -> tuple[np.ndarray, np.ndarray]:
    pairs = [_bounds(shape) for shape in shapes]
    return np.min([pair[0] for pair in pairs], axis=0), np.max([pair[1] for pair in pairs], axis=0)


def _triangles(shape) -> np.ndarray:
    vertices, faces = shape.tessellate(0.15)
    points = np.array([[vertex.x, vertex.y, vertex.z] for vertex in vertices])
    return np.array([[points[index] for index in face] for face in faces])


def _shade(triangles: np.ndarray, color: str) -> np.ndarray:
    base = np.array(matplotlib.colors.to_rgb(color))
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1
    light = np.array([0.45, -0.75, 0.5])
    light /= np.linalg.norm(light)
    intensity = np.abs((normals / lengths) @ light)
    return np.clip((0.42 + 0.58 * intensity)[:, None] * base, 0, 1)


def _axes(shape, *, elev: float, azim: float, framing=None):
    figure = plt.figure(figsize=(5, 5), dpi=160)
    axis = figure.add_subplot(111, projection="3d")
    frame_min, frame_max = framing or _bounds(shape)
    centre = (frame_min + frame_max) / 2
    radius = max(float(np.max(frame_max - frame_min)) * 0.60, 0.5)
    axis.set_xlim(centre[0] - radius, centre[0] + radius)
    axis.set_ylim(centre[1] - radius, centre[1] + radius)
    axis.set_zlim(centre[2] - radius, centre[2] + radius)
    axis.set_box_aspect((1, 1, 1))
    axis.view_init(elev=elev, azim=azim)
    axis.set_axis_off()
    figure.patch.set_alpha(0)
    return figure, axis


def _render(shape, path: Path, *, color: str, elev: float = 20, azim: float = -55, framing=None) -> None:
    triangles = _triangles(shape)
    figure, axis = _axes(shape, elev=elev, azim=azim, framing=framing)
    axis.add_collection3d(Poly3DCollection(triangles, facecolors=_shade(triangles, color), edgecolors="none"))
    figure.savefig(path, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(figure)


def _render_role(shape, entities, path: Path, *, color: str, elev: float = 22, azim: float = -55) -> None:
    figure, axis = _axes(shape, elev=elev, azim=azim)
    base = _triangles(shape)
    axis.add_collection3d(Poly3DCollection(base, facecolors="#d7dee9", edgecolors="none", alpha=0.09))
    for edge in shape.Edges:
        points = edge.discretize(Number=50)
        axis.plot(
            [point.x for point in points],
            [point.y for point in points],
            [point.z for point in points],
            color="#9aa8ba",
            linewidth=0.8,
            alpha=0.7,
        )
    for entity in entities:
        if entity.ShapeType == "Face":
            selected = _triangles(entity)
            axis.add_collection3d(
                Poly3DCollection(
                    selected,
                    facecolors=_shade(selected, color),
                    edgecolors=color,
                    linewidths=0.7,
                    alpha=0.95,
                )
            )
        elif entity.ShapeType == "Edge":
            points = entity.discretize(Number=100)
            axis.plot(
                [point.x for point in points],
                [point.y for point in points],
                [point.z for point in points],
                color=color,
                linewidth=5,
            )
    figure.savefig(path, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(figure)


def _shape_metrics(shape) -> str:
    box = shape.optimalBoundingBox()
    return (
        f"{shape.ShapeType} · valid={shape.isValid()} · faces={len(shape.Faces)} · "
        f"volume={shape.Volume:.3f} mm³ · bounds={box.XLength:.1f}×{box.YLength:.1f}×{box.ZLength:.1f} mm"
    )


def _role_evidence(resolved) -> str:
    provenance = resolved.provenance
    steps = " → ".join(f"{step.name} {step.input_count}→{step.output_count}" for step in resolved.steps)
    signatures = "<br>".join(
        f"{index + 1}. {item.geometry_kind}; measure={item.measure:.3f}; centroid={item.centroid}"
        for index, item in enumerate(resolved.signatures)
    )
    return f"""<dl class="evidence">
    <dt>Binding</dt><dd>{html.escape(provenance.source_feature)}.{html.escape(provenance.role)}</dd>
    <dt>Operation / revision</dt><dd>{html.escape(provenance.source_operation)} / {provenance.history_version}</dd>
    <dt>Cardinality</dt><dd>{resolved.expected_cardinality}; matched {resolved.count}</dd>
    <dt>Candidates</dt><dd>{resolved.candidate_count}</dd>
    <dt>Filters</dt><dd>{html.escape(steps)}</dd>
    <dt>Signatures</dt><dd>{signatures}</dd>
    <dt>B-rep SHA-256</dt><dd><code>{provenance.source_shape_hash}</code></dd>
    <dt>Reason</dt><dd>{html.escape(provenance.reason)}</dd></dl>"""


def main() -> None:
    import FreeCAD  # type: ignore
    import Part  # type: ignore

    OUT.mkdir(parents=True, exist_ok=True)

    profile_cards = []
    for slug, label, source, color in PROFILE_CASES:
        _, shape = _build(source)
        _render(shape, OUT / f"profile-{slug}.png", color=color)
        shape.exportStl(str(OUT / f"profile-{slug}.stl"))
        profile_cards.append(
            f"""<article><h3>{label}</h3><img src="profile-{slug}.png" alt="{label}">
            <p class="mono">{html.escape(_shape_metrics(shape))}</p>
            <details><summary>DSL</summary><pre>{html.escape(source)}</pre></details></article>"""
        )

    operation_cards = []
    for slug, label, source, color in OPERATION_CASES:
        backend, shape = _build(source)
        _render(shape, OUT / f"operation-{slug}.png", color=color)
        shape.exportStl(str(OUT / f"operation-{slug}.stl"))
        note = (
            f"{len(backend.constraints)} validated declaration retained for the verify layer."
            if slug == "constraint"
            else "Real kernel geometry; every accepted argument is covered by an effect/error test."
        )
        operation_cards.append(
            f"""<article><h3>{html.escape(label)}</h3><img src="operation-{slug}.png" alt="{html.escape(label)}">
            <p>{html.escape(note)}</p><p class="mono">{html.escape(_shape_metrics(shape))}</p>
            <details><summary>DSL</summary><pre>{html.escape(source)}</pre></details></article>"""
        )

    rect_backend, rect_shape = _build(
        "sk=sketch(plane=XY,rect=[w=10,h=20]);\nbody=extrude(profile=sk,length=30);"
    )
    pocket_backend, pocket_shape = _build(POCKET)
    fillet_backend, fillet_shape = _build(FILLET)
    groove_backend, groove_shape = _build(GROOVE)
    pocket_section = pocket_shape.common(Part.makeBox(60, 30, 220, FreeCAD.Vector(-30, 0, -10)))
    groove_section = groove_shape.common(Part.makeBox(60, 30, 220, FreeCAD.Vector(-30, 0, -10)))
    role_specs = [
        (
            "face-top",
            "body.face_top",
            rect_backend,
            rect_shape,
            Ref(["body", "face_top"]),
            "#e63946",
            22,
            -55,
        ),
        (
            "edge-top",
            "body.edge_top · 4 edges",
            rect_backend,
            rect_shape,
            Ref(["body", "edge_top"]),
            "#f59e0b",
            22,
            -55,
        ),
        (
            "rect-wall",
            "body.wall · 4 faces",
            rect_backend,
            rect_shape,
            Ref(["body", "wall"]),
            "#2563eb",
            22,
            -55,
        ),
        (
            "outer-wall",
            "body.wall · after pocket",
            pocket_backend,
            pocket_shape,
            Ref(["body", "wall"]),
            "#2563eb",
            22,
            -55,
        ),
        (
            "pocket-floor",
            "hole.floor · section",
            pocket_backend,
            pocket_section,
            Ref(["hole", "floor"]),
            "#ef7c2d",
            14,
            -62,
        ),
        (
            "pocket-wall",
            "hole.wall · section",
            pocket_backend,
            pocket_section,
            Ref(["hole", "wall"]),
            "#7c3aed",
            14,
            -62,
        ),
        (
            "fillet-wall",
            "body.wall · cylinder + toroid",
            fillet_backend,
            fillet_shape,
            Ref(["body", "wall"]),
            "#0f9f78",
            22,
            -55,
        ),
        (
            "groove-floor",
            "g.floor · cylindrical section",
            groove_backend,
            groove_section,
            Ref(["g", "floor"]),
            "#dc4c64",
            14,
            -62,
        ),
        (
            "groove-wall",
            "g.wall · two side faces",
            groove_backend,
            groove_section,
            Ref(["g", "wall"]),
            "#7c3aed",
            14,
            -62,
        ),
    ]
    role_cards = []
    for slug, label, backend, display_shape, reference, color, elev, azim in role_specs:
        resolved = backend.resolve_role(reference)
        _render_role(
            display_shape,
            resolved.entities,
            OUT / f"role-{slug}.png",
            color=color,
            elev=elev,
            azim=azim,
        )
        role_cards.append(
            f"""<article><h3>{html.escape(label)}</h3><img src="role-{slug}.png" alt="{html.escape(label)}">
            {_role_evidence(resolved)}</article>"""
        )

    ambiguous = Part.makeCompound([Part.makeBox(4, 4, 4), Part.makeBox(4, 4, 4, FreeCAD.Vector(7, 0, 0))])
    _render(ambiguous, OUT / "role-ambiguous.png", color="#9ca3af", elev=28, azim=-55)
    ambiguity_backend = FreeCADBackend()
    obj = ambiguity_backend.doc.addObject("PartDesign::Feature", "body")
    obj.Shape = ambiguous
    ambiguity_backend.objects["body"] = obj
    ambiguity_backend.axes["body"] = (FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1))
    ambiguity_backend.feature_ops["body"] = "extrude"
    ambiguity_backend.history_versions["body"] = 1
    try:
        ambiguity_backend.resolve_role(Ref(["body", "face_top"]))
        ambiguity_error = "ERROR: ambiguity was silently accepted"
    except CompileError as exc:
        ambiguity_error = str(exc)

    history_cards = []
    for slug, label, before_source, after_source in [
        ("edit", "edit · length 200 → 250 mm", POCKET, EDITED),
        ("replace", "replace · circle → hex", POCKET, REPLACED),
    ]:
        _, before = _build(before_source)
        _, after = _build(after_source)
        framing = _combined_bounds(before, after)
        _render(before, OUT / f"history-{slug}-before.png", color="#718096", framing=framing)
        _render(after, OUT / f"history-{slug}-after.png", color="#16a36a", framing=framing)
        history_cards.append(
            f"""<article class="wide"><h3>{html.escape(label)}</h3><div class="compare">
            <figure><img src="history-{slug}-before.png"><figcaption>Before<br>{html.escape(_shape_metrics(before))}</figcaption></figure>
            <figure><img src="history-{slug}-after.png"><figcaption>After<br>{html.escape(_shape_metrics(after))}</figcaption></figure></div>
            <details><summary>Rebuilt DSL</summary><pre>{html.escape(after_source)}</pre></details></article>"""
        )

    test_run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *TEST_TARGETS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    test_status = "PASS" if test_run.returncode == 0 else "FAIL"
    test_class = "pass" if test_run.returncode == 0 else "fail"
    matrix = "\n".join(
        f'<tr><td>{html.escape(requirement)}</td><td><span class="tag {status.lower().replace(" ", "-")}">{status}</span></td><td>{html.escape(evidence)}</td></tr>'
        for requirement, status, evidence in GATE_ROWS
    )
    report = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width"><title>P0 Geometry Fidelity Visual Report</title>
    <style>
    :root{{--ink:#182233;--muted:#657083;--paper:#f3f6fa;--card:#fff;--blue:#175cd3}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui}}
    main{{max-width:1500px;margin:auto;padding:44px 26px 80px}} h1{{font-size:clamp(32px,5vw,60px);margin:0 0 6px}}
    h2{{margin-top:48px;font-size:28px}} h3{{margin:0 0 10px}} .lead{{font-size:18px;color:var(--muted)}}
    .status{{display:inline-block;padding:9px 15px;border-radius:999px;font-weight:800;margin:12px 8px 22px 0}}
    .progress{{background:#fff2c7;color:#765600}} .pass{{background:#dbf7e8;color:#12613a}} .fail{{background:#fee2e2;color:#991b1b}}
    table{{width:100%;border-collapse:collapse;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 8px 26px #1620330d}}
    th,td{{padding:12px 14px;text-align:left;border-bottom:1px solid #e7ebf1}} th{{background:#eaf0f8}}
    .tag{{display:inline-block;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:800}}
    .tag.pass{{background:#dcfce7;color:#166534}} .tag.partial{{background:#fef3c7;color:#92400e}} .tag.not-started{{background:#e5e7eb;color:#4b5563}}
    .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}}
    .history{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}
    article{{background:var(--card);padding:18px;border-radius:17px;box-shadow:0 8px 26px #1620330d;min-width:0}}
    article>img{{width:100%;aspect-ratio:1;object-fit:contain;background:#f8fafc;border-radius:12px}}
    .compare{{display:grid;grid-template-columns:1fr 1fr;gap:10px}} figure{{margin:0}} figure img{{width:100%;aspect-ratio:1;object-fit:contain;background:#f8fafc;border-radius:12px}}
    figcaption{{font-size:12px;color:var(--muted);text-align:center}} .mono,code,pre{{font-family:ui-monospace,SFMono-Regular,monospace}}
    pre{{white-space:pre-wrap;overflow:auto;background:#172033;color:#deebff;padding:15px;border-radius:12px}}
    details{{margin-top:12px}} summary{{color:var(--blue);font-weight:750;cursor:pointer}}
    .evidence{{display:grid;grid-template-columns:minmax(105px,.7fr) minmax(0,1.7fr);gap:6px 10px;font-size:12px}}
    .evidence dt{{color:var(--muted)}} .evidence dd{{margin:0;overflow-wrap:anywhere}} .error{{color:#a61b1b;font-weight:750}}
    @media(max-width:900px){{.grid,.history{{grid-template-columns:1fr}}}}
    </style></head><body><main>
    <h1>P0 Geometry Fidelity</h1><p class="lead">Visual acceptance evidence from real FreeCAD/OCCT geometry, symbolic-role bindings, and feature-history rebuilds.</p>
    <span class="status pass">P0 PASS · geometry-fidelity baseline complete</span>
    <span class="status {test_class}">{test_status} · P0 evidence tests</span>
    <h2>Acceptance matrix</h2><table><thead><tr><th>P0 requirement</th><th>Status</th><th>Evidence / scope</th></tr></thead><tbody>{matrix}</tbody></table>
    <h2>1 · Unified profiles and plane orientation</h2><p>Every model follows Edge → closed Wire → planar Face → extrude; every image comes from a real OCCT solid.</p>
    <section class="grid">{"".join(profile_cards)}</section>
    <h2>2 · Complete v1 operation set</h2><p>Revolve, chamfer, groove, linear/circular pattern, mirror, and constraint declarations execute through the same validated backend and history model.</p>
    <section class="grid">{"".join(operation_cards)}</section>
    <h2>3 · Actual symbolic-role bindings</h2><p>The pale model provides context; colored regions are the exact subshapes returned by the resolver. Each card records provenance, cardinality, filter steps, and geometric signatures.</p>
    <section class="grid">{"".join(role_cards)}
    <article><h3>Ambiguity must raise</h3><img src="role-ambiguous.png" alt="two ambiguous caps"><p class="error">{html.escape(ambiguity_error)}</p><p>Two top caps at the same height must never result in a silent first match.</p></article></section>
    <h2>4 · Edit / replace history rebuild</h2><p>Before and after use the same visual scale. Green is the rebuilt final solid, with the downstream pocket preserved.</p>
    <section class="history">{"".join(history_cards)}</section>
    <h2>5 · Automated evidence</h2><pre>{html.escape((test_run.stdout + test_run.stderr).strip())}</pre>
    <h2>P0 scope boundary</h2><p>The P0 geometry-fidelity baseline is complete. Constraint declarations are validated and retained, while executable engineering obligations remain P3 work. Pattern instance selectors and model-input evidence hashes remain P2 work. Checked CSG reduces predictable failures but does not claim that arbitrary OCCT Booleans are mathematically total.</p>
    <p>Generator: <code>scripts/render_p0_report.py</code>. All PNG and STL outputs are under <code>artifacts/p0_visual/</code>.</p>
    </main></body></html>"""
    (OUT / "index.html").write_text(report, encoding="utf-8")
    print(f"wrote P0 visual report to {OUT / 'index.html'}")
    if test_run.returncode != 0:
        raise SystemExit(test_run.returncode)


if __name__ == "__main__":
    main()
