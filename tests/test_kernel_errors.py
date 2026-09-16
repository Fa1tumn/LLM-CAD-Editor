"""Error-contract tests for FreeCADBackend, plus SymbolicBackend verdict parity (grammar.md §4.1/§7).

Every case asserts the exception CLASS as well as the message: CLAUDE.md makes
`ParseError` / `ReferenceError` / `CompileError` load-bearing, because the metrics count them
per-layer. `CompileError` (kernel/symbolic execution) and `dsl.registry.ReferenceError`
(reference validation, a `ValueError` subclass, NOT the builtin) must never be collapsed.
"""

from __future__ import annotations

import re

import pytest

from dsl.compiler import CompileError, FreeCADBackend, SymbolicBackend, SymbolicModel, compile_program
from dsl.parser import parse
from dsl.registry import ReferenceError

pytest.importorskip("FreeCAD")


# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------


@pytest.fixture
def kernel():
    """Factory for FreeCADBackend instances, each on its own document, all closed on teardown.

    `FreeCAD.newDocument("LLMCAD")` does NOT collide across tests -- FreeCAD auto-suffixes
    (LLMCAD, LLMCAD1, LLMCAD2...) -- but every FreeCADBackend() otherwise leaks a document for
    the life of the process, so this fixture closes what it created.
    """
    created: list[FreeCADBackend] = []

    def make() -> FreeCADBackend:
        backend = FreeCADBackend()
        created.append(backend)
        return backend

    yield make

    for backend in created:
        backend.FreeCAD.closeDocument(backend.doc.Name)


# --------------------------------------------------------------------------------------
# Shared DSL corpus (every source below was executed against the real kernel)
# --------------------------------------------------------------------------------------

CIRCLE = "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nbody = extrude(profile=sk, length=200);"
RECT = "sk = sketch(plane=XY, rect=[w=10, h=20]);\nbody = extrude(profile=sk, length=30);"
UNNAMED = "sk = sketch(plane=XY, rect=[w=2, h=3]);\nextrude(profile=sk, length=4);"
DEGENERATE_CIRCLE = "sk = sketch(plane=XY, circle=[center=origin, r=0]);\nb = extrude(profile=sk, length=3);"

# Programs both backends ACCEPT.
BOTH_ACCEPT = {
    "chamfer": RECT + "\ncut = chamfer(on=body.edge_top, dist=1);",
    "circle_extrude": CIRCLE,
    "constraint": CIRCLE + "\nconstraint(type=dim, on=body.axis, value=5);",
    "edit_rebuild": CIRCLE + "\nedit(target=body, set=length, value=250);",
    "groove": (
        CIRCLE
        + "\ngp = sketch(plane=XZ, polygon=[[15,80],[22,80],[22,90],[15,90]]);"
        + "\ng = groove(on=body.face_top, profile=gp, axis=body.axis);"
    ),
    "hex_extrude": "body = extrude(profile=hex(r=4), length=5);",
    "mirror": RECT + "\nm = mirror(feature=body, plane=YZ);",
    "pattern": (
        "sk = sketch(plane=XY, rect=[w=2, h=4]);\n"
        "body = extrude(profile=sk, length=3);\n"
        "p = pattern(feature=body, type=circular, count=4, angle=90);"
    ),
    "polygon_extrude": (
        "sk = sketch(plane=XY, polygon=[[0,0],[3,0],[0,4]]);\nbody = extrude(profile=sk, length=5);"
    ),
    "rect_extrude": RECT,
    "replace_rebuild": CIRCLE + "\nreplace(target=body, with=extrude(profile=sk, length=300));",
    "revolve": (
        "sk = sketch(plane=XY, polygon=[[0,0],[4,0],[4,2],[0,2]]);\n"
        "body = revolve(profile=sk, axis=origin, angle=360);"
    ),
    "unnamed_extrude": UNNAMED,
    "section_3": (
        CIRCLE
        + "\nhole1 = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);"
        + "\nedge1 = fillet(on=body.edge_top, radius=2);"
    ),
}

