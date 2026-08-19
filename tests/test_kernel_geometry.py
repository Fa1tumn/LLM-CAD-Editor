"""Real-kernel geometry regressions for FreeCADBackend (grammar.md §4.1, §7).

Every test here drives an actual OCCT solid through `Part.makeCylinder` /
`Part.makeBox` and asserts concrete geometry — volume, bounding-box extents,
topology counts — rather than merely "it did not raise".
"""

from __future__ import annotations

import math

import pytest

from dsl.compiler import FreeCADBackend, compile_program
from dsl.parser import parse

pytest.importorskip("FreeCAD")

import FreeCAD  # noqa: E402


@pytest.fixture(autouse=True)
def close_freecad_documents():
    """Close every document a test opens, so each backend gets a fresh one.

    `FreeCAD.newDocument("LLMCAD")` does not collide — FreeCAD uniquifies the
    name (LLMCAD, LLMCAD1, ...) — but the documents leak for the whole session,
    so tear them down to keep tests hermetic.
    """
    before = set(FreeCAD.listDocuments())
    yield
    for name in set(FreeCAD.listDocuments()) - before:
        FreeCAD.closeDocument(name)


def build(source: str):
    """Compile `source` on a dedicated FreeCADBackend and return the OCCT shape."""
    return compile_program(parse(source), FreeCADBackend())


# --- circle -> Part.makeCylinder ------------------------------------------------


def test_circle_sketch_extrudes_to_cylinder_solid():
    shape = build(
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nbody = extrude(profile=sk, length=200);"
    )
    assert shape.ShapeType == "Solid"
    assert shape.isValid()
    assert len(shape.Solids) == 1
    # A capped cylinder: lateral face + two planar caps.
    assert len(shape.Faces) == 3
    assert shape.Volume == pytest.approx(math.pi * 20**2 * 200)
    assert shape.Area == pytest.approx(2 * math.pi * 20 * 200 + 2 * math.pi * 20**2)


def test_cylinder_bound_box_is_axis_aligned_on_z_from_origin():
    shape = build(
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nbody = extrude(profile=sk, length=200);"
    )
    box = shape.BoundBox
    # r drives X and Y (diameter), length drives Z, and the base sits on z = 0.
    assert (box.XLength, box.YLength, box.ZLength) == pytest.approx((40.0, 40.0, 200.0))
    assert (box.XMin, box.XMax) == pytest.approx((-20.0, 20.0))
    assert (box.YMin, box.YMax) == pytest.approx((-20.0, 20.0))
    assert (box.ZMin, box.ZMax) == pytest.approx((0.0, 200.0))
    assert shape.CenterOfMass.z == pytest.approx(100.0)


def test_cylinder_radius_and_length_flow_through_independently():
    shape = build("sk = sketch(plane=XY, circle=[center=origin, r=3]);\nb = extrude(profile=sk, length=7);")
    assert shape.Volume == pytest.approx(math.pi * 3**2 * 7)
    assert (shape.BoundBox.XLength, shape.BoundBox.ZLength) == pytest.approx((6.0, 7.0))


# --- rect -> Part.makeBox -------------------------------------------------------


def test_rect_sketch_extrudes_to_box_solid():
    shape = build("sk = sketch(plane=XY, rect=[w=10, h=20]);\nbody = extrude(profile=sk, length=30);")
    assert shape.ShapeType == "Solid"
    assert shape.isValid()
    assert len(shape.Solids) == 1
    assert (len(shape.Faces), len(shape.Edges), len(shape.Vertexes)) == (6, 12, 8)
    assert shape.Volume == pytest.approx(6000.0)
    assert shape.Area == pytest.approx(2 * (10 * 20 + 10 * 30 + 20 * 30))


def test_rect_w_h_length_map_to_x_y_z_with_three_distinct_values():
    shape = build("sk = sketch(plane=XY, rect=[w=3, h=5]);\nb = extrude(profile=sk, length=7);")
    box = shape.BoundBox
    # Distinct values, so a swapped axis mapping cannot pass by coincidence.
    assert (box.XLength, box.YLength, box.ZLength) == pytest.approx((3.0, 5.0, 7.0))
    # makeBox anchors the corner at the global origin.
    assert (box.XMin, box.YMin, box.ZMin) == pytest.approx((0.0, 0.0, 0.0))
    assert shape.CenterOfMass == pytest.approx((1.5, 2.5, 3.5))
    assert shape.Volume == pytest.approx(105.0)


