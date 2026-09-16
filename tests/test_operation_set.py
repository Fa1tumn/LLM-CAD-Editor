"""Real-kernel acceptance tests for the complete grammar.md §4 operation set (P0)."""

from __future__ import annotations

import math

import pytest

from dsl.ast import Ref
from dsl.compiler import CompileError, FreeCADBackend, compile_program
from dsl.parser import parse

pytest.importorskip("FreeCAD")

import FreeCAD  # noqa: E402


@pytest.fixture(autouse=True)
def close_freecad_documents():
    before = set(FreeCAD.listDocuments())
    yield
    for name in set(FreeCAD.listDocuments()) - before:
        FreeCAD.closeDocument(name)


def _build(source: str, backend: FreeCADBackend | None = None):
    return compile_program(parse(source), backend or FreeCADBackend())


RECT_REVOLVE = (
    "sk=sketch(plane=XY,polygon=[[0,0],[4,0],[4,2],[0,2]]);\nbody=revolve(profile=sk,axis=origin,angle=360);"
)
SHAFT = "sk=sketch(plane=XY,circle=[center=origin,r=20]);\nbody=extrude(profile=sk,length=200);"
GROOVE = (
    SHAFT
    + "\ngp=sketch(plane=XZ,polygon=[[15,80],[22,80],[22,90],[15,90]]);"
    + "\ng=groove(on=body.face_top,profile=gp,axis=body.axis);"
)


def test_revolve_builds_a_capped_solid_and_exposes_axis_roles():
    backend = FreeCADBackend()
    shape = _build(RECT_REVOLVE, backend)

    assert shape.ShapeType == "Solid"
    assert shape.isValid()
    assert shape.Volume == pytest.approx(math.pi * 2**2 * 4)
    assert backend.resolve_role(Ref(["body", "face_top"])).count == 1
    assert backend.resolve_role(Ref(["body", "face_bottom"])).count == 1
    assert backend.resolve_role(Ref(["body", "edge_top"])).count == 1


def test_revolve_angle_changes_the_observed_brep_volume():
    half = _build(RECT_REVOLVE.replace("angle=360", "angle=180"))
    full = _build(RECT_REVOLVE)
    assert half.Volume == pytest.approx(full.Volume / 2)


def test_chamfer_consumes_the_complete_top_outer_wire():
    plain = _build("sk=sketch(plane=XY,rect=[w=10,h=20]);\nbody=extrude(profile=sk,length=30);")
    backend = FreeCADBackend()
    chamfered = _build(
        "sk=sketch(plane=XY,rect=[w=10,h=20]);\n"
        "body=extrude(profile=sk,length=30);\n"
        "cut=chamfer(on=body.edge_top,dist=1);",
        backend,
    )

    assert chamfered.ShapeType == "Solid"
    assert chamfered.isValid()
    assert chamfered.Volume < plain.Volume
    assert backend.history_versions == {"sk": 1, "body": 2, "cut": 1}


def test_groove_removes_the_expected_annular_volume_and_resolves_roles():
    backend = FreeCADBackend()
    shape = _build(GROOVE, backend)
    removed = math.pi * (20**2 - 15**2) * 10

    assert shape.Volume == pytest.approx(math.pi * 20**2 * 200 - removed)
    floor = backend.resolve_role(Ref(["g", "floor"]))
    walls = backend.resolve_role(Ref(["g", "wall"]))
    assert floor.count == 1
    assert floor.signatures[0].geometry_kind == "Part::GeomCylinder"
    assert floor.signatures[0].measure == pytest.approx(2 * math.pi * 15 * 10)
    assert walls.count == 2
    assert {signature.geometry_kind for signature in walls.signatures} == {"Part::GeomPlane"}


def test_linear_pattern_creates_the_requested_number_of_disconnected_instances():
    shape = _build(
        "sk=sketch(plane=XY,rect=[w=2,h=3]);\n"
        "body=extrude(profile=sk,length=4);\n"
        "p=pattern(feature=body,type=linear,count=3,spacing=6);"
    )
    assert shape.isValid()
    assert len(shape.Solids) == 3
    assert shape.Volume == pytest.approx(3 * 2 * 3 * 4)


