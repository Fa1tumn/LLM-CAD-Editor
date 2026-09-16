"""Real-kernel contracts for provenance-carrying symbolic subshape roles (P0/P2)."""

from __future__ import annotations

import math

import pytest

from dsl.ast import Ref
from dsl.compiler import CompileError, FreeCADBackend, compile_program
from dsl.parser import parse
from dsl.subshapes import ResolvedSubshape, SubshapeResolutionError

pytest.importorskip("FreeCAD")

import FreeCAD  # noqa: E402
import Part  # noqa: E402


@pytest.fixture(autouse=True)
def close_freecad_documents():
    before = set(FreeCAD.listDocuments())
    yield
    for name in set(FreeCAD.listDocuments()) - before:
        FreeCAD.closeDocument(name)


def _backend(source: str) -> FreeCADBackend:
    backend = FreeCADBackend()
    compile_program(parse(source), backend)
    return backend


def test_face_top_records_provenance_signature_cardinality_and_filter_steps():
    backend = _backend("sk = sketch(plane=XY, rect=[w=10, h=20]);\nbody = extrude(profile=sk, length=30);")
    resolved = backend.resolve_role(Ref(["body", "face_top"]))

    assert isinstance(resolved, ResolvedSubshape)
    assert resolved.topology_kind == "Face"
    assert resolved.expected_cardinality == "one"
    assert resolved.count == 1
    assert resolved.candidate_count == 6
    assert resolved.require_one().ShapeType == "Face"
    assert resolved.signatures[0].geometry_kind == "Part::GeomPlane"
    assert resolved.signatures[0].measure == pytest.approx(200.0)
    assert resolved.signatures[0].orientation == pytest.approx((0.0, 0.0, 1.0))
    assert [step.name for step in resolved.steps] == [
        "planar",
        "outward_normal",
        "axial_extremum",
    ]
    assert resolved.provenance.source_feature == "body"
    assert resolved.provenance.source_operation == "extrude"
    assert resolved.provenance.history_version == 1
    assert len(resolved.provenance.source_shape_hash) == 64
    assert "unique planar cap" in resolved.provenance.reason


def test_top_edge_excludes_hole_rim_and_pocket_roles_keep_distinct_provenance():
    backend = _backend(
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\n"
        "body = extrude(profile=sk, length=200);\n"
        "hole = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);"
    )

    top_edge = backend.resolve_role(Ref(["body", "edge_top"]))
    outer_wall = backend.resolve_role(Ref(["body", "wall"]))
    floor = backend.resolve_role(Ref(["hole", "floor"]))
    pocket_wall = backend.resolve_role(Ref(["hole", "wall"]))

    assert top_edge.count == 1
    assert top_edge.signatures[0].measure == pytest.approx(2 * math.pi * 20)
    assert outer_wall.count == 1
    assert outer_wall.signatures[0].measure == pytest.approx(2 * math.pi * 20 * 200)
    assert floor.require_one().Area == pytest.approx(math.pi * 6**2)
    assert pocket_wall.count == 1
    assert pocket_wall.signatures[0].measure == pytest.approx(2 * math.pi * 6 * 180)
    assert outer_wall.provenance.source_operation == "extrude"
    assert outer_wall.provenance.history_version == 2
    assert pocket_wall.provenance.source_operation == "pocket"
    assert pocket_wall.provenance.history_version == 1


def test_many_cardinality_returns_every_polygon_rim_and_wall_in_stable_order():
    source = "sk = sketch(plane=XY, rect=[w=10, h=20]);\nbody = extrude(profile=sk, length=30);"
    backend = _backend(source)
    first_edges = backend.resolve_role(Ref(["body", "edge_top"]))
    second_edges = backend.resolve_role(Ref(["body", "edge_top"]))
    walls = backend.resolve_role(Ref(["body", "wall"]))

    assert first_edges.expected_cardinality == "many"
    assert first_edges.count == 4
    assert [signature.measure for signature in first_edges.signatures] == pytest.approx(
        [20.0, 10.0, 10.0, 20.0]
    )
    assert first_edges.signatures == second_edges.signatures
    assert walls.expected_cardinality == "many"
    assert walls.count == 4

    rounded = compile_program(parse(source + "\nround = fillet(on=body.edge_top, radius=1);"))
    assert rounded.ShapeType == "Solid"
    assert rounded.isValid()
    assert rounded.Volume < 10 * 20 * 30


@pytest.mark.parametrize(
    ("plane", "expected_normal"),
    [
        ("XY", (0.0, 0.0, 1.0)),
        ("XZ", (0.0, -1.0, 0.0)),
        ("YZ", (1.0, 0.0, 0.0)),
    ],
)
def test_role_resolution_uses_the_feature_axis_on_every_sketch_plane(plane, expected_normal):
    backend = _backend(f"sk = sketch(plane={plane}, rect=[w=2, h=3]);\nbody = extrude(profile=sk, length=4);")
    top = backend.resolve_role(Ref(["body", "face_top"]))
    bottom = backend.resolve_role(Ref(["body", "face_bottom"]))

    assert top.signatures[0].orientation == pytest.approx(expected_normal)
    assert bottom.signatures[0].orientation == pytest.approx(
        tuple(-component for component in expected_normal)
    )


def test_wall_binding_survives_pocket_and_fillet_history_changes():
    backend = _backend(
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\n"
        "body = extrude(profile=sk, length=200);\n"
        "hole = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);\n"
        "round = fillet(on=body.edge_top, radius=2);"
    )

    body_wall = backend.resolve_role(Ref(["body", "wall"]))
    hole_wall = backend.resolve_role(Ref(["hole", "wall"]))

    assert backend.history_versions == {"sk": 1, "body": 3, "hole": 2, "round": 1}
    assert body_wall.provenance.history_version == 3
    assert body_wall.count == 2
    assert {signature.geometry_kind for signature in body_wall.signatures} == {
        "Part::GeomCylinder",
        "Part::GeomToroid",
    }
    assert hole_wall.provenance.history_version == 2
    assert hole_wall.count == 1
    assert hole_wall.signatures[0].geometry_kind == "Part::GeomCylinder"


def test_unique_role_never_silently_chooses_from_ambiguous_caps():
    backend = FreeCADBackend()
    obj = backend.doc.addObject("PartDesign::Feature", "body")
    obj.Shape = Part.makeCompound(
        [
            Part.makeBox(1, 1, 1),
            Part.makeBox(1, 1, 1, FreeCAD.Vector(3, 0, 0)),
        ]
    )
    backend.objects["body"] = obj
    backend.axes["body"] = (FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1))
    backend.feature_ops["body"] = "extrude"
    backend.history_versions["body"] = 1

    with pytest.raises(CompileError, match="body.face_top expected exactly one Face, matched 2") as excinfo:
        backend.resolve_role(Ref(["body", "face_top"]))
    assert isinstance(excinfo.value.__cause__, SubshapeResolutionError)