def test_rect_keyword_order_does_not_change_the_solid():
    forward = build("sk = sketch(plane=XY, rect=[w=3, h=5]);\nb = extrude(profile=sk, length=7);")
    reversed_ = build("sk = sketch(plane=XY, rect=[h=5, w=3]);\nb = extrude(profile=sk, length=7);")
    assert reversed_.Volume == pytest.approx(forward.Volume)
    assert (
        reversed_.BoundBox.XLength,
        reversed_.BoundBox.YLength,
        reversed_.BoundBox.ZLength,
    ) == pytest.approx((3.0, 5.0, 7.0))


def test_float_literals_reach_the_kernel_unrounded():
    shape = build("sk = sketch(plane=XY, rect=[w=1.5, h=2.5]);\nb = extrude(profile=sk, length=4.0);")
    assert shape.Volume == pytest.approx(15.0)
    assert (
        shape.BoundBox.XLength,
        shape.BoundBox.YLength,
        shape.BoundBox.ZLength,
    ) == pytest.approx((1.5, 2.5, 4.0))


def test_unit_suffix_is_dropped_and_the_magnitude_is_used_verbatim():
    """`_number` returns Quantity.value and discards `.unit` (compiler.py:84-89)."""
    with_units = build(
        "sk = sketch(plane=XY, circle=[center=origin, r=2 mm]);\nb = extrude(profile=sk, length=10 mm);"
    )
    bare = build("sk = sketch(plane=XY, circle=[center=origin, r=2]);\nb = extrude(profile=sk, length=10);")
    assert with_units.Volume == pytest.approx(math.pi * 2**2 * 10)
    assert with_units.Volume == pytest.approx(bare.Volume)


# --- multi-statement programs ---------------------------------------------------


def test_multi_statement_program_builds_every_solid_and_finish_fuses_them():
    source = (
        "a = sketch(plane=XY, rect=[w=1, h=1]);\n"
        "b = sketch(plane=XY, circle=[center=origin, r=10]);\n"
        "big = extrude(profile=b, length=100);\n"
        "small = extrude(profile=a, length=1);"
    )
    backend = FreeCADBackend()
    shape = compile_program(parse(source), backend)

    # Both extrudes really executed and landed in the document as separate features.
    assert [obj.Name for obj in backend.doc.Objects] == ["big", "small"]
    assert backend.objects["big"].Shape.Volume == pytest.approx(math.pi * 10**2 * 100)
    assert backend.objects["small"].Shape.Volume == pytest.approx(1.0)

    # finish() returns the whole model. The unit cube sits inside the cylinder, so
    # the fusion is the cylinder — notably NOT the sum, which would double-count it.
    assert shape.Volume == pytest.approx(math.pi * 10**2 * 100)


def test_finish_result_is_independent_of_declaration_order():
    """Reversing the declaration order must not change the model that comes back.

    Regression for the defect where `finish()` returned `solids[-1]`, so the same
    two solids yielded whichever one happened to be declared last.
    """
    prefix = "a = sketch(plane=XY, rect=[w=1, h=1]);\nb = sketch(plane=XY, circle=[center=origin, r=10]);\n"
    forward = build(prefix + "small = extrude(profile=a, length=1);\nbig = extrude(profile=b, length=100);")
    reverse = build(prefix + "big = extrude(profile=b, length=100);\nsmall = extrude(profile=a, length=1);")
    assert forward.Volume == pytest.approx(reverse.Volume)
    assert _extents(forward) == pytest.approx(_extents(reverse))


def test_finish_does_not_double_count_overlapping_solids():
    """A boss standing on a base must fuse, not sum — otherwise every IoU metric inflates."""
    shape = build(
        "base = sketch(plane=XY, rect=[w=100, h=100]);\n"
        "b = extrude(profile=base, length=10);\n"
        "sk = sketch(plane=XY, circle=[center=b.axis, r=5]);\n"
        "post = extrude(profile=sk, length=20);"
    )
    overlap = math.pi * 5**2 * 10  # the boss's lower 10 mm sits inside the base
    assert shape.Volume == pytest.approx(100000 + math.pi * 5**2 * 20 - overlap)
    assert shape.Volume != pytest.approx(100000 + math.pi * 5**2 * 20)


