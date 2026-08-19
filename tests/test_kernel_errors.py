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
    "circle_extrude": CIRCLE,
    "rect_extrude": RECT,
    "unnamed_extrude": UNNAMED,
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
    "edit": (
        CIRCLE + "\nedit(target=body, set=length, value=250);",
        "FreeCAD parameter edit requires feature-history rebuild",
    ),
    "replace": (
        CIRCLE + "\nreplace(target=body, with=extrude(profile=sk, length=300));",
        "FreeCAD replacement requires feature-history rebuild",
    ),
    "pocket": (
        CIRCLE + "\nh = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);",
        "FreeCAD backend operation not implemented: pocket",
    ),
    "fillet": (
        CIRCLE + "\ne = fillet(on=body.edge_top, radius=2);",
        "FreeCAD backend operation not implemented: fillet",
    ),
    "chamfer_unnamed": (
        CIRCLE + "\nchamfer(on=body.edge_top, dist=1.5);",
        "FreeCAD backend operation not implemented: chamfer",
    ),
    "revolve": (
        "sk = sketch(plane=XY, circle=[center=origin, r=20]);\n"
        "body = revolve(profile=sk, axis=origin, angle=90);",
        "FreeCAD backend operation not implemented: revolve",
    ),
    "groove": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=9);\n"
        "g = groove(on=b.face_top, profile=sk, axis=b.axis);",
        "FreeCAD backend operation not implemented: groove",
    ),
    "pattern": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=9);\n"
        "p = pattern(feature=b, type=circular, count=4, angle=90);",
        "FreeCAD backend operation not implemented: pattern",
    ),
    "mirror": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=9);\n"
        "m = mirror(feature=b, plane=XY);",
        "FreeCAD backend operation not implemented: mirror",
    ),
    "constraint": (
        "sk = sketch(plane=XY, circle=[center=origin, r=2]);\n"
        "b = extrude(profile=sk, length=9);\n"
        "constraint(type=dim, on=b.axis, value=5);",
        "FreeCAD backend operation not implemented: constraint",
    ),
    "polygon_sketch": (
        "sk = sketch(plane=XY, polygon=[[0,0],[1,0],[1,1]]);\nbody = extrude(profile=sk, length=5);",
        "FreeCAD backend currently supports circle/rect sketches",
    ),
    "empty_sketch": (
        "sk = sketch(plane=XY);\nbody = extrude(profile=sk, length=5);",
        "FreeCAD backend currently supports circle/rect sketches",
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
    "profile_is_a_nested_opcall": (
        "b = extrude(profile=hex(r=20), length=5);",
        "extrude profile is not a compiled sketch: OpCall(op='hex', "
        "args={'r': Quantity(value=20.0, unit=None)})",
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
        "backend execution failed: length of box too small",
    ),
    "subtolerance_cylinder": (
        "sk = sketch(plane=XY, circle=[center=origin, r=0.0000000001]);\nb = extrude(profile=sk, length=1);",
        "program produced an invalid solid",
    ),
    "circle_given_as_bare_list": (
        "sk = sketch(plane=XY, circle=[20]);\nb = extrude(profile=sk, length=3);",
        "backend execution failed: 'list' object has no attribute 'get'",
    ),
}


def _expect_compile_error(kernel, source: str, message: str) -> CompileError:
    with pytest.raises(CompileError, match=re.escape(message)) as excinfo:
        compile_program(parse(source), kernel())
    assert not isinstance(excinfo.value, ReferenceError), "CompileError must stay distinct per-layer"
    return excinfo.value


# --------------------------------------------------------------------------------------
# edit / replace: unconditionally rejected by the kernel backend
# --------------------------------------------------------------------------------------


def test_edit_requires_feature_history_rebuild(kernel):
    _expect_compile_error(
        kernel,
        CIRCLE + "\nedit(target=body, set=length, value=250);",
        "FreeCAD parameter edit requires feature-history rebuild",
    )


def test_replace_requires_feature_history_rebuild(kernel):
    _expect_compile_error(
        kernel,
        CIRCLE + "\nreplace(target=body, with=extrude(profile=sk, length=300));",
        "FreeCAD replacement requires feature-history rebuild",
    )


# --------------------------------------------------------------------------------------
# Unimplemented ops (M2 W1 backlog: pocket / fillet / chamfer / pattern / mirror ...)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "pocket",
        "fillet",
        "chamfer_unnamed",
        "revolve",
        "groove",
        "pattern",
        "mirror",
        "constraint",
    ],
)
def test_unimplemented_op_rejected(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    _expect_compile_error(kernel, source, message)


def test_unimplemented_op_message_names_the_op_not_the_auto_name(kernel):
    """An unnamed edit_op statement becomes `__op_<index>`; the message must still cite the op."""
    error = _expect_compile_error(
        kernel,
        CIRCLE + "\nchamfer(on=body.edge_top, dist=1.5);",
        "FreeCAD backend operation not implemented: chamfer",
    )
    assert "__op_" not in str(error)


# --------------------------------------------------------------------------------------
# Unsupported sketch shapes
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["polygon_sketch", "empty_sketch"])
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
        "profile_is_a_nested_opcall",
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
# Errors raised inside OCCT / Python and wrapped by compile_program's blanket handler
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["subtolerance_box"])
def test_occt_error_wrapped_as_compile_error(kernel, case):
    source, message = KERNEL_ONLY_REJECTS[case]
    _expect_compile_error(kernel, source, message)


def test_python_error_wrapped_as_compile_error(kernel):
    """A bare-list `circle=` is legal grammar §3 but blows up inside feature(); it must not escape."""
    source, message = KERNEL_ONLY_REJECTS["circle_given_as_bare_list"]
    error = _expect_compile_error(kernel, source, message)
    assert isinstance(error.__cause__, AttributeError)


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
    milestone teaches the kernel backend a new op (e.g. `pocket`), this test fails and the case
    must move into BOTH_ACCEPT.
    """
    source, message = KERNEL_ONLY_REJECTS[case]
    with pytest.raises(CompileError, match=re.escape(message)):
        compile_program(parse(source), kernel())
    assert isinstance(compile_program(parse(source), SymbolicBackend()), SymbolicModel)
