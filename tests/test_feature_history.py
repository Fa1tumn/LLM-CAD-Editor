"""Transactional FreeCAD feature-history rebuild tests for edit/replace (grammar.md §4/§6)."""

from __future__ import annotations

import math

import pytest

from dsl.ast import Quantity, Ref
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


SHAFT = "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nbody = extrude(profile=sk, length=200);"
POCKET = SHAFT + "\nhole = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);"


def test_edit_rebuilds_target_and_downstream_pocket_from_updated_length():
    backend = FreeCADBackend()
    shape = compile_program(
        parse(POCKET + "\nedit(target=body, set=length, value=250);"),
        backend,
    )

    assert shape.isValid()
    assert shape.Volume == pytest.approx(math.pi * 20**2 * 250 - math.pi * 6**2 * 180)
    assert shape.optimalBoundingBox().ZLength == pytest.approx(250.0)
    assert [record.name for record in backend.feature_history] == ["sk", "body", "hole"]
    assert backend.feature_history[1].args["length"] == Quantity(250.0)
    assert backend.history_versions == {"sk": 1, "body": 3, "hole": 2}
    assert [obj.Name for obj in backend.doc.Objects] == ["body", "hole"]


def test_editing_pocket_depth_rebuilds_only_the_authored_history_result():
    backend = FreeCADBackend()
    shape = compile_program(
        parse(POCKET + "\nedit(target=hole, set=depth, value=100);"),
        backend,
    )

    assert shape.Volume == pytest.approx(math.pi * 20**2 * 200 - math.pi * 6**2 * 100)
    assert backend.feature_history[2].args["depth"] == Quantity(100.0)
    floor = backend.resolve_role(Ref(["hole", "floor"]))
    assert floor.require_one().CenterOfMass.z == pytest.approx(100.0)


def test_edit_replays_a_chained_fillet_and_advances_provenance_versions():
    backend = FreeCADBackend()
    shape = compile_program(
        parse(
            POCKET
            + "\nround = fillet(on=body.edge_top, radius=2);"
            + "\nedit(target=body, set=length, value=250);"
        ),
        backend,
    )

    assert shape.isValid()
    assert shape.optimalBoundingBox().ZLength == pytest.approx(250.0)
    assert backend.history_versions == {"sk": 1, "body": 4, "hole": 3, "round": 2}
    assert backend.resolve_role(Ref(["body", "wall"])).provenance.history_version == 4
    assert backend.resolve_role(Ref(["hole", "wall"])).provenance.history_version == 3


def test_replace_circle_extrude_with_hex_and_rebuild_downstream_pocket():
    backend = FreeCADBackend()
    shape = compile_program(
        parse(POCKET + "\nreplace(target=body, with=extrude(profile=hex(r=20), length=200));"),
        backend,
    )

    hex_area = 3 * math.sqrt(3) * 20**2 / 2
    assert shape.ShapeType == "Solid"
    assert shape.isValid()
    assert shape.Volume == pytest.approx(hex_area * 200 - math.pi * 6**2 * 180)
    assert backend.feature_history[1].op == "extrude"
    assert backend.feature_history[1].args["profile"].op == "hex"
    assert backend.resolve_role(Ref(["body", "edge_top"])).count == 6
    assert backend.resolve_role(Ref(["hole", "wall"])).count == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            "edit(target=body, set=length, value=-5);",
            "extrude length must be positive, got -5",
        ),
        (
            "replace(target=body, with=revolve(profile=sk, axis=origin, angle=-90));",
            r"revolve angle must be in \(0, 360\], got -90",
        ),
    ],
)
def test_failed_history_mutation_rolls_back_to_the_last_valid_model(mutation, message):
    backend = FreeCADBackend()
    with pytest.raises(CompileError, match=message):
        compile_program(parse(SHAFT + "\n" + mutation), backend)

    restored = backend.finish()
    assert restored.isValid()
    assert restored.Volume == pytest.approx(math.pi * 20**2 * 200)
    assert backend.feature_history[1].op == "extrude"
    assert backend.feature_history[1].args["length"] == Quantity(200.0)
    assert [obj.Name for obj in backend.doc.Objects] == ["body"]


def test_replacement_cannot_introduce_a_forward_history_dependency():
    backend = FreeCADBackend()
    source = (
        SHAFT
        + "\nlater = sketch(plane=XY, rect=[w=2, h=3]);"
        + "\nreplace(target=body, with=extrude(profile=later, length=5));"
    )
    with pytest.raises(CompileError, match="extrude profile is not a compiled sketch: later"):
        compile_program(parse(source), backend)

    restored = backend.finish()
    assert restored.Volume == pytest.approx(math.pi * 20**2 * 200)
    assert [record.name for record in backend.feature_history] == ["sk", "body", "later"]


def test_edit_of_a_missing_field_is_rejected_without_rebuilding():
    backend = FreeCADBackend()
    with pytest.raises(CompileError, match="edit field does not exist on body: radius"):
        compile_program(parse(SHAFT + "\nedit(target=body, set=radius, value=5);"), backend)

    assert backend.finish().Volume == pytest.approx(math.pi * 20**2 * 200)
    assert backend.history_versions["body"] == 1