def test_finish_keeps_solids_that_do_not_overlap():
    """Fusing must not drop a body just because it is disjoint from the others."""
    shape = build(
        "a = sketch(plane=XY, rect=[w=2, h=2]);\none = extrude(profile=a, length=2);\n"
        "b = sketch(plane=XZ, rect=[w=2, h=2]);\ntwo = extrude(profile=b, length=2);"
    )
    # (0,0,0)-(2,2,2) and (0,-2,0)-(2,0,2): face-to-face, no shared volume.
    assert shape.Volume == pytest.approx(16.0)
    assert _extents(shape) == pytest.approx((0.0, -2.0, 0.0, 2.0, 2.0, 2.0))


def test_unnamed_extrude_statement_still_produces_a_real_solid():
    shape = build("sk = sketch(plane=XY, rect=[w=2, h=3]);\nextrude(profile=sk, length=4);")
    assert shape.ShapeType == "Solid"
    assert shape.Volume == pytest.approx(24.0)
    assert (
        shape.BoundBox.XLength,
        shape.BoundBox.YLength,
        shape.BoundBox.ZLength,
    ) == pytest.approx((2.0, 3.0, 4.0))


def test_circle_wins_over_rect_when_a_sketch_carries_both():
    """compiler.py:101 tests `"circle" in sketch` first, whatever the source order."""
    shape = build(
        "sk = sketch(plane=XY, rect=[w=100, h=100], circle=[center=origin, r=1]);\n"
        "b = extrude(profile=sk, length=1);"
    )
    assert shape.Volume == pytest.approx(math.pi)
    assert len(shape.Faces) == 3  # a cylinder, not a 6-faced box
    assert shape.BoundBox.XLength == pytest.approx(2.0)


def test_zero_radius_cylinder_is_a_degenerate_but_returned_solid():
    """makeCylinder(0, L) does not raise (unlike makeBox with a zero side)."""
    shape = build("sk = sketch(plane=XY, circle=[center=origin, r=0]);\nb = extrude(profile=sk, length=3);")
    assert shape.ShapeType == "Solid"
    assert shape.Volume == pytest.approx(0.0)
    assert not shape.isValid()  # OCCT itself flags the degenerate result


# --- sketch placement: plane, dir and center (issues #3 / #4) -------------------


def _extents(shape):
    b = shape.BoundBox
    return tuple(round(v, 6) for v in (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax))


@pytest.mark.parametrize(
    ("plane", "expected"),
    [
        ("XY", (0.0, 0.0, 0.0, 1.0, 2.0, 3.0)),
        ("XZ", (0.0, -3.0, 0.0, 1.0, 0.0, 2.0)),
        ("YZ", (0.0, 0.0, 0.0, 3.0, 1.0, 2.0)),
    ],
)
def test_sketch_plane_orients_the_solid(plane, expected):
    """`plane` selects the sketch frame; w/h lie in it and the extrusion follows its normal.

    Regression for the defect where `plane` was parsed, stored and then discarded,
    so XY/XZ/YZ all produced the identical solid.
    """
    shape = build(f"sk = sketch(plane={plane}, rect=[w=1, h=2]);\nb = extrude(profile=sk, length=3);")
    assert shape.Volume == pytest.approx(6.0)
    assert _extents(shape) == pytest.approx(expected)


def test_the_three_planes_produce_distinct_geometry():
    """The bug's signature was that all three planes compared equal — pin that they do not."""
    boxes = {
        p: _extents(build(f"sk = sketch(plane={p}, rect=[w=1, h=2]);\nb = extrude(profile=sk, length=3);"))
        for p in ("XY", "XZ", "YZ")
    }
    assert len(set(boxes.values())) == 3, boxes


def test_circle_plane_orients_the_cylinder_axis():
    """A cylinder's axis follows the sketch plane normal, not always +Z."""
    shape = build("sk = sketch(plane=YZ, circle=[center=origin, r=5]);\nb = extrude(profile=sk, length=3);")
    assert shape.Volume == pytest.approx(math.pi * 25 * 3)
    # Extruded along +X, so X spans the length and Y/Z span the diameter.
    assert _extents(shape) == pytest.approx((0.0, -5.0, -5.0, 3.0, 5.0, 5.0))


