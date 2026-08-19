"""Execute DSL AST programs through a pluggable CAD backend."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from .ast import OpCall, Program, Quantity, Ref
from .registry import ReferenceError, ReferenceRegistry


class CompileError(Exception):
    """Parsing succeeded, but symbolic or kernel execution failed."""


# Local (x, y) axes of each sketch plane named in grammar.md §5; the normal is x cross y.
_PLANE_AXES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "XY": ((1, 0, 0), (0, 1, 0)),
    "XZ": ((1, 0, 0), (0, 0, 1)),
    "YZ": ((0, 1, 0), (0, 0, 1)),
}


class Backend(Protocol):
    def reset(self) -> None: ...
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

    def reset(self) -> None:
        """Drop all state, so one backend can compile successive programs independently."""
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
        # feature name -> (point on its axis, unit direction), so `<feature>.axis`
        # can be resolved as a sketch anchor (grammar.md §5).
        self.axes: dict[str, tuple[Any, Any]] = {}

    def reset(self) -> None:
        """Drop all state, so one backend can compile successive programs independently.

        Without this, `self.objects` outlives a `compile_program` call while the
        registry does not, so a later program could return an earlier program's
        solid and leave superseded objects orphaned in the document.
        """
        for name in list(self.objects):
            obj = self.objects.pop(name)
            if hasattr(obj, "Shape"):
                self.doc.removeObject(obj.Name)
        self.axes.clear()

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, Quantity):
            return value.value
        if isinstance(value, (int, float)):
            return float(value)
        raise CompileError(f"expected numeric quantity, got {value!r}")

    def _positive(self, value: Any, what: str) -> float:
        """A dimension the kernel can actually build.

        `Part.makeBox` rejects non-positive sides, but `Part.makeCylinder` accepts
        them and returns a degenerate or inside-out solid whose `.Volume` then raises
        a raw kernel error outside the compiler's error channel. Check both here so
        the two profile branches fail the same way.
        """
        number = self._number(value)
        if number <= 0:
            raise CompileError(f"{what} must be positive, got {number:g}")
        return number

    def _plane_frame(self, plane: Any) -> Any:
        """Rotation taking the sketch's local frame to world (grammar.md §4.1 `plane`)."""
        name = plane.path[0] if isinstance(plane, Ref) and plane.path else "XY"
        try:
            local_x, local_y = _PLANE_AXES[name]
        except KeyError:
            raise CompileError(
                f"unknown sketch plane: {name} (expected one of {', '.join(sorted(_PLANE_AXES))})"
            ) from None
        Vector, Rotation = self.FreeCAD.Vector, self.FreeCAD.Rotation
        return Rotation(Vector(*local_x), Vector(*local_y), Vector(0, 0, 0), "ZXY")

    def _resolve_anchor(self, value: Any, normal: Any) -> Any:
        """Resolve a sketch `center=` to a world point on the sketch plane through the origin."""
        Vector = self.FreeCAD.Vector
        if value is None:
            return Vector(0, 0, 0)
        if isinstance(value, Ref):
            root = value.path[0]
            if root == "origin" and len(value.path) == 1:
                return Vector(0, 0, 0)
            if len(value.path) == 2 and value.path[1] == "axis":
                if root not in self.axes:
                    raise CompileError(f"cannot anchor on the axis of an unbuilt feature: {value}")
                base, direction = self.axes[root]
                # The anchor is where that axis meets the sketch plane (which passes
                # through the world origin with the given normal).
                denominator = direction.dot(normal)
                if abs(denominator) < 1e-9:
                    raise CompileError(f"axis {value} is parallel to the sketch plane; no anchor point")
                return base - direction * (base.dot(normal) / denominator)
            raise CompileError(
                f"sketch anchor {value} is not resolvable yet; v1 supports `origin` and `<feature>.axis`"
            )
        raise CompileError(f"expected a sketch anchor reference, got {value!r}")

    def _extrusion_direction(self, args: dict[str, Any], normal: Any) -> Any:
        """`dir` overrides the plane normal, but only along the same axis (grammar.md §4.1)."""
        given = args.get("dir")
        if given is None:
            return normal
        if not isinstance(given, Ref) or not given.path:
            raise CompileError(f"expected an axis reference for dir, got {given!r}")
        try:
            local_x, local_y = _PLANE_AXES[given.path[0]]
        except KeyError:
            raise CompileError(f"unknown extrude direction: {given.path[0]}") from None
        Vector = self.FreeCAD.Vector
        candidate = Vector(*local_x).cross(Vector(*local_y))
        if candidate.cross(normal).Length > 1e-9:
            raise CompileError(
                f"oblique extrusion is not supported: dir={given.path[0]} is not parallel to the "
                "sketch plane normal"
            )
        return candidate

    def feature(self, name: str, op: str, args: dict[str, Any]) -> Any:
        if op == "sketch":
            self.objects[name] = deepcopy(args)
            return self.objects[name]
        if op == "extrude":
            profile = args.get("profile")
            sketch = self.objects.get(str(profile)) if isinstance(profile, Ref) else None
            length = self._positive(args.get("length"), "extrude length")
            if not isinstance(sketch, dict):
                raise CompileError(f"extrude profile is not a compiled sketch: {profile}")

            rotation = self._plane_frame(sketch.get("plane"))
            normal = rotation.multVec(self.FreeCAD.Vector(0, 0, 1))
            direction = self._extrusion_direction(args, normal)

            if "circle" in sketch:
                circle = sketch["circle"]
                anchor = self._resolve_anchor(circle.get("center"), normal)
                shape = self.Part.makeCylinder(
                    self._positive(circle.get("r"), "circle r"), length, anchor, direction
                )
            elif "rect" in sketch:
                rect = sketch["rect"]
                anchor = self._resolve_anchor(rect.get("center"), normal)
                # A rect is anchored by its corner, so orientation comes from the sketch
                # frame rather than from `direction` alone.
                shape = self.Part.makeBox(
                    self._positive(rect.get("w"), "rect w"),
                    self._positive(rect.get("h"), "rect h"),
                    length,
                )
                placement = self.FreeCAD.Placement(anchor, rotation)
                if direction.dot(normal) < 0:
                    placement = self.FreeCAD.Placement(
                        anchor, rotation.multiply(self.FreeCAD.Rotation(self.FreeCAD.Vector(1, 0, 0), 180))
                    )
                shape.Placement = placement
            else:
                raise CompileError("FreeCAD backend currently supports circle/rect sketches")

            obj = self.doc.addObject("PartDesign::Feature", name)
            obj.Shape = shape
            self.objects[name] = obj
            self.axes[name] = (obj.Shape.CenterOfMass, direction)
            return obj
        raise CompileError(f"FreeCAD backend operation not implemented: {op}")

    def edit(self, target: str, field_name: str, value: Any) -> None:
        raise CompileError("FreeCAD parameter edit requires feature-history rebuild")

    def replace(self, target: str, op: str, args: dict[str, Any]) -> Any:
        raise CompileError("FreeCAD replacement requires feature-history rebuild")

    def finish(self) -> Any:
        """Return the whole model, fusing every solid the program built.

        Returning one body would silently hand downstream measurement a fragment
        of the described part, and which fragment would depend on declaration
        order rather than on modelling intent.
        """
        self.doc.recompute()
        solids = [obj.Shape for obj in self.objects.values() if hasattr(obj, "Shape")]
        if not solids:
            raise CompileError("program produced no solid")
        model = solids[0]
        for solid in solids[1:]:
            model = model.fuse(solid)
        if not model.isValid():
            raise CompileError("program produced an invalid solid")
        return model


