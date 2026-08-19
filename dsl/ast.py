"""
AST nodes.

The parser turns DSL text into a tree of these nodes. Every node carries a
stable feature name, an op type, and an args dict whose references are Ref
objects — never raw coordinates.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Ref:
    """A symbolic reference, e.g. body.face_top, or a pattern-instance
    selector, e.g. pat1[*] / pat1[2] (grammar.md §5)."""
    path: list[str]                       # ["body", "face_top"]
    index: str | int | None = None        # "*", an int, or None

    def __str__(self) -> str:
        base = ".".join(self.path)
        return base if self.index is None else f"{base}[{self.index}]"


@dataclass
class Quantity:
    """A number with an optional unit (grammar.md §2): 200, or 200 mm / 90 deg."""
    value: float
    unit: str | None = None               # "mm" | "deg" | None (default)

    def __str__(self) -> str:
        return f"{self.value}{self.unit or ''}"


@dataclass
class OpCall:
    """An unnamed, nested operation invocation used as an argument value,
    e.g. the `with=` argument of `replace` (grammar.md §6)."""
    op: str
    args: dict = field(default_factory=dict)


@dataclass
class Statement:
    """One statement: name = op(args) ;"""
    name: str | None                      # None for an edit op with no new feature
    op: str                               # sketch/extrude/.../replace/pattern/...
    args: dict = field(default_factory=dict)


@dataclass
class Program:
    """Ordered statements = one CAD model."""
    statements: list[Statement] = field(default_factory=list)


# Required args for the new ops (grammar.md §4.2), enforced by
# validate_new_op() so a malformed replace/pattern/mirror/constraint call
# fails at parse time instead of silently reaching the compiler.
NEW_OP_REQUIRED_ARGS: dict[str, set[str]] = {
    "replace": {"target", "with"},
    "pattern": {"feature", "type", "count"},
    "mirror": {"feature", "plane"},
    "constraint": {"type", "on", "value"},
}

PATTERN_TYPES = {"linear", "circular"}


class ASTValidationError(Exception):
    """A statement/op-call violates one of the new ops' grammar requirements."""


def validate_new_op(op: str, args: dict) -> None:
    """Check a replace/pattern/mirror/constraint call has its required args.

    A no-op for any other operation — base ops (sketch/extrude/...) aren't
    validated here.
    """
    required = NEW_OP_REQUIRED_ARGS.get(op)
    if required is None:
        return
    missing = required - args.keys()
    if missing:
        raise ASTValidationError(
            f"{op}(...) missing required arg(s): {', '.join(sorted(missing))}"
        )
    if op == "replace" and not isinstance(args["with"], OpCall):
        raise ASTValidationError("replace(...): `with` must be a nested operation call")
    if op == "pattern":
        ptype = args["type"]
        if isinstance(ptype, Ref) and str(ptype) not in PATTERN_TYPES:
            raise ASTValidationError(
                f"pattern(...): type must be one of {sorted(PATTERN_TYPES)}, got {ptype}"
            )