# Programs rejected ABOVE the backend (compile_program dispatch guards + ReferenceRegistry),
# so the verdict, the exception class and the message are all backend-independent.
BACKEND_INDEPENDENT_REJECTS = {
    "edit_set_not_a_ref": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=3);\n"
        "edit(target=b, set=250, value=1);",
        CompileError,
        "edit set must be a bare field name",
    ),
    "edit_target_with_instance_selector": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=3);\n"
        "edit(target=b[0], set=length, value=1);",
        CompileError,
        "edit target must be a whole-feature reference",
    ),
    "edit_target_derived_role": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=3);\n"
        "edit(target=b.axis, set=length, value=1);",
        CompileError,
        "edit target must be a whole-feature reference",
    ),
    # `replace` never reaches compile_program's dispatch guard: ReferenceRegistry.register()
    # screens the target first, so the near-identical wording arrives as a ReferenceError.
    "replace_target_derived_role": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=3);\n"
        "replace(target=b.axis, with=extrude(profile=sk, length=9));",
        ReferenceError,
        "replace target must be a whole-feature reference",
    ),
    "replace_target_with_instance_selector": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=3);\n"
        "replace(target=b[0], with=extrude(profile=sk, length=9));",
        ReferenceError,
        "replace target must be a whole-feature reference",
    ),
    "dangling_profile": (
        "b = extrude(profile=missing, length=3);",
        ReferenceError,
        "dangling reference: missing",
    ),
    "edit_set_not_a_literal_root": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=3);\n"
        "edit(target=b, set=widget, value=1);",
        ReferenceError,
        "dangling reference: widget",
    ),
    "duplicate_feature_name": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "sk = sketch(plane=XY, circle=[center=origin, r=3]);",
        ReferenceError,
        "feature already exists: sk",
    ),
}