def test_circular_pattern_uses_count_and_angle_to_add_distinct_geometry():
    source = "sk=sketch(plane=XY,rect=[w=2,h=4]);\nbody=extrude(profile=sk,length=3);"
    plain = _build(source)
    patterned = _build(source + "\np=pattern(feature=body,type=circular,count=4,angle=90);")
    assert patterned.isValid()
    assert patterned.Volume > plain.Volume
    assert patterned.optimalBoundingBox().XLength == pytest.approx(4.0)
    assert patterned.optimalBoundingBox().YLength == pytest.approx(4.0)


def test_pattern_replays_a_pocket_cutter_instead_of_copying_the_whole_body():
    source = (
        "sk=sketch(plane=XY,circle=[center=origin,r=20]);\n"
        "body=extrude(profile=sk,length=30);\n"
        "hole=pocket(on=body.face_top,circle=[center=body.axis,r=3],depth=10);\n"
        "holes=pattern(feature=hole,type=linear,count=2,spacing=[10,0,0]);"
    )
    shape = _build(source)
    assert shape.ShapeType == "Solid"
    assert shape.Volume == pytest.approx(math.pi * 20**2 * 30 - 2 * math.pi * 3**2 * 10)


def test_mirror_fuses_the_original_and_reflected_feature():
    shape = _build(
        "sk=sketch(plane=XY,rect=[w=3,h=4]);\n"
        "body=extrude(profile=sk,length=5);\n"
        "m=mirror(feature=body,plane=YZ);"
    )
    assert shape.ShapeType == "Solid"
    assert shape.Volume == pytest.approx(2 * 3 * 4 * 5)
    assert (shape.BoundBox.XMin, shape.BoundBox.XMax) == pytest.approx((-3.0, 3.0))


def test_constraint_is_validated_and_retained_without_changing_geometry():
    backend = FreeCADBackend()
    source = (
        "sk=sketch(plane=XY,rect=[w=3,h=4]);\n"
        "body=extrude(profile=sk,length=5);\n"
        "constraint(type=dim,on=body.axis,value=5);\n"
        "constraint(type=geom,on=body.axis,value=parallel);"
    )
    shape = _build(source, backend)
    assert shape.Volume == pytest.approx(60.0)
    assert [(item.constraint_type, str(item.target)) for item in backend.constraints] == [
        ("dim", "body.axis"),
        ("geom", "body.axis"),
    ]


def test_edit_rebuilds_new_operations_and_advances_history():
    backend = FreeCADBackend()
    shape = _build(
        "sk=sketch(plane=XY,polygon=[[0,0],[4,0],[4,2],[0,2]]);\n"
        "body=revolve(profile=sk,axis=origin,angle=180);\n"
        "edit(target=body,set=angle,value=360);",
        backend,
    )
    assert shape.Volume == pytest.approx(math.pi * 2**2 * 4)
    assert backend.history_versions == {"sk": 1, "body": 2}


def test_replace_rebuilds_a_downstream_chamfer_against_a_revolved_body():
    backend = FreeCADBackend()
    shape = _build(
        "sk=sketch(plane=XY,polygon=[[0,0],[4,0],[4,2],[0,2]]);\n"
        "body=extrude(profile=sk,length=5);\n"
        "cut=chamfer(on=body.edge_top,dist=0.2);\n"
        "replace(target=body,with=revolve(profile=sk,axis=origin,angle=360));",
        backend,
    )
    assert shape.ShapeType == "Solid"
    assert shape.isValid()
    assert shape.Volume < math.pi * 2**2 * 4
    assert backend.history_versions == {"sk": 1, "body": 3, "cut": 2}


def test_boolean_precondition_rejects_a_nonintersecting_groove():
    source = (
        SHAFT
        + "\ngp=sketch(plane=XZ,polygon=[[30,80],[35,80],[35,90],[30,90]]);"
        + "\ng=groove(on=body.face_top,profile=gp,axis=body.axis);"
    )
    with pytest.raises(CompileError, match="groove cutter does not intersect the target solid"):
        _build(source)


def test_boolean_precondition_rejects_a_groove_that_erases_the_target():
    source = (
        SHAFT
        + "\ngp=sketch(plane=XZ,polygon=[[0,0],[22,0],[22,200],[0,200]]);"
        + "\ng=groove(on=body.face_top,profile=gp,axis=body.axis);"
    )
    with pytest.raises(CompileError, match="groove would remove the entire target solid"):
        _build(source)


