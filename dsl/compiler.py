"""Execute DSL AST programs through a pluggable CAD backend."""
#asdfsafd
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from math import cos, pi, sin
from typing import Any, Protocol

from .ast import OpCall, Program, Quantity, Ref
from .registry import ReferenceError, ReferenceRegistry
from .subshapes import ResolvedSubshape, SubshapeResolutionError, SubshapeResolver


class CompileError(Exception):
    """Parsing succeeded, but symbolic or kernel execution failed."""


@dataclass(frozen=True)
class ProfileSpec:
    """Kernel-independent, normalized description of a closed 2D profile.

    Rectangles, polygons, and hexagons all become a vertex loop. Circles keep
    their analytic radius so OCCT can build a true circular edge rather than a
    tessellated approximation. ``plane`` and ``anchor`` remain symbolic until
    the backend resolves them against the current model.
    """

    kind: str
    plane: Any
    anchor: Any
    radius: float | None = None
    vertices: tuple[tuple[float, float], ...] = ()


@dataclass
class KernelFeatureRecord:
    """Replayable authored feature used for explicit history rebuilds."""

    name: str
    op: str
    args: dict[str, Any]
    revision: int = 1


@dataclass(frozen=True)
class ConstraintRecord:
    """Validated v1 constraint declaration retained for the verify layer (P0/P3 boundary)."""

    constraint_type: str
    target: Ref
    value: Any
    history_version: int


# Local (x, y) axes of each sketch plane named in grammar.md §5; the normal is x cross y.
_PLANE_AXES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "XY": ((1, 0, 0), (0, 1, 0)),
    "XZ": ((1, 0, 0), (0, 0, 1)),
    "YZ": ((0, 1, 0), (0, 0, 1)),
}