# Programs only the KERNEL backend rejects. SymbolicBackend accepts all of them, so it is NOT a
# faithful proxy here -- see test_symbolic_backend_accepts_every_kernel_only_rejection.
KERNEL_ONLY_REJECTS = {
    "empty_sketch": (
        "sk = sketch(plane=XY);\nbody = extrude(profile=sk, length=5);",
        "sketch must define exactly one of circle, rect, or polygon",
    ),
    "symbolic_length": (
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nbody = extrude(profile=sk, length=depth);",
        "expected numeric quantity, got Ref(path=['depth'], index=None)",
    ),
    "missing_length": (
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nbody = extrude(profile=sk);",
        "expected numeric quantity, got None",
    ),
    "missing_circle_radius": (
        "sk = sketch(plane=XY, circle=[center=origin]);\nb = extrude(profile=sk, length=3);",
        "expected numeric quantity, got None",
    ),
    "missing_rect_height": (
        "sk = sketch(plane=XY, rect=[w=5]);\nbody = extrude(profile=sk, length=2);",
        "expected numeric quantity, got None",
    ),
    "string_radius": (
        'sk = sketch(plane=XY, circle=[center=origin, r="20"]);\nbody = extrude(profile=sk, length=3);',
        "expected numeric quantity, got '20'",
    ),
    "profile_is_a_solid": (
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\n"
        "b1 = extrude(profile=sk, length=5);\n"
        "b2 = extrude(profile=b1, length=5);",
        "extrude profile is not a compiled sketch: b1",
    ),
    "profile_absent": (
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\nb = extrude(length=5);",
        "extrude profile is not a compiled sketch: None",
    ),
    "profile_is_a_derived_role": (
        "sk = sketch(plane=XY, circle=[center=origin, r=3]);\n"
        "b = extrude(profile=sk, length=3);\n"
        "c = extrude(profile=b.face_top, length=3);",
        "extrude profile is not a compiled sketch: b.face_top",
    ),
    "profile_is_a_literal_root": (
        "b = extrude(profile=origin, length=5);",
        "extrude profile is not a compiled sketch: origin",
    ),
    "sketch_only": (
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);",
        "program produced no solid",
    ),
    "empty_program": ("", "program produced no solid"),
    "negative_extrude_length": (
        "sk = sketch(plane=XY, rect=[w=2, h=3]);\nbody = extrude(profile=sk, length=-4);",
        "extrude length must be positive, got -4",
    ),
    "zero_rect_width": (
        "sk = sketch(plane=XY, rect=[w=0, h=3]);\nb = extrude(profile=sk, length=3);",
        "rect w must be positive, got 0",
    ),
    "zero_radius_cylinder": (
        DEGENERATE_CIRCLE,
        "circle r must be positive, got 0",
    ),
    "subtolerance_box": (
        "sk = sketch(plane=XY, rect=[w=0.0000000001, h=0.0000000001]);\n"
        "b = extrude(profile=sk, length=0.0000000001);",
        "profile did not produce a valid planar face",
    ),
    "subtolerance_cylinder": (
        "sk = sketch(plane=XY, circle=[center=origin, r=0.0000000001]);\nb = extrude(profile=sk, length=1);",
        "profile did not produce a valid planar face",
    ),
    "circle_given_as_bare_list": (
        "sk = sketch(plane=XY, circle=[20]);\nb = extrude(profile=sk, length=3);",
        "circle must be [center=..., r=...]",
    ),
    "polygon_duplicate_point": (
        "sk = sketch(plane=XY, polygon=[[0,0],[2,0],[2,2],[2,0],[0,2]]);\nb = extrude(profile=sk, length=1);",
        "polygon contains duplicate points",
    ),
    "polygon_self_intersection": (
        "sk = sketch(plane=XY, polygon=[[0,0],[2,2],[0,2],[2,0]]);\nb = extrude(profile=sk, length=1);",
        "polygon is self-intersecting",
    ),
    "polygon_zero_area": (
        "sk = sketch(plane=XY, polygon=[[0,0],[1,0],[2,0]]);\nb = extrude(profile=sk, length=1);",
        "polygon has zero area",
    ),
    "ambiguous_sketch": (
        "sk = sketch(plane=XY, rect=[w=2, h=3], circle=[center=origin, r=1]);\n"
        "b = extrude(profile=sk, length=1);",
        "sketch must define exactly one of circle, rect, or polygon",
    ),
    "unknown_sketch_arg": (
        'sk = sketch(plane=XY, circle=[center=origin, r=1], color="red");\n'
        "b = extrude(profile=sk, length=1);",
        "sketch has unsupported arg(s): color",
    ),
}


def _expect_compile_error(kernel, source: str, message: str) -> CompileError:
    with pytest.raises(CompileError, match=re.escape(message)) as excinfo:
        compile_program(parse(source), kernel())
    assert not isinstance(excinfo.value, ReferenceError), "CompileError must stay distinct per-layer"
    return excinfo.value