def test_center_on_a_feature_axis_anchors_the_profile_there():
    """`center=b.axis` must place the profile on b's axis, not at the global origin.

    grammar.md §1.1 makes symbolic anchoring the point of the language; the defect
    compiled `center=b.axis` and `center=origin` to identical geometry.
    """
    base = "base = sketch(plane=XY, rect=[w=100, h=100]);\nb = extrude(profile=base, length=10);\n"

    def boss(center: str):
        """The boss on its own — finish() returns the fused model, so inspect the feature."""
        backend = FreeCADBackend()
        compile_program(
            parse(
                base
                + f"sk = sketch(plane=XY, circle=[center={center}, r=5]);\np = extrude(profile=sk, length=20);"
            ),
            backend,
        )
        return _extents(backend.objects["p"].Shape)

    # b spans (0,0)-(100,100), so its axis is at x=50, y=50.
    assert boss("b.axis") == pytest.approx((45.0, 45.0, 0.0, 55.0, 55.0, 20.0))
    assert boss("origin") == pytest.approx((-5.0, -5.0, 0.0, 5.0, 5.0, 20.0))
    assert boss("b.axis") != boss("origin")


def test_dir_parallel_to_the_plane_normal_is_accepted():
    """`dir` naming the same axis as the plane normal is a no-op, not an error."""
    with_dir = build("sk = sketch(plane=XY, rect=[w=1, h=2]);\nb = extrude(profile=sk, length=3, dir=XY);")
    without = build("sk = sketch(plane=XY, rect=[w=1, h=2]);\nb = extrude(profile=sk, length=3);")
    assert _extents(with_dir) == pytest.approx(_extents(without))


def test_oblique_extrusion_is_rejected_rather_than_silently_ignored():
    """`dir` across the sketch plane cannot be expressed yet, so it must raise.

    The defect silently ignored `dir` entirely, so dir=XZ on an XY sketch produced
    a +Z extrusion with no complaint.
    """
    from dsl.compiler import CompileError

    with pytest.raises(CompileError, match="oblique extrusion is not supported"):
        build("sk = sketch(plane=XY, rect=[w=1, h=2]);\nb = extrude(profile=sk, length=3, dir=XZ);")


def test_unresolvable_anchor_raises_instead_of_defaulting_to_origin():
    """A role the backend cannot resolve yet must fail loudly, not quietly become origin."""
    from dsl.compiler import CompileError

    base = "base = sketch(plane=XY, rect=[w=100, h=100]);\nb = extrude(profile=base, length=10);\n"
    with pytest.raises(CompileError, match="not resolvable yet"):
        build(
            base
            + "sk = sketch(plane=XY, circle=[center=b.face_top, r=5]);\np = extrude(profile=sk, length=20);"
        )


# --- backend reuse across programs (issue #7) -----------------------------------


def test_reused_backend_does_not_return_the_previous_programs_solid():
    """`compile_program` rebuilds the registry each call, so the backend must too.

    Regression for the defect where `self.objects` outlived the call and re-binding
    a name kept its original insertion slot, so a second program returned the first
    program's solid.
    """
    backend = FreeCADBackend()
    first = compile_program(
        parse(
            "a = sketch(plane=XY, rect=[w=1, h=1]);\nb1 = extrude(profile=a, length=1);\n"
            "c = sketch(plane=XY, rect=[w=2, h=2]);\nb2 = extrude(profile=c, length=2);"
        ),
        backend,
    )
    assert first.Volume == pytest.approx(8.0)  # the unit cube is inside the 2-cube

    second = compile_program(
        parse("a = sketch(plane=XY, rect=[w=10, h=10]);\nb1 = extrude(profile=a, length=10);"),
        backend,
    )
    assert second.Volume == pytest.approx(1000.0)


def test_reused_backend_does_not_orphan_superseded_document_objects():
    """The defect left names like ['b1', 'b2', 'b001'] behind in the document."""
    backend = FreeCADBackend()
    compile_program(
        parse(
            "a = sketch(plane=XY, rect=[w=1, h=1]);\nb1 = extrude(profile=a, length=1);\n"
            "c = sketch(plane=XY, rect=[w=2, h=2]);\nb2 = extrude(profile=c, length=2);"
        ),
        backend,
    )
    compile_program(
        parse("a = sketch(plane=XY, rect=[w=10, h=10]);\nb1 = extrude(profile=a, length=10);"),
        backend,
    )
    assert [obj.Name for obj in backend.doc.Objects] == ["b1"]
    assert set(backend.objects) == {"a", "b1"}


def test_reset_clears_state_without_closing_the_document():
    backend = FreeCADBackend()
    compile_program(
        parse("a = sketch(plane=XY, rect=[w=1, h=1]);\nb = extrude(profile=a, length=1);"), backend
    )
    backend.reset()
    assert backend.objects == {}
    assert backend.axes == {}
    assert backend.doc.Objects == []
