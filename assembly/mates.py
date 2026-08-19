"""Decide whether declared mating interfaces actually assemble (proposed grammar.md §9).

The point of this module is that fastener mating is **parameter algebra, not geometry**.
Whether an M8x1.25 bolt accepts an M8x1.25 nut is decidable from the declarations alone:
no solid, no boolean, no solver. That puts it in the cheapest tier of the verification
strategy — a closed-form check that runs at compile time and either passes or names the
reason it did not.

What this module does NOT do, and must not be read as doing: it verifies that two
*declarations* are compatible, not that the geometry implements its own declaration. An
interface whose `on=` face is really 7.9 mm across while the declaration says `d=8` passes
every check here. Closing that gap needs the kernel, and is tracked separately.

Syntax note: `thread(...)`, `interface(...)` and `mate(...)` already parse under DSL v1 —
they are ordinary `name = op(args);` statements (grammar.md §3), so no parser change is
required. Only `dsl/registry.py`'s `LITERAL_ROOTS` would need the new bare words before
these statements can travel through `compile_program`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dsl.ast import Program, Quantity, Ref, Statement

# Bare words this layer treats as literals rather than feature references. These are what
# `dsl/registry.py`'s LITERAL_ROOTS would have to gain for the §9 addendum.
THREAD_FORMS = {"M", "UNC", "UNF", "G"}
HANDS = {"right", "left"}
INTERFACE_KINDS = {"male_thread", "female_thread", "clearance_hole", "spigot", "bore"}
MATE_KINDS = {"threaded", "clearance"}


class MateError(Exception):
    """Two declared interfaces cannot assemble.

    A distinct class per layer, following the convention CLAUDE.md records: the metrics
    count failures by exception type, so this must not be folded into CompileError.
    """


class AssemblyDeclarationError(Exception):
    """An assembly statement is malformed — wrong argument type, missing key, unknown word."""


@dataclass(frozen=True)
class Thread:
    form: str
    d: float  # nominal major diameter, mm
    pitch: float  # mm
    hand: str
    fit: str | None = None  # tolerance class, e.g. "6g" external / "6H" internal

    @property
    def designation(self) -> str:
        return f"{self.form}{self.d:g}x{self.pitch:g}"


@dataclass(frozen=True)
class Interface:
    name: str
    kind: str
    on: str | None = None  # the geometric reference this interface claims to describe
    thread: Thread | None = None
    engage: float | None = None  # length of thread engagement, mm
    d: float | None = None  # bore/clearance diameter, mm


def _word(value: Any, key: str, allowed: set[str]) -> str:
    """Read a bare identifier argument, e.g. `hand=right`."""
    if isinstance(value, Ref) and len(value.path) == 1 and value.index is None:
        word = value.path[0]
    elif isinstance(value, str):
        word = value
    else:
        raise AssemblyDeclarationError(f"{key} must be one of {', '.join(sorted(allowed))}, got {value!r}")
    if word not in allowed:
        raise AssemblyDeclarationError(f"unknown {key}: {word} (expected {', '.join(sorted(allowed))})")
    return word


def _number(value: Any, key: str) -> float:
    if isinstance(value, Quantity):
        return value.value
    if isinstance(value, (int, float)):
        return float(value)
    raise AssemblyDeclarationError(f"{key} must be a number, got {value!r}")


def _positive(value: Any, key: str) -> float:
    number = _number(value, key)
    if number <= 0:
        raise AssemblyDeclarationError(f"{key} must be positive, got {number:g}")
    return number


def _ref_name(value: Any, key: str) -> str:
    if not isinstance(value, Ref) or not value.path:
        raise AssemblyDeclarationError(f"{key} must be a reference, got {value!r}")
    return ".".join(value.path)


def _thread(statement: Statement) -> Thread:
    args = statement.args
    fit = args.get("fit")
    if fit is not None and not isinstance(fit, str):
        raise AssemblyDeclarationError(f"fit must be a quoted tolerance class, got {fit!r}")
    return Thread(
        form=_word(args.get("form"), "form", THREAD_FORMS),
        d=_positive(args.get("d"), "d"),
        pitch=_positive(args.get("pitch"), "pitch"),
        hand=_word(args.get("hand", Ref(["right"])), "hand", HANDS),
        fit=fit,
    )


def _interface(statement: Statement, threads: dict[str, Thread]) -> Interface:
    args = statement.args
    kind = _word(args.get("kind"), "kind", INTERFACE_KINDS)

    thread = None
    if "thread" in args:
        key = _ref_name(args["thread"], "thread")
        if key not in threads:
            raise AssemblyDeclarationError(f"interface refers to an undeclared thread: {key}")
        thread = threads[key]

    return Interface(
        name=statement.name or "<anonymous>",
        kind=kind,
        on=_ref_name(args["on"], "on") if "on" in args else None,
        thread=thread,
        engage=_positive(args["engage"], "engage") if "engage" in args else None,
        d=_positive(args["d"], "d") if "d" in args else None,
    )


def collect(prog: Program) -> tuple[dict[str, Interface], list[Statement]]:
    """Pull the assembly declarations out of a program, ignoring the geometry statements."""
    threads: dict[str, Thread] = {}
    interfaces: dict[str, Interface] = {}
    mates: list[Statement] = []

    for statement in prog.statements:
        if statement.op == "thread":
            if statement.name is None:
                raise AssemblyDeclarationError("a thread declaration must be named")
            threads[statement.name] = _thread(statement)
        elif statement.op == "interface":
            if statement.name is None:
                raise AssemblyDeclarationError("an interface declaration must be named")
            interfaces[statement.name] = _interface(statement, threads)
        elif statement.op == "mate":
            mates.append(statement)

    return interfaces, mates


# --- the checks -------------------------------------------------------------------


def _external_class(fit: str) -> bool:
    """ISO 965 writes external tolerance classes lowercase (6g) and internal uppercase (6H)."""
    return fit[-1].islower()


def check_threaded(a: Interface, b: Interface, *, min_engagement_ratio: float = 0.8) -> None:
    """Every condition under which a nut does not accept a bolt, checked from declarations."""
    kinds = {a.kind, b.kind}
    if kinds != {"male_thread", "female_thread"}:
        raise MateError(
            f"a threaded mate needs one male_thread and one female_thread, got "
            f"{a.name}={a.kind} and {b.name}={b.kind}"
        )
    male, female = (a, b) if a.kind == "male_thread" else (b, a)

    if male.thread is None or female.thread is None:
        raise MateError("both interfaces of a threaded mate must declare a thread")
    mt, ft = male.thread, female.thread

    if mt.form != ft.form:
        raise MateError(f"thread form differs: {male.name} is {mt.form}, {female.name} is {ft.form}")
    if mt.d != ft.d:
        raise MateError(
            f"nominal diameter differs: {male.name} is {mt.designation}, {female.name} is {ft.designation}"
        )
    if mt.pitch != ft.pitch:
        raise MateError(f"pitch differs: {male.name} is {mt.designation}, {female.name} is {ft.designation}")
    if mt.hand != ft.hand:
        raise MateError(f"hand differs: {male.name} is {mt.hand}, {female.name} is {ft.hand}")

    # A tolerance class only means anything on the side it was written for; two external
    # classes on a bolt/nut pair is a specification error, not a tight fit.
    if mt.fit is not None and not _external_class(mt.fit):
        raise MateError(f"{male.name} is an external thread but carries the internal class {mt.fit}")
    if ft.fit is not None and _external_class(ft.fit):
        raise MateError(f"{female.name} is an internal thread but carries the external class {ft.fit}")

    engagements = [e for e in (male.engage, female.engage) if e is not None]
    if engagements:
        required = min_engagement_ratio * mt.d
        available = min(engagements)
        if available < required:
            raise MateError(
                f"thread engagement {available:g} mm is below the {min_engagement_ratio:g}xd minimum "
                f"of {required:g} mm for {mt.designation}"
            )


def check_clearance(a: Interface, b: Interface, *, clearance: dict[float, float] | None = None) -> None:
    """A fastener passing through a hole: the hole has to be big enough, and not absurdly big."""
    kinds = {a.kind, b.kind}
    if kinds != {"male_thread", "clearance_hole"} and kinds != {"spigot", "bore"}:
        raise MateError(
            f"a clearance mate needs a fastener and a hole, got {a.name}={a.kind} and {b.name}={b.kind}"
        )
    pin, hole = (a, b) if a.kind in {"male_thread", "spigot"} else (b, a)

    pin_d = pin.thread.d if pin.thread is not None else pin.d
    if pin_d is None:
        raise MateError(f"{pin.name} declares no diameter, so clearance cannot be checked")
    if hole.d is None:
        raise MateError(f"{hole.name} declares no diameter, so clearance cannot be checked")

    if hole.d < pin_d:
        raise MateError(
            f"{hole.name} is {hole.d:g} mm, smaller than {pin.name} at {pin_d:g} mm — it cannot pass"
        )

    # The recommended hole comes from a standards table the project owns; see
    # config/default.yaml. Without one, "fits at all" is the only decidable claim.
    if clearance:
        recommended = clearance.get(pin_d)
        if recommended is not None and hole.d < recommended:
            raise MateError(
                f"{hole.name} is {hole.d:g} mm; {pin_d:g} mm needs at least {recommended:g} mm clearance"
            )


def check_grip(bolt_length: float, stack: list[float], nut_height: float, *, protrusion: float = 1.5) -> None:
    """A bolt long enough to clear the stack and still show thread past the nut."""
    needed = sum(stack) + nut_height + protrusion
    if bolt_length < needed:
        raise MateError(
            f"bolt length {bolt_length:g} mm is short: {sum(stack):g} mm of stack plus a "
            f"{nut_height:g} mm nut plus {protrusion:g} mm protrusion needs {needed:g} mm"
        )


def check_program(prog: Program, *, min_engagement_ratio: float = 0.8, clearance=None) -> list[str]:
    """Check every `mate` in a program. Returns the mates that passed, raises on the first that does not."""
    interfaces, mates = collect(prog)
    checked: list[str] = []

    for statement in mates:
        kind = _word(statement.args.get("kind"), "kind", MATE_KINDS)
        names = []
        for key in ("a", "b"):
            if key not in statement.args:
                raise AssemblyDeclarationError(f"a mate needs both `a` and `b`; missing {key}")
            names.append(_ref_name(statement.args[key], key))

        pair = []
        for name in names:
            if name not in interfaces:
                raise AssemblyDeclarationError(f"mate refers to an undeclared interface: {name}")
            pair.append(interfaces[name])

        if kind == "threaded":
            check_threaded(pair[0], pair[1], min_engagement_ratio=min_engagement_ratio)
        else:
            check_clearance(pair[0], pair[1], clearance=clearance)
        checked.append(statement.name or f"{names[0]}~{names[1]}")

    return checked