# --------------------------------------------------------------------------------------
# Unsupported sketch shapes
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["ambiguous_sketch", "empty_sketch", "unknown_sketch_arg"])
def test_unsupported_sketch_shape_rejected(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    _expect_compile_error(kernel, source, message)


# --------------------------------------------------------------------------------------
# Bad quantities (_number)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "symbolic_length",
        "missing_length",
        "missing_circle_radius",
        "missing_rect_height",
        "string_radius",
    ],
)
def test_non_numeric_quantity_rejected(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    _expect_compile_error(kernel, source, message)


# --------------------------------------------------------------------------------------
# Bad extrude profiles
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "profile_is_a_solid",
        "profile_absent",
        "profile_is_a_derived_role",
        "profile_is_a_literal_root",
    ],
)
def test_bad_extrude_profile_rejected(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    _expect_compile_error(kernel, source, message)


# --------------------------------------------------------------------------------------
# finish(): "program produced no solid"
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["sketch_only", "empty_program"])
def test_program_produced_no_solid(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    _expect_compile_error(kernel, source, message)


# --------------------------------------------------------------------------------------
# Profile-schema and kernel-tolerance errors
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["subtolerance_box"])
def test_subtolerance_profile_error_is_a_compile_error(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    _expect_compile_error(kernel, source, message)


def test_malformed_circle_profile_has_an_explicit_compile_error(kernel):
    """A bare-list `circle=` is grammar-valid but fails the kernel profile schema."""
    source, message = KERNEL_ONLY_REJECTS["circle_given_as_bare_list"]
    error = _expect_compile_error(kernel, source, message)
    assert error.__cause__ is None


@pytest.mark.parametrize(
    "case", ["polygon_duplicate_point", "polygon_self_intersection", "polygon_zero_area"]
)
def test_invalid_polygon_rejected_before_occt(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    error = _expect_compile_error(kernel, source, message)
    assert error.__cause__ is None


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "sk = sketch(plane=XY, circle=[center=origin, r=2, diameter=4]);\n"
            "b = extrude(profile=sk, length=3);",
            "circle has unsupported arg(s): diameter",
        ),
        (
            "sk = sketch(plane=XY, rect=[w=2, h=3, depth=4]);\nb = extrude(profile=sk, length=3);",
            "rect has unsupported arg(s): depth",
        ),
        (
            "b = extrude(profile=hex(r=2, sides=6), length=3);",
            "hex has unsupported arg(s): sides",
        ),
        (
            "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
            "b = extrude(profile=sk, length=3, taper=1);",
            "extrude has unsupported arg(s): taper",
        ),
        (
            CIRCLE + "\nh = pocket(on=body.face_top, circle=[center=body.axis, r=2], depth=3, mode=1);",
            "pocket has unsupported arg(s): mode",
        ),
        (
            CIRCLE + "\nf = fillet(on=body.edge_top, radius=2, transitions=1);",
            "fillet has unsupported arg(s): transitions",
        ),
    ],
)
def test_implemented_operations_never_silently_ignore_arguments(kernel, source, message):
    _expect_compile_error(kernel, source, message)


def test_degenerate_dimensions_are_rejected_symmetrically(kernel):
    """Both profile branches now refuse a degenerate dimension before reaching the kernel.

    `Part.makeCylinder(0, l)` succeeds and returns an INVALID solid while `Part.makeBox(0, ...)`
    raises, so validation used to depend on which profile shape the program happened to use.
    """
    _expect_compile_error(kernel, DEGENERATE_CIRCLE, "circle r must be positive, got 0")
    _expect_compile_error(
        kernel,
        "sk = sketch(plane=XY, rect=[w=0, h=3]);\nb = extrude(profile=sk, length=3);",
        "rect w must be positive, got 0",
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "sk = sketch(plane=XY, circle=[center=origin, r=2 deg]);\nbody = extrude(profile=sk, length=10);",
            "circle r must use mm, got deg",
        ),
        (
            "sk = sketch(plane=XY, circle=[center=origin, r=2]);\nbody = extrude(profile=sk, length=10 deg);",
            "extrude length must use mm, got deg",
        ),
        (
            CIRCLE + "\nh = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180 deg);",
            "pocket depth must use mm, got deg",
        ),
        (CIRCLE + "\nf = fillet(on=body.edge_top, radius=2 deg);", "fillet radius must use mm, got deg"),
        (
            "sk = sketch(plane=XY, polygon=[[0,0],[2 deg,0],[0,2]]);\nbody = extrude(profile=sk, length=1);",
            "polygon point 1 x must use mm, got deg",
        ),
    ],
)
def test_angular_units_are_rejected_for_linear_dimensions(kernel, source, message):
    _expect_compile_error(kernel, source, message)


# --------------------------------------------------------------------------------------
# Layer separation: registry rejections must NOT be reported as CompileError
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "dangling_profile",
        "edit_set_not_a_literal_root",
        "duplicate_feature_name",
        "replace_target_derived_role",
        "replace_target_with_instance_selector",
    ],
)
def test_reference_errors_are_not_compile_errors(kernel, case):
    source, exc_type, message = BACKEND_INDEPENDENT_REJECTS[case]
    assert exc_type is ReferenceError
    with pytest.raises(ReferenceError, match=re.escape(message)) as excinfo:
        compile_program(parse(source), kernel())
    assert not isinstance(excinfo.value, CompileError), "compile_program re-raises ReferenceError unwrapped"


