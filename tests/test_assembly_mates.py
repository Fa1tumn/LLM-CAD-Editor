"""Assembly mating checks (proposed grammar.md §9 addendum).

These run with no kernel and no solver: fastener mating is parameter algebra, so every
case here is decided from the declarations alone.
"""

from __future__ import annotations

import pytest

from assembly.mates import (
    AssemblyDeclarationError,
    Interface,
    MateError,
    Thread,
    check_clearance,
    check_grip,
    check_program,
    collect,
)
from dsl.parser import parse

BOLT = (
    't_b = thread(form=M, d=8, pitch=1.25, hand=right, fit="6g");\n'
    "i_b = interface(on=shank.wall, kind=male_thread, thread=t_b, engage=25);"
)
MATE = "m1 = mate(a=i_b, b=i_n, kind=threaded);"


def nut(*, form="M", d=8, pitch=1.25, hand="right", fit="6H", engage=6.5, kind="female_thread") -> str:
    return (
        f't_n = thread(form={form}, d={d}, pitch={pitch}, hand={hand}, fit="{fit}");\n'
        f"i_n = interface(on=bore.wall, kind={kind}, thread=t_n, engage={engage});"
    )


def check(nut_source: str):
    return check_program(parse(f"{BOLT}\n{nut_source}\n{MATE}"))


# --- the syntax already exists ----------------------------------------------------


def test_assembly_statements_parse_under_dsl_v1_without_a_grammar_change():
    """`thread`/`interface`/`mate` are ordinary `name = op(args);` statements (grammar.md §3).

    This is what makes the addendum cheap: no parser change, only new vocabulary and a
    semantic layer. Pinning it here means a future parser edit that broke it would fail.
    """
    prog = parse(f"{BOLT}\n{nut()}\n{MATE}")
    assert [s.op for s in prog.statements] == [
        "thread",
        "interface",
        "thread",
        "interface",
        "mate",
    ]
    interfaces, mates = collect(prog)
    assert set(interfaces) == {"i_b", "i_n"}
    assert len(mates) == 1


# --- a pair that assembles --------------------------------------------------------


def test_matching_bolt_and_nut_pass():
    assert check(nut()) == ["m1"]


def test_engagement_exactly_at_the_minimum_passes():
    """0.8 x d for M8 is 6.4 mm — the boundary must not be excluded."""
    assert check(nut(engage=6.4)) == ["m1"]


def test_a_thread_declaration_may_omit_the_tolerance_class():
    source = (
        "t_b = thread(form=M, d=8, pitch=1.25, hand=right);\n"
        "i_b = interface(on=shank.wall, kind=male_thread, thread=t_b, engage=25);\n"
        "t_n = thread(form=M, d=8, pitch=1.25, hand=right);\n"
        "i_n = interface(on=bore.wall, kind=female_thread, thread=t_n, engage=6.5);\n"
        f"{MATE}"
    )
    assert check_program(parse(source)) == ["m1"]


# --- every way a pair fails to assemble -------------------------------------------


@pytest.mark.parametrize(
    ("case", "message"),
    [
        (dict(d=10), "nominal diameter differs"),
        (dict(pitch=1.0), "pitch differs"),
        (dict(hand="left"), "hand differs"),
        (dict(form="UNC"), "thread form differs"),
        (dict(fit="6g"), "internal thread but carries the external class"),
        (dict(engage=3), "below the 0.8xd minimum"),
        (dict(kind="male_thread"), "needs one male_thread and one female_thread"),
    ],
)
def test_mismatched_pairs_are_rejected_with_a_specific_reason(case, message):
    """Each failure names what is wrong, so the message is usable as repair feedback."""
    with pytest.raises(MateError, match=message):
        check(nut(**case))


def test_an_external_class_on_the_bolt_is_accepted_but_on_the_nut_is_not():
    """A tolerance class only means something on the side it was written for."""
    assert check(nut(fit="6H")) == ["m1"]
    with pytest.raises(MateError, match="internal thread but carries the external class"):
        check(nut(fit="6g"))


