"""Execute DSL AST programs through a pluggable CAD backend."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from .ast import OpCall, Program, Quantity, Ref
from .registry import ReferenceError, ReferenceRegistry


class CompileError(Exception):
    """Parsing succeeded, but symbolic or kernel execution failed."""


class Backend(Protocol):
    def feature(self, name: str, op: str, args: dict[str, Any]) -> Any: ...
    def edit(self, target: str, field_name: str, value: Any) -> None: ...
    def replace(self, target: str, op: str, args: dict[str, Any]) -> Any: ...
    def finish(self) -> Any: ...


@dataclass
class SymbolicFeature:
    name: str
    op: str
    args: dict[str, Any]


@dataclass
class SymbolicModel:
    features: dict[str, SymbolicFeature] = field(default_factory=dict)
    operations: list[str] = field(default_factory=list)


class SymbolicBackend:
    """Deterministic no-kernel backend for CI and reference evaluation."""

    def __init__(self) -> None:
        self.model = SymbolicModel()

    def feature(self, name: str, op: str, args: dict[str, Any]) -> SymbolicFeature:
        feature = SymbolicFeature(name, op, deepcopy(args))
        self.model.features[name] = feature
        self.model.operations.append(f"{name}={op}")
        return feature

    def edit(self, target: str, field_name: str, value: Any) -> None:
        if target not in self.model.features:
            raise CompileError(f"edit target does not exist: {target}")
        self.model.features[target].args[field_name] = deepcopy(value)
        self.model.operations.append(f"edit:{target}.{field_name}")

    def replace(self, target: str, op: str, args: dict[str, Any]) -> SymbolicFeature:
        if target not in self.model.features:
            raise CompileError(f"replace target does not exist: {target}")
        feature = SymbolicFeature(target, op, deepcopy(args))
        self.model.features[target] = feature
        self.model.operations.append(f"replace:{target}={op}")
        return feature

    def finish(self) -> SymbolicModel:
        return self.model


class FreeCADBackend:
    """Headless FreeCAD Part adapter; imports FreeCAD only when selected."""

    def __init__(self) -> None:
        try:
            import FreeCAD  # type: ignore
            import Part  # type: ignore
        except ImportError as exc:
            raise CompileError(
                "FreeCAD Python modules are unavailable; install FreeCAD or pass "
                "SymbolicBackend() for syntax/reference evaluation"
            ) from exc
        self.FreeCAD, self.Part = FreeCAD, Part
        self.doc = FreeCAD.newDocument("LLMCAD")
        self.objects: dict[str, Any] = {}

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, Quantity):
            return value.value
        if isinstance(value, (int, float)):
            return float(value)
        raise CompileError(f"expected numeric quantity, got {value!r}")

    def feature(self, name: str, op: str, args: dict[str, Any]) -> Any:
        if op == "sketch":
            self.objects[name] = deepcopy(args)
            return self.objects[name]
        if op == "extrude":
            profile = args.get("profile")
            sketch = self.objects.get(str(profile)) if isinstance(profile, Ref) else None
            length = self._number(args.get("length"))
            if not isinstance(sketch, dict):
                raise CompileError(f"extrude profile is not a compiled sketch: {profile}")
            if "circle" in sketch:
                shape = self.Part.makeCylinder(self._number(sketch["circle"].get("r")), length)
            elif "rect" in sketch:
                rect = sketch["rect"]
                shape = self.Part.makeBox(self._number(rect.get("w")), self._number(rect.get("h")), length)
            else:
                raise CompileError("FreeCAD backend currently supports circle/rect sketches")
            obj = self.doc.addObject("PartDesign::Feature", name)
            obj.Shape = shape
            self.objects[name] = obj
            return obj
        raise CompileError(f"FreeCAD backend operation not implemented: {op}")

    def edit(self, target: str, field_name: str, value: Any) -> None:
        raise CompileError("FreeCAD parameter edit requires feature-history rebuild")

    def replace(self, target: str, op: str, args: dict[str, Any]) -> Any:
        raise CompileError("FreeCAD replacement requires feature-history rebuild")

    def finish(self) -> Any:
        self.doc.recompute()
        solids = [obj.Shape for obj in self.objects.values() if hasattr(obj, "Shape")]
        if not solids:
            raise CompileError("program produced no solid")
        return solids[-1]


def _whole_feature(value: Any, op: str) -> str:
    if not isinstance(value, Ref) or len(value.path) != 1 or value.index is not None:
        raise CompileError(f"{op} target must be a whole-feature reference")
    return value.path[0]


def compile_program(prog: Program, backend: Backend | None = None) -> Any:
    """Validate references and execute statements in source order."""
    active_backend: Backend = backend if backend is not None else FreeCADBackend()
    registry = ReferenceRegistry()
    try:
        for index, statement in enumerate(prog.statements):
            registry.register(statement)
            if statement.op == "edit":
                target = _whole_feature(statement.args.get("target"), "edit")
                field_ref = statement.args.get("set")
                if not isinstance(field_ref, Ref) or len(field_ref.path) != 1:
                    raise CompileError("edit set must be a bare field name")
                active_backend.edit(target, field_ref.path[0], statement.args.get("value"))
            elif statement.op == "replace":
                target = _whole_feature(statement.args.get("target"), "replace")
                replacement = statement.args["with"]
                if not isinstance(replacement, OpCall):
                    raise CompileError("replace `with` must be an operation call")
                active_backend.replace(target, replacement.op, replacement.args)
            else:
                name = statement.name or f"__op_{index}"
                active_backend.feature(name, statement.op, statement.args)
        return active_backend.finish()
    except (CompileError, ReferenceError):
        raise
    except Exception as exc:
        raise CompileError(f"backend execution failed: {exc}") from exc