@pytest.mark.parametrize(
    "case",
    ["edit_set_not_a_ref", "edit_target_with_instance_selector", "edit_target_derived_role"],
)
def test_dispatch_guards_raise_compile_error(kernel, case):
    source, exc_type, message = BACKEND_INDEPENDENT_REJECTS[case]
    assert exc_type is CompileError
    _expect_compile_error(kernel, source, message)


def test_edit_and_replace_target_guards_live_in_different_layers(kernel):
    """Same wording, different layer -- and the metrics count the two classes separately.

    `edit(target=b.axis, ...)` falls to compile_program's `_whole_feature` guard (CompileError),
    while `replace(target=b.axis, ...)` is screened earlier by ReferenceRegistry.register
    (ReferenceError). Collapsing the two classes would silently re-bucket the replace case from
    the reference layer into the compile layer.
    """
    edit_source = BACKEND_INDEPENDENT_REJECTS["edit_target_derived_role"][0]
    replace_source = BACKEND_INDEPENDENT_REJECTS["replace_target_derived_role"][0]

    with pytest.raises(CompileError) as edit_exc:
        compile_program(parse(edit_source), kernel())
    with pytest.raises(ReferenceError) as replace_exc:
        compile_program(parse(replace_source), kernel())

    assert str(edit_exc.value) == "edit target must be a whole-feature reference"
    assert str(replace_exc.value) == "replace target must be a whole-feature reference"
    assert not isinstance(edit_exc.value, ReferenceError)
    assert not isinstance(replace_exc.value, CompileError)


# --------------------------------------------------------------------------------------
# FreeCADBackend vs SymbolicBackend verdict parity
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(BOTH_ACCEPT))
def test_both_backends_accept_the_same_programs(kernel, case):
    program_source = BOTH_ACCEPT[case]
    shape = compile_program(parse(program_source), kernel())
    model = compile_program(parse(program_source), SymbolicBackend())
    assert shape.ShapeType == "Solid"
    assert isinstance(model, SymbolicModel)
    assert shape.isValid()


@pytest.mark.parametrize("case", sorted(BACKEND_INDEPENDENT_REJECTS))
def test_both_backends_reject_identically_above_the_backend(kernel, case):
    """Dispatch-guard and registry rejections happen before any backend call: same class, same text."""
    source, exc_type, message = BACKEND_INDEPENDENT_REJECTS[case]
    program = parse(source)

    with pytest.raises(exc_type, match=re.escape(message)) as kernel_exc:
        compile_program(program, kernel())
    with pytest.raises(exc_type, match=re.escape(message)) as symbolic_exc:
        compile_program(parse(source), SymbolicBackend())

    assert type(kernel_exc.value) is type(symbolic_exc.value)
    assert str(kernel_exc.value) == str(symbolic_exc.value)


@pytest.mark.parametrize("case", sorted(KERNEL_ONLY_REJECTS))
def test_symbolic_backend_accepts_every_kernel_only_rejection(kernel, case):
    """SymbolicBackend is NOT a faithful accept/reject proxy below the dispatch layer.

    It has no kernel, so it accepts every program FreeCADBackend rejects inside
    feature()/edit()/replace()/finish(). This test pins the exact divergence set: if a future
        milestone teaches the kernel backend a new op (e.g. `chamfer`), this test fails and the case
    must move into BOTH_ACCEPT.
    """
    source, message = KERNEL_ONLY_REJECTS[case]
    with pytest.raises(CompileError, match=re.escape(message)):
        compile_program(parse(source), kernel())
    assert isinstance(compile_program(parse(source), SymbolicBackend()), SymbolicModel)