def _anonymous_name(index: int) -> str:
    """Key for an unnamed statement that no DSL identifier can collide with.

    `grammar.md` §2 defines `identifier ::= [a-zA-Z_][a-zA-Z0-9_]*`, so a name
    containing spaces or angle brackets is unreachable from source. The previous
    `__op_{index}` form was a legal identifier, and since the registry never sees
    auto-minted names its uniqueness guard could not protect the backend from a
    user feature of the same name.
    """
    return f"<anonymous {index}>"


def _whole_feature(value: Any, op: str) -> str:
    if not isinstance(value, Ref) or len(value.path) != 1 or value.index is not None:
        raise CompileError(f"{op} target must be a whole-feature reference")
    return value.path[0]


def compile_program(prog: Program, backend: Backend | None = None) -> Any:
    """Validate references and execute statements in source order."""
    active_backend: Backend = backend if backend is not None else FreeCADBackend()
    # The registry is rebuilt per call, so the backend must start clean too — otherwise
    # a reused backend disagrees with it about which features exist.
    active_backend.reset()
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
                name = statement.name if statement.name is not None else _anonymous_name(index)
                active_backend.feature(name, statement.op, statement.args)
        return active_backend.finish()
    except (CompileError, ReferenceError):
        raise
    except Exception as exc:
        raise CompileError(f"backend execution failed: {exc}") from exc