def test_the_error_type_is_distinct_from_the_compiler_layer():
    """CLAUDE.md records that the metrics count failures per layer by exception class."""
    from dsl.compiler import CompileError

    with pytest.raises(MateError) as excinfo:
        check(nut(d=10))
    assert not isinstance(excinfo.value, CompileError)


# --- clearance and grip -----------------------------------------------------------


def test_a_hole_smaller_than_the_fastener_is_rejected():
    bolt = Interface(name="bolt", kind="male_thread", thread=Thread("M", 8, 1.25, "right"))
    hole = Interface(name="hole", kind="clearance_hole", d=7.5)
    with pytest.raises(MateError, match="smaller than"):
        check_clearance(bolt, hole)


def test_a_hole_larger_than_the_fastener_passes_without_a_standards_table():
    bolt = Interface(name="bolt", kind="male_thread", thread=Thread("M", 8, 1.25, "right"))
    check_clearance(bolt, Interface(name="hole", kind="clearance_hole", d=9.0))


def test_a_supplied_clearance_table_tightens_the_check():
    """Recommended clearance is standards data the project owns, so it is injected, not baked in."""
    bolt = Interface(name="bolt", kind="male_thread", thread=Thread("M", 8, 1.25, "right"))
    hole = Interface(name="hole", kind="clearance_hole", d=8.2)
    check_clearance(bolt, hole)  # passes on "fits at all" alone
    with pytest.raises(MateError, match="needs at least 9 mm"):
        check_clearance(bolt, hole, clearance={8.0: 9.0})


def test_a_bolt_too_short_for_its_stack_is_rejected():
    check_grip(40, [10, 12], 6.5)  # 28.5 + 1.5 protrusion
    with pytest.raises(MateError, match="bolt length 25 mm is short"):
        check_grip(25, [10, 12], 6.5)


# --- malformed declarations -------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("t = thread(form=Q, d=8, pitch=1.25, hand=right);", "unknown form"),
        ("t = thread(form=M, d=0, pitch=1.25, hand=right);", "d must be positive"),
        ("t = thread(form=M, d=8, pitch=1.25, hand=sideways);", "unknown hand"),
        ("t = thread(form=M, d=8, pitch=1.25, hand=right, fit=6);", "fit must be a quoted"),
        ("thread(form=M, d=8, pitch=1.25, hand=right);", "must be named"),
    ],
)
def test_malformed_declarations_are_rejected(source, message):
    with pytest.raises(AssemblyDeclarationError, match=message):
        collect(parse(source))


def test_a_mate_referring_to_an_undeclared_interface_is_rejected():
    with pytest.raises(AssemblyDeclarationError, match="undeclared interface: i_missing"):
        check_program(parse(f"{BOLT}\nm1 = mate(a=i_b, b=i_missing, kind=threaded);"))


# --- the boundary of what this proves ---------------------------------------------


def test_the_check_believes_the_declaration_not_the_geometry():
    """The known soundness gap, pinned so nobody reads more into a pass than is there.

    Both interfaces below claim M8 and mate cleanly. Nothing here looks at `shank.wall`
    or `bore.wall` to confirm the solid is actually 8 mm — that needs the kernel, and is
    the reason this layer alone cannot certify an assembly.
    """
    source = (
        't_b = thread(form=M, d=8, pitch=1.25, hand=right, fit="6g");\n'
        "i_b = interface(on=nonexistent_part.wall, kind=male_thread, thread=t_b, engage=25);\n"
        't_n = thread(form=M, d=8, pitch=1.25, hand=right, fit="6H");\n'
        "i_n = interface(on=also_nonexistent.wall, kind=female_thread, thread=t_n, engage=6.5);\n"
        f"{MATE}"
    )
    assert check_program(parse(source)) == ["m1"]