class Backend(Protocol):
    def reset(self) -> None: ...
    def close(self) -> None: ...
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

    def close(self) -> None:
        """No kernel resources to release; present so the Backend protocol is uniform."""

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
            # Order is load-bearing: Part.so links against the App layer FreeCAD sets
            # up, and importing Part first segfaults rather than raising.
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
        # Terminal solids only. Modifier features replace their input here,
        # while ``objects`` keeps aliases such as ``body`` resolvable.
        self.active_solids: dict[str, Any] = {}
        # feature name -> (point on its axis, unit direction), so `<feature>.axis`
        # can be resolved as a sketch anchor (grammar.md §5).
        self.axes: dict[str, tuple[Any, Any]] = {}
        # Authored feature provenance stays separate from object aliases. A
        # modifier advances every alias that points at its source tip, while the
        # new modifier name keeps its own operation semantics (for example,
        # `body.wall` is the outer wall and `hole.wall` is the pocket wall).
        self.feature_ops: dict[str, str] = {}
        self.history_versions: dict[str, int] = {}
        # Pocket/groove tools let pattern and mirror replay the feature effect
        # instead of copying the entire already-modified body.
        self.modifier_tools: dict[str, Any] = {}
        self.modifier_sources: dict[str, str] = {}
        self.constraints: list[ConstraintRecord] = []
        self.subshape_resolver = SubshapeResolver()
        self.feature_history: list[KernelFeatureRecord] = []
        self._replaying_history = False
        self._active_revision = 1

    def _clear_runtime_geometry(self) -> None:
        """Clear generated OCCT objects and bindings while retaining authored history."""
        for obj in list(self.doc.Objects):
            self.doc.removeObject(obj.Name)
        self.objects.clear()
        self.active_solids.clear()
        self.axes.clear()
        self.feature_ops.clear()
        self.history_versions.clear()
        self.modifier_tools.clear()
        self.modifier_sources.clear()
        self.constraints.clear()

    def reset(self) -> None:
        """Drop all state, so one backend can compile successive programs independently.

        Without this, `self.objects` outlives a `compile_program` call while the
        registry does not, so a later program could return an earlier program's
        solid and leave superseded objects orphaned in the document.
        """
        if self.doc is None:
            raise CompileError("this FreeCADBackend has been closed")
        # The document belongs exclusively to this backend. Iterating the
        # document itself also removes superseded modifier-history objects that
        # no longer have an alias in ``self.objects``.
        self._clear_runtime_geometry()
        self.feature_history.clear()
        self._replaying_history = False
        self._active_revision = 1

    def close(self) -> None:
        """Release the FreeCAD document. Idempotent.

        Shapes already returned stay valid — OCCT reference-counts them — so a
        caller can keep the compiled solid after the backend is gone. Without
        this, every backend leaked a document for the life of the process, and
        `newDocument` scans the open-document list to uniquify names, so backend
        construction slowed as the leak grew.
        """
        if self.doc is not None:
            self.FreeCAD.closeDocument(self.doc.Name)
            self.doc = None
        self.objects.clear()
        self.active_solids.clear()
        self.axes.clear()
        self.feature_ops.clear()
        self.history_versions.clear()
        self.modifier_tools.clear()
        self.modifier_sources.clear()
        self.constraints.clear()
        self.feature_history.clear()
        self._replaying_history = False
        self._active_revision = 1

    def __enter__(self) -> FreeCADBackend:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, Quantity):
            return value.value
        if isinstance(value, (int, float)):
            return float(value)
        raise CompileError(f"expected numeric quantity, got {value!r}")

    def _positive(self, value: Any, what: str) -> float:
        """Validate a positive linear dimension before it reaches OCCT."""
        if isinstance(value, Quantity) and value.unit not in {None, "mm"}:
            raise CompileError(f"{what} must use mm, got {value.unit}")
        number = self._number(value)
        if number <= 0:
            raise CompileError(f"{what} must be positive, got {number:g}")
        return number

    def _linear_number(self, value: Any, what: str) -> float:
        """Return a signed linear coordinate expressed in millimetres."""
        if isinstance(value, Quantity) and value.unit not in {None, "mm"}:
            raise CompileError(f"{what} must use mm, got {value.unit}")
        return self._number(value)

    def _angle(self, value: Any, what: str, *, full_turn: bool = True) -> float:
        """Return a positive angle in degrees within one turn."""
        if isinstance(value, Quantity) and value.unit not in {None, "deg"}:
            raise CompileError(f"{what} must use deg, got {value.unit}")
        number = self._number(value)
        maximum = 360.0 if full_turn else 180.0
        if number <= 0 or number > maximum:
            raise CompileError(f"{what} must be in (0, {maximum:g}], got {number:g}")
        return number

    def _count(self, value: Any, what: str) -> int:
        """Validate a pattern count without silently rounding a float."""
        if isinstance(value, Quantity) and value.unit is not None:
            raise CompileError(f"{what} must be unitless, got {value.unit}")
        number = self._number(value)
        if not number.is_integer() or number < 2:
            raise CompileError(f"{what} must be an integer >= 2, got {number:g}")
        return int(number)

    @staticmethod
    def _check_profile_args(values: dict[str, Any], allowed: set[str], what: str) -> None:
        unexpected = values.keys() - allowed
        if unexpected:
            raise CompileError(f"{what} has unsupported arg(s): {', '.join(sorted(unexpected))}")

    @staticmethod
    def _segments_intersect(
        first_start: tuple[float, float],
        first_end: tuple[float, float],
        second_start: tuple[float, float],
        second_end: tuple[float, float],
    ) -> bool:
        """Return whether two closed 2D segments intersect, including collinear overlap."""

        def cross(origin: tuple[float, float], end: tuple[float, float], point: tuple[float, float]) -> float:
            return (end[0] - origin[0]) * (point[1] - origin[1]) - (end[1] - origin[1]) * (
                point[0] - origin[0]
            )

        def on_segment(
            start: tuple[float, float], end: tuple[float, float], point: tuple[float, float]
        ) -> bool:
            epsilon = 1e-12
            return (
                min(start[0], end[0]) - epsilon <= point[0] <= max(start[0], end[0]) + epsilon
                and min(start[1], end[1]) - epsilon <= point[1] <= max(start[1], end[1]) + epsilon
            )

        epsilon = 1e-12
        c1 = cross(first_start, first_end, second_start)
        c2 = cross(first_start, first_end, second_end)
        c3 = cross(second_start, second_end, first_start)
        c4 = cross(second_start, second_end, first_end)
        if ((c1 > epsilon and c2 < -epsilon) or (c1 < -epsilon and c2 > epsilon)) and (
            (c3 > epsilon and c4 < -epsilon) or (c3 < -epsilon and c4 > epsilon)
        ):
            return True
        return (
            (abs(c1) <= epsilon and on_segment(first_start, first_end, second_start))
            or (abs(c2) <= epsilon and on_segment(first_start, first_end, second_end))
            or (abs(c3) <= epsilon and on_segment(second_start, second_end, first_start))
            or (abs(c4) <= epsilon and on_segment(second_start, second_end, first_end))
        )

    def _validated_vertices(self, raw_points: Any, what: str = "polygon") -> tuple[tuple[float, float], ...]:
        if not isinstance(raw_points, list):
            raise CompileError(f"{what} must be a list of [x, y] points")
        points: list[tuple[float, float]] = []
        for index, raw_point in enumerate(raw_points):
            if not isinstance(raw_point, list) or len(raw_point) != 2:
                raise CompileError(f"{what} point {index} must be [x, y]")
            points.append(
                (
                    self._linear_number(raw_point[0], f"{what} point {index} x"),
                    self._linear_number(raw_point[1], f"{what} point {index} y"),
                )
            )
        # Both open vertex lists and explicitly closed lists are accepted; the
        # normalized representation stores the closing point only once.
        if len(points) >= 2 and points[0] == points[-1]:
            points.pop()
        if len(points) < 3:
            raise CompileError(f"{what} requires at least 3 distinct points")
        if len(set(points)) != len(points):
            raise CompileError(f"{what} contains duplicate points")

        count = len(points)
        for first in range(count):
            for second in range(first + 1, count):
                # Adjacent edges share an endpoint by construction. Edge zero
                # and the final edge are adjacent too.
                if second == first + 1 or (first == 0 and second == count - 1):
                    continue
                if self._segments_intersect(
                    points[first],
                    points[(first + 1) % count],
                    points[second],
                    points[(second + 1) % count],
                ):
                    raise CompileError(f"{what} is self-intersecting")

        twice_area = sum(
            point[0] * points[(index + 1) % count][1] - points[(index + 1) % count][0] * point[1]
            for index, point in enumerate(points)
        )
        if abs(twice_area) <= 1e-12:
            raise CompileError(f"{what} has zero area")
        return tuple(points)

    def _circle_spec(self, values: Any, plane: Any = None) -> ProfileSpec:
        if not isinstance(values, dict):
            raise CompileError("circle must be [center=..., r=...]")
        self._check_profile_args(values, {"center", "r"}, "circle")
        return ProfileSpec(
            kind="circle",
            plane=plane,
            anchor=values.get("center"),
            radius=self._positive(values.get("r"), "circle r"),
        )

    def _profile_from_sketch(self, sketch: dict[str, Any]) -> ProfileSpec:
        self._check_profile_args(sketch, {"plane", "circle", "rect", "polygon"}, "sketch")
        profile_keys = [key for key in ("circle", "rect", "polygon") if key in sketch]
        if len(profile_keys) != 1:
            raise CompileError("sketch must define exactly one of circle, rect, or polygon")
        plane = sketch.get("plane")
        if "circle" in sketch:
            return self._circle_spec(sketch["circle"], plane)
        if "rect" in sketch:
            rect = sketch["rect"]
            if not isinstance(rect, dict):
                raise CompileError("rect must be [w=..., h=...] with an optional center")
            self._check_profile_args(rect, {"center", "w", "h"}, "rect")
            width = self._positive(rect.get("w"), "rect w")
            height = self._positive(rect.get("h"), "rect h")
            return ProfileSpec(
                kind="polygon",
                plane=plane,
                anchor=rect.get("center"),
                vertices=((0.0, 0.0), (width, 0.0), (width, height), (0.0, height)),
            )
        if "polygon" in sketch:
            return ProfileSpec(
                kind="polygon",
                plane=plane,
                anchor=None,
                vertices=self._validated_vertices(sketch["polygon"]),
            )
        raise AssertionError("validated profile key was not dispatched")

    def _profile_spec(self, profile: Any) -> ProfileSpec:
        if isinstance(profile, Ref):
            sketch = self.objects.get(str(profile))
            if not isinstance(sketch, ProfileSpec):
                raise CompileError(f"extrude profile is not a compiled sketch: {profile}")
            return sketch
        if isinstance(profile, OpCall) and profile.op == "hex":
            self._check_profile_args(profile.args, {"center", "plane", "r"}, "hex")
            radius = self._positive(profile.args.get("r"), "hex r")
            vertices = tuple(
                (radius * cos(index * pi / 3), radius * sin(index * pi / 3)) for index in range(6)
            )
            return ProfileSpec(
                kind="polygon",
                plane=profile.args.get("plane", Ref(["XY"])),
                anchor=profile.args.get("center", Ref(["origin"])),
                vertices=vertices,
            )
        raise CompileError(f"extrude profile is not a compiled sketch: {profile}")

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

    @staticmethod
    def _whole_ref(value: Any, what: str) -> str:
        if not isinstance(value, Ref) or len(value.path) != 1 or value.index is not None:
            raise CompileError(f"{what} must be a whole-feature reference")
        return value.path[0]

    def _axis_line(self, value: Any, *, profile: ProfileSpec | None = None, what: str) -> tuple[Any, Any]:
        """Resolve a revolve/groove axis to a point and unit direction."""
        Vector = self.FreeCAD.Vector
        if isinstance(value, Ref) and value.path == ["origin"]:
            if profile is None:
                raise CompileError(f"{what}=origin requires a profile plane")
            plane_name = profile.plane.path[0] if isinstance(profile.plane, Ref) else "XY"
            try:
                local_x, _ = _PLANE_AXES[plane_name]
            except KeyError:
                raise CompileError(f"unknown sketch plane: {plane_name}") from None
            return Vector(0, 0, 0), Vector(*local_x).normalize()
        if isinstance(value, Ref) and len(value.path) == 2 and value.path[1] == "axis":
            try:
                base, direction = self.axes[value.path[0]]
            except KeyError:
                raise CompileError(f"cannot resolve {what}: {value}") from None
            return base, direction.normalize()
        raise CompileError(f"{what} must be origin or <feature>.axis, got {value}")

    @staticmethod
    def _volume_tolerance(shape: Any) -> float:
        return max(1e-8, abs(float(shape.Volume)) * 1e-10)

    def _checked_cut(self, source: Any, cutter: Any, operation: str) -> Any:
        """Enforce Total-CSG preconditions and postconditions for subtractive features."""
        if cutter.isNull() or not cutter.isValid() or cutter.Volume <= self._volume_tolerance(cutter):
            raise CompileError(f"{operation} cutter is not a valid nonzero solid")
        intersection = source.common(cutter)
        tolerance = self._volume_tolerance(source)
        if intersection.isNull() or intersection.Volume <= tolerance:
            raise CompileError(f"{operation} cutter does not intersect the target solid")
        if intersection.Volume >= source.Volume - tolerance:
            raise CompileError(f"{operation} would remove the entire target solid")
        result = source.cut(cutter)
        if result.ShapeType != "Solid" and len(result.Solids) == 1:
            result = result.Solids[0]
        if result.isNull() or not result.isValid() or not result.Solids:
            raise CompileError(f"{operation} produced an invalid or empty B-rep")
        if result.Volume >= source.Volume - tolerance:
            raise CompileError(f"{operation} did not remove a measurable volume")
        return result

    def _checked_union(self, source: Any, additions: list[Any], operation: str) -> Any:
        """Fuse patterned/mirrored additions and reject duplicate/no-op placements."""
        result = source
        before = float(source.Volume)
        for addition in additions:
            if addition.isNull() or not addition.isValid() or not addition.Solids:
                raise CompileError(f"{operation} generated an invalid solid instance")
            result = result.fuse(addition)
        if result.ShapeType != "Solid" and len(result.Solids) == 1:
            result = result.Solids[0]
        if result.isNull() or not result.isValid() or not result.Solids:
            raise CompileError(f"{operation} produced an invalid or empty B-rep")
        if result.Volume <= before + self._volume_tolerance(source):
            raise CompileError(f"{operation} instances do not add distinct geometry")
        return result

    def _require_roles(self, shape: Any, axis: Any, operation: str, roles: tuple[str, ...]) -> None:
        """Reject a solid that cannot expose roles promised by grammar.md §5."""
        try:
            for role in roles:
                self.subshape_resolver.resolve(
                    feature="<candidate>",
                    operation=operation,
                    history_version=self._active_revision,
                    role=role,
                    shape=shape,
                    axis=axis,
                )
        except SubshapeResolutionError as exc:
            raise CompileError(f"{operation} result cannot expose required v1 roles: {exc}") from exc

    def _profile_face(
        self,
        spec: ProfileSpec,
        *,
        anchor_override: Any = None,
        normal_override: Any = None,
    ) -> tuple[Any, Any]:
        """Compile a normalized profile through Edge -> closed Wire -> planar Face."""
        Vector = self.FreeCAD.Vector
        rotation = self._plane_frame(spec.plane)
        normal = (
            normal_override.normalize()
            if normal_override is not None
            else rotation.multVec(Vector(0, 0, 1)).normalize()
        )
        anchor = anchor_override if anchor_override is not None else self._resolve_anchor(spec.anchor, normal)

        try:
            if spec.kind == "circle":
                edge = self.Part.makeCircle(spec.radius, anchor, normal)
                wire = self.Part.Wire([edge])
            elif spec.kind == "polygon":
                points = [anchor + rotation.multVec(Vector(x, y, 0)) for x, y in spec.vertices]
                edges = [
                    self.Part.makeLine(points[index], points[(index + 1) % len(points)])
                    for index in range(len(points))
                ]
                wire = self.Part.Wire(edges)
            else:
                raise CompileError(f"unsupported normalized profile kind: {spec.kind}")
            if not wire.isClosed():
                raise CompileError("profile edges do not form a closed wire")
            face = self.Part.Face(wire)
            if face.isNull() or not face.isValid() or face.Area <= 0:
                raise CompileError("profile did not produce a valid planar face")
        except CompileError:
            raise
        except Exception as exc:
            raise CompileError("profile did not produce a valid planar face") from exc
        return face, normal

    def resolve_role(self, value: Any) -> ResolvedSubshape:
        """Resolve a symbolic role against the current tip with provenance evidence."""
        if not isinstance(value, Ref) or len(value.path) != 2:
            raise CompileError(f"expected a <feature>.<role> reference, got {value}")
        root, role = value.path
        obj = self.objects.get(root)
        if obj is None or not hasattr(obj, "Shape"):
            raise CompileError(f"subshape target is not a compiled solid: {value}")
        if root not in self.axes:
            raise CompileError(f"subshape target has no feature axis: {value}")
        _, direction = self.axes[root]
        try:
            return self.subshape_resolver.resolve(
                feature=root,
                operation=self.feature_ops.get(root, "unknown"),
                history_version=self.history_versions.get(root, 0),
                role=role,
                shape=obj.Shape,
                axis=direction,
            )
        except SubshapeResolutionError as exc:
            raise CompileError(str(exc)) from exc
        except Exception as exc:
            raise CompileError(f"subshape resolution failed for {value}: {exc}") from exc

    def _source_for_role(self, value: Any, op: str, role: str) -> tuple[str, Any, ResolvedSubshape]:
        """Resolve ``on=<feature>.<role>`` to the current solid and exact subshape."""
        if not isinstance(value, Ref) or len(value.path) != 2 or value.path[1] != role:
            raise CompileError(f"{op} on must reference <feature>.{role}, got {value}")
        root = value.path[0]
        obj = self.objects.get(root)
        if obj is None or not hasattr(obj, "Shape"):
            raise CompileError(f"{op} target is not a compiled solid: {value}")
        return root, obj, self.resolve_role(value)

    def _replace_tip(self, name: str, operation: str, source: Any, shape: Any) -> Any:
        """Append a PartDesign feature and make every source alias see the new tip."""
        # Boolean operations may wrap one valid solid in a Compound. Feeding
        # that wrapper to later Part fillet/chamfer calls produces bad topology.
        if shape.ShapeType != "Solid" and len(shape.Solids) == 1:
            shape = shape.Solids[0]
        if shape.isNull() or not shape.isValid():
            raise CompileError(f"{name} produced an invalid solid")
        obj = self.doc.addObject("PartDesign::Feature", name)
        obj.Shape = shape
        for alias, current in list(self.objects.items()):
            if current is source:
                self.objects[alias] = obj
                self.history_versions[alias] = self.history_versions.get(alias, 0) + 1
        for active_name, current in list(self.active_solids.items()):
            if current is source:
                del self.active_solids[active_name]
        self.objects[name] = obj
        self.active_solids[name] = obj
        self.feature_ops[name] = operation
        self.history_versions[name] = self._active_revision
        return obj

    def _pocket(self, name: str, args: dict[str, Any]) -> Any:
        self._check_profile_args(args, {"on", "circle", "depth"}, "pocket")
        root, source, top = self._source_for_role(args.get("on"), "pocket", "face_top")
        circle = args.get("circle")
        if not isinstance(circle, dict):
            raise CompileError("pocket currently supports circle=[center=..., r=...]")
        depth = self._positive(args.get("depth"), "pocket depth")
        base, direction = self.axes[root]
        direction = direction.normalize()
        top_projection = top.require_one().CenterOfMass.dot(direction)
        top_center = base + direction * (top_projection - base.dot(direction))
        bottom = self.resolve_role(Ref([root, "face_bottom"]))
        axial_thickness = top_projection - bottom.require_one().CenterOfMass.dot(direction)
        if depth >= axial_thickness - 1e-7:
            raise CompileError(f"pocket depth must leave a floor; target thickness is {axial_thickness:g} mm")

        center = circle.get("center")
        if isinstance(center, Ref) and center.path == [root, "axis"]:
            cutter_center = top_center
        elif isinstance(center, Ref) and center.path == ["origin"]:
            cutter_center = direction * top_projection
        else:
            raise CompileError(f"pocket circle center must be origin or {root}.axis, got {center}")
        spec = self._circle_spec(circle)
        # Pocket and extrude intentionally share the same analytic Edge -> Wire
        # -> Face compiler. Only the placement and extrusion vector differ.
        face, _ = self._profile_face(spec, anchor_override=cutter_center, normal_override=direction)
        top_face = top.require_one()
        overlap = top_face.common(face)
        area_tolerance = max(1e-8, face.Area * 1e-9)
        if overlap.isNull() or abs(overlap.Area - face.Area) > area_tolerance:
            raise CompileError("pocket profile is not fully contained by the target face")
        clearance = top_face.OuterWire.distToShape(face.OuterWire)[0]
        if clearance <= 1e-7:
            raise CompileError("pocket profile has insufficient clearance from the target boundary")
        cutter = face.extrude(-direction * depth)
        cut = self._checked_cut(source.Shape, cutter, "pocket")
        self._require_roles(cut, direction, "pocket", ("floor", "wall"))
        result = self._replace_tip(name, "pocket", source, cut)
        self.axes[name] = (cutter_center - direction * (depth / 2), direction)
        self.modifier_tools[name] = cutter
        self.modifier_sources[name] = root
        return result

    def _fillet(self, name: str, args: dict[str, Any]) -> Any:
        self._check_profile_args(args, {"on", "radius"}, "fillet")
        root, source, edges = self._source_for_role(args.get("on"), "fillet", "edge_top")
        radius = self._positive(args.get("radius"), "fillet radius")
        # `edge_top` is the selected top face's complete outer wire. Holes are
        # inner wires and never enter this set; multi-edge polygon rims are
        # intentionally returned as a cardinality-many binding.
        result = self._replace_tip(
            name, "fillet", source, source.Shape.makeFillet(radius, list(edges.entities))
        )
        self.axes[name] = self.axes[root]
        return result

    def _chamfer(self, name: str, args: dict[str, Any]) -> Any:
        self._check_profile_args(args, {"on", "dist"}, "chamfer")
        root, source, edges = self._source_for_role(args.get("on"), "chamfer", "edge_top")
        distance = self._positive(args.get("dist"), "chamfer dist")
        try:
            shape = source.Shape.makeChamfer(distance, list(edges.entities))
        except Exception as exc:
            raise CompileError(f"chamfer kernel operation failed: {exc}") from exc
        if shape.isNull() or not shape.isValid() or not shape.Solids:
            raise CompileError("chamfer produced an invalid or empty B-rep")
        if shape.Volume >= source.Shape.Volume - self._volume_tolerance(source.Shape):
            raise CompileError("chamfer did not remove a measurable volume")
        result = self._replace_tip(name, "chamfer", source, shape)
        self.axes[name] = self.axes[root]
        return result

    def _revolve(self, name: str, args: dict[str, Any]) -> Any:
        self._check_profile_args(args, {"profile", "axis", "angle"}, "revolve")
        spec = self._profile_spec(args.get("profile"))
        face, normal = self._profile_face(spec)
        base, direction = self._axis_line(args.get("axis"), profile=spec, what="revolve axis")
        if abs(normal.dot(direction)) > 1e-8:
            raise CompileError("revolve axis must lie in the profile plane")
        if abs((base - face.CenterOfMass).dot(normal)) > 1e-7:
            raise CompileError("revolve axis base must lie in the profile plane")
        angle = self._angle(args.get("angle"), "revolve angle")
        try:
            shape = face.revolve(base, direction, angle)
        except Exception as exc:
            raise CompileError(f"revolve kernel operation failed: {exc}") from exc
        if shape.ShapeType != "Solid" and len(shape.Solids) == 1:
            shape = shape.Solids[0]
        if shape.isNull() or not shape.isValid() or len(shape.Solids) != 1 or shape.Volume <= 1e-8:
            raise CompileError("revolve did not produce one valid nonzero solid")
        self._require_roles(
            shape,
            direction,
            "revolve",
            ("face_top", "face_bottom", "edge_top", "edge_bottom", "wall"),
        )
        obj = self.doc.addObject("PartDesign::Feature", name)
        obj.Shape = shape
        self.objects[name] = obj
        self.active_solids[name] = obj
        self.axes[name] = (base, direction)
        self.feature_ops[name] = "revolve"
        self.history_versions[name] = self._active_revision
        return obj

    def _groove(self, name: str, args: dict[str, Any]) -> Any:
        self._check_profile_args(args, {"on", "profile", "axis"}, "groove")
        root, source, _ = self._source_for_role(args.get("on"), "groove", "face_top")
        spec = self._profile_spec(args.get("profile"))
        face, normal = self._profile_face(spec)
        base, direction = self._axis_line(args.get("axis"), profile=spec, what="groove axis")
        if abs(normal.dot(direction)) > 1e-8:
            raise CompileError("groove axis must lie in the profile plane")
        if abs((base - face.CenterOfMass).dot(normal)) > 1e-7:
            raise CompileError("groove axis base must lie in the profile plane")
        try:
            cutter = face.revolve(base, direction, 360.0)
        except Exception as exc:
            raise CompileError(f"groove cutter revolution failed: {exc}") from exc
        cut = self._checked_cut(source.Shape, cutter, "groove")
        self._require_roles(cut, direction, "groove", ("floor", "wall"))
        result = self._replace_tip(name, "groove", source, cut)
        self.axes[name] = self.axes[root]
        self.modifier_tools[name] = cutter
        self.modifier_sources[name] = root
        return result

    def _linear_pattern_step(self, value: Any, axis: Any) -> Any:
        Vector = self.FreeCAD.Vector
        if isinstance(value, list):
            if len(value) != 3:
                raise CompileError("linear pattern spacing list must be [x, y, z]")
            components = [
                self._linear_number(item, f"pattern spacing[{index}]") for index, item in enumerate(value)
            ]
            step = Vector(*components)
        else:
            step = axis.normalize() * self._positive(value, "pattern spacing")
        if step.Length <= 1e-9:
            raise CompileError("linear pattern spacing vector must be nonzero")
        return step

    def _pattern_transforms(self, args: dict[str, Any], axis_line: tuple[Any, Any]) -> list[tuple[str, Any]]:
        pattern_type = args.get("type")
        if not isinstance(pattern_type, Ref) or len(pattern_type.path) != 1:
            raise CompileError(f"pattern type must be linear or circular, got {pattern_type}")
        count = self._count(args.get("count"), "pattern count")
        base, axis = axis_line
        if pattern_type.path[0] == "linear":
            self._check_profile_args(args, {"feature", "type", "count", "spacing"}, "pattern")
            step = self._linear_pattern_step(args.get("spacing"), axis)
            return [("translate", step * index) for index in range(1, count)]
        if pattern_type.path[0] == "circular":
            self._check_profile_args(args, {"feature", "type", "count", "angle"}, "pattern")
            angle = self._angle(args.get("angle"), "pattern angle")
            if (count - 1) * angle >= 360.0 - 1e-9:
                raise CompileError("circular pattern placements must stay below one full turn")
            return [("rotate", (base, axis, angle * index)) for index in range(1, count)]
        raise CompileError(f"pattern type must be linear or circular, got {pattern_type}")

    @staticmethod
    def _transform_shape(shape: Any, transform: tuple[str, Any]) -> Any:
        result = shape.copy()
        kind, value = transform
        if kind == "translate":
            result.translate(value)
        else:
            base, axis, angle = value
            result.rotate(base, axis, angle)
        return result

    def _pattern(self, name: str, args: dict[str, Any]) -> Any:
        feature = self._whole_ref(args.get("feature"), "pattern feature")
        source = self.objects.get(feature)
        if source is None or not hasattr(source, "Shape"):
            raise CompileError(f"pattern feature is not a compiled solid: {feature}")
        axis_line = self.axes.get(feature)
        if axis_line is None:
            raise CompileError(f"pattern feature has no axis: {feature}")
        transforms = self._pattern_transforms(args, axis_line)
        if feature in self.modifier_tools:
            tool = self.modifier_tools[feature]
            additions = [self._transform_shape(tool, transform) for transform in transforms]
            aggregate = tool
            for addition in additions:
                aggregate = aggregate.fuse(addition)
            result_shape = self._checked_cut(source.Shape, aggregate, "pattern")
            root = self.modifier_sources[feature]
            result = self._replace_tip(name, "pattern", source, result_shape)
            self.modifier_tools[name] = aggregate
            self.modifier_sources[name] = root
        else:
            additions = [self._transform_shape(source.Shape, transform) for transform in transforms]
            result_shape = self._checked_union(source.Shape, additions, "pattern")
            result = self._replace_tip(name, "pattern", source, result_shape)
        self.axes[name] = axis_line
        return result

    @staticmethod
    def _mirror_plane(value: Any, vector: Any) -> tuple[Any, Any]:
        if not isinstance(value, Ref) or len(value.path) != 1:
            raise CompileError(f"mirror plane must be XY, XZ, or YZ, got {value}")
        normals = {"XY": (0, 0, 1), "XZ": (0, 1, 0), "YZ": (1, 0, 0)}
        try:
            normal = normals[value.path[0]]
        except KeyError:
            raise CompileError(f"mirror plane must be XY, XZ, or YZ, got {value}") from None
        return vector(0, 0, 0), vector(*normal)

    def _mirror(self, name: str, args: dict[str, Any]) -> Any:
        self._check_profile_args(args, {"feature", "plane"}, "mirror")
        feature = self._whole_ref(args.get("feature"), "mirror feature")
        source = self.objects.get(feature)
        if source is None or not hasattr(source, "Shape"):
            raise CompileError(f"mirror feature is not a compiled solid: {feature}")
        plane_base, plane_normal = self._mirror_plane(args.get("plane"), self.FreeCAD.Vector)
        if feature in self.modifier_tools:
            tool = self.modifier_tools[feature]
            mirrored_tool = tool.mirror(plane_base, plane_normal)
            aggregate = tool.fuse(mirrored_tool)
            result_shape = self._checked_cut(source.Shape, aggregate, "mirror")
            root = self.modifier_sources[feature]
            result = self._replace_tip(name, "mirror", source, result_shape)
            self.modifier_tools[name] = aggregate
            self.modifier_sources[name] = root
        else:
            mirrored = source.Shape.mirror(plane_base, plane_normal)
            result_shape = self._checked_union(source.Shape, [mirrored], "mirror")
            result = self._replace_tip(name, "mirror", source, result_shape)
        self.axes[name] = self.axes[feature]
        return result

    def _constraint(self, name: str, args: dict[str, Any]) -> ConstraintRecord:
        self._check_profile_args(args, {"type", "on", "value"}, "constraint")
        constraint_type = args.get("type")
        target = args.get("on")
        if not isinstance(constraint_type, Ref) or constraint_type.path not in (["dim"], ["geom"]):
            raise CompileError(f"constraint type must be dim or geom, got {constraint_type}")
        if not isinstance(target, Ref):
            raise CompileError("constraint on must be a symbolic reference")
        value = args.get("value")
        if constraint_type.path == ["dim"]:
            if isinstance(value, Quantity) and value.unit not in {None, "mm"}:
                raise CompileError(f"dim constraint value must use mm, got {value.unit}")
            self._number(value)
        else:
            allowed = {"concentric", "coplanar", "parallel"}
            if not isinstance(value, Ref) or value.path[0] not in allowed or len(value.path) != 1:
                raise CompileError("geom constraint value must be concentric, coplanar, or parallel")
        record = ConstraintRecord(
            constraint_type=constraint_type.path[0],
            target=deepcopy(target),
            value=deepcopy(value),
            history_version=self._active_revision,
        )
        self.constraints.append(record)
        self.feature_ops[name] = "constraint"
        self.history_versions[name] = self._active_revision
        return record

    def _remember_feature(self, name: str, op: str, args: dict[str, Any]) -> None:
        if not self._replaying_history:
            self.feature_history.append(KernelFeatureRecord(name, op, deepcopy(args)))

    def _history_index(self, target: str) -> int:
        for index, record in enumerate(self.feature_history):
            if record.name == target:
                return index
        raise CompileError(f"feature history does not contain target: {target}")

    def _rebuild_from_history(self) -> None:
        """Regenerate the complete current tip from replayable authored records."""
        records = list(self.feature_history)
        self._clear_runtime_geometry()
        self._replaying_history = True
        try:
            for record in records:
                self._active_revision = record.revision
                self.feature(record.name, record.op, deepcopy(record.args))
            self.doc.recompute()
        finally:
            self._active_revision = 1
            self._replaying_history = False

    def _mutate_history(self, target_index: int, mutate: Any) -> None:
        """Apply one history mutation transactionally, rebuilding or rolling back."""
        snapshot = deepcopy(self.feature_history)
        mutate(self.feature_history[target_index])
        for record in self.feature_history[target_index:]:
            record.revision += 1
        try:
            self._rebuild_from_history()
            self.finish()
        except Exception:
            self.feature_history = snapshot
            self._rebuild_from_history()
            raise

    def feature(self, name: str, op: str, args: dict[str, Any]) -> Any:
        if op == "sketch":
            self.objects[name] = self._profile_from_sketch(args)
            self.feature_ops[name] = op
            self.history_versions[name] = self._active_revision
            self._remember_feature(name, op, args)
            return self.objects[name]
        if op == "extrude":
            self._check_profile_args(args, {"profile", "length", "dir"}, "extrude")
            profile = args.get("profile")
            length = self._positive(args.get("length"), "extrude length")
            spec = self._profile_spec(profile)
            face, normal = self._profile_face(spec)
            direction = self._extrusion_direction(args, normal)
            shape = face.extrude(direction * length)

            obj = self.doc.addObject("PartDesign::Feature", name)
            obj.Shape = shape
            self.objects[name] = obj
            self.active_solids[name] = obj
            self.axes[name] = (obj.Shape.CenterOfMass, direction)
            self.feature_ops[name] = op
            self.history_versions[name] = self._active_revision
            self._remember_feature(name, op, args)
            return obj
        if op == "revolve":
            result = self._revolve(name, args)
            self._remember_feature(name, op, args)
            return result
        if op == "pocket":
            result = self._pocket(name, args)
            self._remember_feature(name, op, args)
            return result
        if op == "fillet":
            result = self._fillet(name, args)
            self._remember_feature(name, op, args)
            return result
        if op == "chamfer":
            result = self._chamfer(name, args)
            self._remember_feature(name, op, args)
            return result
        if op == "groove":
            result = self._groove(name, args)
            self._remember_feature(name, op, args)
            return result
        if op == "pattern":
            result = self._pattern(name, args)
            self._remember_feature(name, op, args)
            return result
        if op == "mirror":
            result = self._mirror(name, args)
            self._remember_feature(name, op, args)
            return result
        if op == "constraint":
            result = self._constraint(name, args)
            self._remember_feature(name, op, args)
            return result
        raise CompileError(f"FreeCAD backend operation not implemented: {op}")

    def edit(self, target: str, field_name: str, value: Any) -> None:
        target_index = self._history_index(target)
        record = self.feature_history[target_index]
        if field_name not in record.args:
            raise CompileError(f"edit field does not exist on {target}: {field_name}")

        def mutate(feature: KernelFeatureRecord) -> None:
            feature.args[field_name] = deepcopy(value)

        self._mutate_history(target_index, mutate)

    def replace(self, target: str, op: str, args: dict[str, Any]) -> Any:
        target_index = self._history_index(target)

        def mutate(feature: KernelFeatureRecord) -> None:
            feature.op = op
            feature.args = deepcopy(args)

        self._mutate_history(target_index, mutate)
        return self.objects[target]

    def finish(self) -> Any:
        """Return the whole model, fusing every solid the program built.

        Returning one body would silently hand downstream measurement a fragment
        of the described part, and which fragment would depend on declaration
        order rather than on modelling intent.
        """
        self.doc.recompute()
        solids = [obj.Shape for obj in self.active_solids.values()]
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
    # A backend we mint here is ours to release; one the caller passed in is not.
    owned = backend is None
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
    finally:
        # Failed compiles leaked too, which is exactly the shape of a self-repair loop.
        if owned:
            active_backend.close()
