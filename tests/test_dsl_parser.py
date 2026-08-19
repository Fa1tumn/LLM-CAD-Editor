"""
Unit tests for dsl/parser.py against the examples in dsl/grammar.md.

Covers the §3 basic example, the §6 replace/re-binding example, and the
§7 5-step chain (the RQ2 benchmark chain) end to end, plus the
replace/pattern/mirror/constraint validation added in dsl/ast.py.
"""

from __future__ import annotations

import pytest

from dsl.ast import OpCall, Quantity, Ref
from dsl.parser import ParseError, parse, parse_ref


def test_section3_basic_example():
    text = """
    # a shaft with an axial hole
    sk1   = sketch(plane=XY, circle=[center=origin, r=20]);
    body  = extrude(profile=sk1, length=200);
    hole1 = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);
    edge1 = fillet(on=body.edge_top, radius=2);
    """
    prog = parse(text)
    assert [s.name for s in prog.statements] == ["sk1", "body", "hole1", "edge1"]

    sketch_stmt = prog.statements[0]
    assert sketch_stmt.op == "sketch"
    assert sketch_stmt.args["plane"] == Ref(path=["XY"])
    circle = sketch_stmt.args["circle"]
    assert circle["center"] == Ref(path=["origin"])
    assert circle["r"] == Quantity(value=20.0)

    hole_stmt = prog.statements[2]
    assert hole_stmt.args["on"] == Ref(path=["body", "face_top"])
    assert hole_stmt.args["depth"] == Quantity(value=180.0)


def test_section6_replace_rebinding_example():
    text = """
    body = extrude(profile=circle_sk, length=200);
    h    = pocket(on=body.face_top, depth=10);
    replace(target=body, with=extrude(profile=hex_sk, length=200));
    """
    prog = parse(text)
    replace_stmt = prog.statements[-1]
    assert replace_stmt.name is None
    assert replace_stmt.op == "replace"
    assert replace_stmt.args["target"] == Ref(path=["body"])

    with_call = replace_stmt.args["with"]
    assert isinstance(with_call, OpCall)
    assert with_call.op == "extrude"
    assert with_call.args["profile"] == Ref(path=["hex_sk"])


def test_section7_five_step_chain():
    text = """
    # initial
    sk1  = sketch(plane=XY, circle=[center=origin, r=20]);
    body = extrude(profile=sk1, length=200);

    # step1: lengthen  ->  body.length: 200 -> 250
    edit(target=body, set=length, value=250);

    # step2: drill top hole
    h1 = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);

    # step3: pattern the hole
    p1 = pattern(feature=h1, type=circular, count=4, angle=90);

    # step4: cylinder -> hex prism (triggers re-binding)
    replace(target=body, with=extrude(profile=hex(r=20), length=250));

    # step5: chamfer top edge
    chamfer(on=body.edge_top, dist=1.5);
    """
    prog = parse(text)
    assert len(prog.statements) == 7

    edit_stmt = prog.statements[2]
    assert edit_stmt.name is None
    assert edit_stmt.op == "edit"
    assert edit_stmt.args["target"] == Ref(path=["body"])
    assert edit_stmt.args["set"] == Ref(path=["length"])
    assert edit_stmt.args["value"] == Quantity(value=250.0)

    pattern_stmt = prog.statements[4]
    assert pattern_stmt.op == "pattern"
    assert pattern_stmt.args["type"] == Ref(path=["circular"])
    assert pattern_stmt.args["count"] == Quantity(value=4.0)

    replace_stmt = prog.statements[5]
    nested = replace_stmt.args["with"]
    assert isinstance(nested, OpCall)
    assert nested.op == "extrude"
    hex_call = nested.args["profile"]
    assert isinstance(hex_call, OpCall)
    assert hex_call.op == "hex"

    chamfer_stmt = prog.statements[6]
    assert chamfer_stmt.args["on"] == Ref(path=["body", "edge_top"])


@pytest.mark.parametrize(
    "ref_text, expected_path, expected_index",
    [
        ("body.face_top", ["body", "face_top"], None),
        ("pat1[*]", ["pat1"], "*"),
        ("pat1[2]", ["pat1"], 2),
    ],
)
def test_parse_ref(ref_text, expected_path, expected_index):
    ref = parse_ref(ref_text)
    assert ref.path == expected_path
    assert ref.index == expected_index


@pytest.mark.parametrize(
    "bad_statement",
    [
        "replace(target=body);",  # missing `with`
        "replace(target=body, with=hex_sk);",  # `with` must be an op call
        "pattern(feature=h1, type=triangular, count=4);",  # bad pattern type
        "mirror(feature=h1);",  # missing `plane`
        "constraint(type=dim, on=body.length);",  # missing `value`
    ],
)
def test_new_op_validation_errors(bad_statement):
    with pytest.raises(ParseError):
        parse(bad_statement)


def test_syntax_error_reports_line_number():
    text = "sk1 = sketch(plane=XY\nbody = extrude(profile=sk1, length=200);"
    with pytest.raises(ParseError, match="line 2"):
        parse(text)


def test_quantity_unit_parsing():
    prog = parse("edit(target=body, set=length, value=250 mm);")
    assert prog.statements[0].args["value"] == Quantity(value=250.0, unit="mm")
