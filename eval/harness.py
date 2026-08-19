"""Sequential-edit scoring harness for RQ2 / G3."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path

from dsl.parser import ParseError, parse
from dsl.registry import ReferenceError, ReferenceRegistry


@dataclass
class StepScore:
    parse_ok: bool
    refs_valid: bool
    prior_preserved: bool


@dataclass
class ChainScore:
    steps: list[StepScore] = field(default_factory=list)

    @property
    def ref_break_rate(self) -> float:
        return 0.0 if not self.steps else sum(not step.refs_valid for step in self.steps) / len(self.steps)


def score_chain(chain_dsls: list[str], registry: ReferenceRegistry | None = None) -> ChainScore:
    """Score incremental DSL chunks; failed steps never corrupt later state."""
    current = registry.clone() if registry is not None else ReferenceRegistry()
    result = ChainScore()
    for source in chain_dsls:
        before = current.features
        try:
            program = parse(source)
        except ParseError:
            result.steps.append(StepScore(False, False, True))
            continue
        candidate = current.clone()
        try:
            for statement in program.statements:
                candidate.register(statement)
        except ReferenceError:
            result.steps.append(StepScore(True, False, True))
            continue
        result.steps.append(StepScore(True, True, before.issubset(candidate.features)))
        current = candidate
    return result


def load_chain(path: str | Path) -> list[str]:
    """Load a benchmark-v1 JSON scenario and return its ordered DSL steps."""
    benchmark_path = Path(path)
    try:
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load benchmark {benchmark_path}: {exc}") from exc
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(steps, list) or not steps or not all(isinstance(step, str) for step in steps):
        raise ValueError(f"benchmark {benchmark_path} must contain a non-empty string list `steps`")
    expected = payload.get("expected", {})
    if expected.get("step_count", len(steps)) != len(steps):
        raise ValueError(f"benchmark {benchmark_path} step_count does not match `steps`")
    return steps