def test_pocket_requires_clearance_from_the_target_boundary():
    source = (
        "sk=sketch(plane=XY,circle=[center=origin,r=5]);\n"
        "body=extrude(profile=sk,length=10);\n"
        "hole=pocket(on=body.face_top,circle=[center=body.axis,r=5],depth=5);"
    )
    with pytest.raises(CompileError, match="insufficient clearance"):
        _build(source)


def test_pocket_rejects_through_cut_because_v1_floor_role_must_exist():
    source = (
        "sk=sketch(plane=XY,circle=[center=origin,r=5]);\n"
        "body=extrude(profile=sk,length=10);\n"
        "hole=pocket(on=body.face_top,circle=[center=body.axis,r=2],depth=10);"
    )
    with pytest.raises(CompileError, match="pocket depth must leave a floor"):
        _build(source)


def test_pocket_origin_and_feature_axis_centers_have_distinct_geometry():
    prefix = (
        "guide_sk=sketch(plane=XY,rect=[w=10,h=10]);\n"
        "guide=extrude(profile=guide_sk,length=5);\n"
        "sk=sketch(plane=XY,circle=[center=guide.axis,r=20]);\n"
        "body=extrude(profile=sk,length=30);\n"
    )
    axis_backend = FreeCADBackend()
    _build(
        prefix + "hole=pocket(on=body.face_top,circle=[center=body.axis,r=2],depth=10);",
        axis_backend,
    )
    origin_backend = FreeCADBackend()
    _build(
        prefix + "hole=pocket(on=body.face_top,circle=[center=origin,r=2],depth=10);",
        origin_backend,
    )
    axis_floor = axis_backend.resolve_role(Ref(["hole", "floor"])).require_one().CenterOfMass
    origin_floor = origin_backend.resolve_role(Ref(["hole", "floor"])).require_one().CenterOfMass
    assert (axis_floor.x, axis_floor.y) == pytest.approx((5.0, 5.0))
    assert (origin_floor.x, origin_floor.y) == pytest.approx((0.0, 0.0))


def test_duplicate_pattern_and_mirror_placements_are_explicit_errors():
    circle = "sk=sketch(plane=XY,circle=[center=origin,r=5]);\nbody=extrude(profile=sk,length=10);"
    with pytest.raises(CompileError, match="instances do not add distinct geometry"):
        _build(circle + "\np=pattern(feature=body,type=circular,count=2,angle=90);")
    with pytest.raises(CompileError, match="instances do not add distinct geometry"):
        _build(circle + "\nm=mirror(feature=body,plane=YZ);")


@pytest.mark.parametrize(
    "source",
    [
        RECT_REVOLVE.replace("angle=360", "angle=360,taper=2"),
        "sk=sketch(plane=XY,rect=[w=10,h=20]);\nbody=extrude(profile=sk,length=30);\nc=chamfer(on=body.edge_top,dist=1,mode=equal);",
        GROOVE.replace("axis=body.axis", "axis=body.axis,depth=2"),
        "sk=sketch(plane=XY,rect=[w=2,h=3]);\nbody=extrude(profile=sk,length=4);\np=pattern(feature=body,type=linear,count=2,spacing=6,axis=body.axis);",
        "sk=sketch(plane=XY,rect=[w=2,h=3]);\nbody=extrude(profile=sk,length=4);\nm=mirror(feature=body,plane=YZ,keep=1);",
        "sk=sketch(plane=XY,rect=[w=2,h=3]);\nbody=extrude(profile=sk,length=4);\nconstraint(type=dim,on=body.axis,value=2,tolerance=0.1);",
    ],
)
def test_new_operations_reject_unknown_arguments(source):
    with pytest.raises(CompileError, match="has unsupported arg"):
        _build(source)


def test_new_operation_units_and_domains_are_explicitly_validated():
    with pytest.raises(CompileError, match="revolve angle must use deg"):
        _build(RECT_REVOLVE.replace("angle=360", "angle=360 mm"))
    with pytest.raises(CompileError, match="pattern count must be an integer >= 2"):
        _build(
            "sk=sketch(plane=XY,rect=[w=2,h=3]);\n"
            "body=extrude(profile=sk,length=4);\n"
            "p=pattern(feature=body,type=linear,count=1,spacing=6);"
        )
    with pytest.raises(CompileError, match="dim constraint value must use mm"):
        _build(
            "sk=sketch(plane=XY,rect=[w=2,h=3]);\n"
            "body=extrude(profile=sk,length=4);\n"
            "constraint(type=dim,on=body.axis,value=2 deg);"
        )
