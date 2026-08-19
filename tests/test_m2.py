from __future__ import annotations

import pytest

from dsl.ast import Quantity, Ref
from dsl.compiler import SymbolicBackend, compile_program
from dsl.parser import parse
from dsl.registry import ReferenceRegistry
from eval.harness import load_chain, score_chain


def test_symbolic_compile_runs_example_and_applies_edit_replace():
    program = parse("""
    sk = sketch(plane=XY, circle=[center=origin, r=20]);
    body = extrude(profile=sk, length=200);
    edit(target=body, set=length, value=250);
    replace(target=body, with=extrude(profile=sk, length=300));
    """)
    model = compile_program(program, SymbolicBackend())
    assert model.features["body"].op == "extrude"
    assert model.features["body"].args["length"] == Quantity(300.0)
    assert model.operations[-2:] == ["edit:body.length", "replace:body=extrude"]


def test_compile_rejects_dangling_derived_reference():
    program = parse("sk = sketch(plane=XY); h = pocket(on=sk.face_top, depth=2);")
    with pytest.raises(ValueError, match="dangling reference"):
        compile_program(program, SymbolicBackend())


def test_registry_rebind_rewrites_graph_and_ast_refs():
    initial = parse("sk = sketch(plane=XY); body = extrude(profile=sk, length=2);")
    registry = ReferenceRegistry()
    for statement in initial.statements:
        registry.register(statement)
    downstream = parse("h = pocket(on=body.face_top, depth=1);").statements
    registry.register(downstream[0])
    registry.rebind("body", "main_body", downstream)
    assert Ref(["main_body", "face_top"]) == downstream[0].args["on"]
    assert "main_body" in registry.features and "body" not in registry.features


def test_score_chain_commits_only_valid_steps():
    score = score_chain([
        "sk = sketch(plane=XY, circle=[center=origin, r=20]); body = extrude(profile=sk, length=2);",
        "h = pocket(on=body.face_top, depth=1);",
        "bad = pocket(on=missing.face_top, depth=1);",
        "p = pattern(feature=h, type=circular, count=4);",
        "not valid DSL",
    ])
    assert [(s.parse_ok, s.refs_valid, s.prior_preserved) for s in score.steps] == [
        (True, True, True), (True, True, True), (True, False, True),
        (True, True, True), (False, False, True),
    ]
    assert score.ref_break_rate == pytest.approx(0.4)


@pytest.mark.parametrize("length", [3, 5, 10])
def test_benchmark_v1_smoke(length):
    path = f"eval/benchmarks/chains_{length}step/shaft.json"
    score = score_chain(load_chain(path))
    assert len(score.steps) == length
    assert all(step.parse_ok and step.refs_valid and step.prior_preserved for step in score.steps)
    assert score.ref_break_rate == 0.0
