"""Resolve stable symbolic roles to provenance-carrying OCCT subshapes (P0/P2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Literal

Cardinality = Literal["one", "many"]


class SubshapeResolutionError(Exception):
    """A symbolic role has zero or ambiguous kernel matches."""


@dataclass(frozen=True)
class ResolutionStep:
    """One auditable filter in a role-to-subshape resolution."""

    name: str
    input_count: int
    output_count: int
    detail: str


@dataclass(frozen=True)
class GeometricSignature:
    """Geometry-only description used for stable ordering and diagnostics."""

    topology_kind: str
    geometry_kind: str
    centroid: tuple[float, float, float]
    measure: float
    orientation: tuple[float, float, float] | None
    bounds: tuple[float, float, float, float, float, float]

    def stable_key(self) -> tuple[Any, ...]:
        return (
            self.topology_kind,
            self.geometry_kind,
            self.centroid,
            self.measure,
            self.orientation or (),
            self.bounds,
        )


@dataclass(frozen=True)
class SubshapeProvenance:
    """Where a role binding came from and which geometry revision it used."""

    source_feature: str
    source_operation: str
    history_version: int
    source_shape_hash: str
    role: str
    reason: str


@dataclass(frozen=True)
class ResolvedSubshape:
    """One named-role result with explicit cardinality and selection evidence."""

    provenance: SubshapeProvenance
    topology_kind: str
    expected_cardinality: Cardinality
    candidate_count: int
    signatures: tuple[GeometricSignature, ...]
    steps: tuple[ResolutionStep, ...]
    entities: tuple[Any, ...] = field(repr=False, compare=False)

    @property
    def count(self) -> int:
        return len(self.entities)

    def require_one(self) -> Any:
        """Return the sole entity without ever silently choosing from many."""
        if self.count != 1:
            raise SubshapeResolutionError(
                f"{self.provenance.source_feature}.{self.provenance.role} expected exactly one "
                f"{self.topology_kind}, matched {self.count}"
            )
        return self.entities[0]


class SubshapeResolver:
    """Resolve v1 semantic roles from the current OCCT B-rep with audit evidence."""

    _TOLERANCE = 1e-7

    @staticmethod
    def _vector_tuple(vector: Any) -> tuple[float, float, float]:
        return tuple(round(float(value), 9) for value in (vector.x, vector.y, vector.z))

    @staticmethod
    def _bounds_tuple(shape: Any) -> tuple[float, float, float, float, float, float]:
        bounds = shape.BoundBox
        return tuple(
            round(float(value), 9)
            for value in (
                bounds.XMin,
                bounds.YMin,
                bounds.ZMin,
                bounds.XMax,
                bounds.YMax,
                bounds.ZMax,
            )
        )

    @staticmethod
    def _face_normal(face: Any) -> Any:
        u_min, u_max, v_min, v_max = face.ParameterRange
        return face.normalAt((u_min + u_max) / 2, (v_min + v_max) / 2).normalize()

    def _signature(self, entity: Any) -> GeometricSignature:
        topology_kind = entity.ShapeType
        geometry = entity.Surface if topology_kind == "Face" else entity.Curve
        geometry_kind = getattr(geometry, "TypeId", type(geometry).__name__)
        orientation = None
        if topology_kind == "Face":
            orientation = self._vector_tuple(self._face_normal(entity))
            measure = entity.Area
        elif topology_kind == "Edge":
            first, last = entity.ParameterRange
            orientation = self._vector_tuple(entity.tangentAt((first + last) / 2))
            measure = entity.Length
        else:
            raise SubshapeResolutionError(f"unsupported topology kind for signature: {topology_kind}")
        return GeometricSignature(
            topology_kind=topology_kind,
            geometry_kind=geometry_kind,
            centroid=self._vector_tuple(entity.CenterOfMass),
            measure=round(float(measure), 9),
            orientation=orientation,
            bounds=self._bounds_tuple(entity),
        )

    @staticmethod
    def _shape_hash(shape: Any) -> str:
        return sha256(shape.exportBrepToString().encode("utf-8")).hexdigest()

    @staticmethod
    def _same(first: Any, second: Any) -> bool:
        return bool(first.isSame(second))

    def _shares_edge(self, first: Any, second: Any) -> bool:
        return any(
            self._same(first_edge, second_edge) for first_edge in first.Edges for second_edge in second.Edges
        )

    def _result(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        role: str,
        shape: Any,
        topology_kind: str,
        expected: Cardinality,
        candidates: list[Any],
        candidate_count: int,
        steps: list[ResolutionStep],
        reason: str,
    ) -> ResolvedSubshape:
        if expected == "one" and len(candidates) != 1:
            raise SubshapeResolutionError(
                f"{feature}.{role} expected exactly one {topology_kind}, matched {len(candidates)}"
            )
        if expected == "many" and not candidates:
            raise SubshapeResolutionError(
                f"{feature}.{role} expected one or more {topology_kind}s, matched 0"
            )
        paired = sorted(
            ((self._signature(entity), entity) for entity in candidates),
            key=lambda item: item[0].stable_key(),
        )
        signatures = tuple(signature for signature, _ in paired)
        entities = tuple(entity for _, entity in paired)
        return ResolvedSubshape(
            provenance=SubshapeProvenance(
                source_feature=feature,
                source_operation=operation,
                history_version=history_version,
                source_shape_hash=self._shape_hash(shape),
                role=role,
                reason=reason,
            ),
            topology_kind=topology_kind,
            expected_cardinality=expected,
            candidate_count=candidate_count,
            signatures=signatures,
            steps=tuple(steps),
            entities=entities,
        )

    def _cap(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        role: str,
        shape: Any,
        axis: Any,
        maximum: bool,
    ) -> ResolvedSubshape:
        faces = list(shape.Faces)
        planar = [face for face in faces if getattr(face.Surface, "TypeId", "") == "Part::GeomPlane"]
        steps = [ResolutionStep("planar", len(faces), len(planar), "surface type is Part::GeomPlane")]
        sign = 1 if maximum else -1
        oriented = [
            face for face in planar if self._face_normal(face).dot(axis) * sign >= 1 - self._TOLERANCE
        ]
        steps.append(
            ResolutionStep(
                "outward_normal",
                len(planar),
                len(oriented),
                f"normal is parallel to {'+' if maximum else '-'} feature axis",
            )
        )
        selected: list[Any] = []
        if oriented:
            projections = [face.CenterOfMass.dot(axis) for face in oriented]
            extremum = (max if maximum else min)(projections)
            selected = [
                face
                for face, projection in zip(oriented, projections, strict=True)
                if abs(projection - extremum) <= self._TOLERANCE
            ]
        steps.append(
            ResolutionStep(
                "axial_extremum",
                len(oriented),
                len(selected),
                f"centroid lies at {'maximum' if maximum else 'minimum'} axis projection",
            )
        )
        return self._result(
            feature=feature,
            operation=operation,
            history_version=history_version,
            role=role,
            shape=shape,
            topology_kind="Face",
            expected="one",
            candidates=selected,
            candidate_count=len(faces),
            steps=steps,
            reason=f"unique planar cap at the {'maximum' if maximum else 'minimum'} feature-axis extent",
        )

    def _floor(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        shape: Any,
        axis: Any,
    ) -> ResolvedSubshape:
        faces = list(shape.Faces)
        planar = [face for face in faces if getattr(face.Surface, "TypeId", "") == "Part::GeomPlane"]
        upward = [face for face in planar if self._face_normal(face).dot(axis) >= 1 - self._TOLERANCE]
        steps = [
            ResolutionStep("planar", len(faces), len(planar), "surface type is Part::GeomPlane"),
            ResolutionStep("upward_normal", len(planar), len(upward), "normal is parallel to +axis"),
        ]
        below_top: list[Any] = []
        if upward:
            top = max(face.CenterOfMass.dot(axis) for face in upward)
            below_top = [face for face in upward if face.CenterOfMass.dot(axis) < top - self._TOLERANCE]
        steps.append(ResolutionStep("below_top", len(upward), len(below_top), "exclude the outer top cap"))
        selected: list[Any] = []
        if below_top:
            floor_projection = max(face.CenterOfMass.dot(axis) for face in below_top)
            selected = [
                face
                for face in below_top
                if abs(face.CenterOfMass.dot(axis) - floor_projection) <= self._TOLERANCE
            ]
        steps.append(
            ResolutionStep(
                "nearest_floor",
                len(below_top),
                len(selected),
                "nearest upward planar face below the top cap",
            )
        )
        return self._result(
            feature=feature,
            operation=operation,
            history_version=history_version,
            role="floor",
            shape=shape,
            topology_kind="Face",
            expected="one",
            candidates=selected,
            candidate_count=len(faces),
            steps=steps,
            reason="unique upward-facing pocket floor below the top cap",
        )

    def _boundary_edges(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        role: str,
        shape: Any,
        cap: ResolvedSubshape,
    ) -> ResolvedSubshape:
        face = cap.require_one()
        edges = list(face.OuterWire.Edges)
        return self._result(
            feature=feature,
            operation=operation,
            history_version=history_version,
            role=role,
            shape=shape,
            topology_kind="Edge",
            expected="many",
            candidates=edges,
            candidate_count=len(shape.Edges),
            steps=[
                *cap.steps,
                ResolutionStep(
                    "outer_wire",
                    len(face.Edges),
                    len(edges),
                    "edges belong to the selected cap's outer boundary, excluding holes",
                ),
            ],
            reason=f"outer boundary of the resolved {cap.provenance.role}",
        )

    def _adjacent_walls(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        shape: Any,
        cap: ResolvedSubshape,
        axis: Any,
        reason: str,
    ) -> ResolvedSubshape:
        face = cap.require_one()
        boundary = list(face.OuterWire.Edges)
        lateral = [
            candidate
            for candidate in shape.Faces
            if not self._same(candidate, face)
            and not (
                getattr(candidate.Surface, "TypeId", "") == "Part::GeomPlane"
                and abs(self._face_normal(candidate).dot(axis)) >= 1 - self._TOLERANCE
            )
        ]
        walls = [
            candidate
            for candidate in lateral
            if any(
                self._same(candidate_edge, boundary_edge)
                for candidate_edge in candidate.Edges
                for boundary_edge in boundary
            )
        ]
        # Fillets introduce transition faces between the selected outer wire and
        # the original side wall. Walk the lateral-face adjacency component so
        # the semantic wall survives that topology change without crossing a
        # horizontal cap or an internal pocket floor.
        changed = True
        while changed:
            changed = False
            for candidate in lateral:
                if any(self._same(candidate, selected) for selected in walls):
                    continue
                if any(self._shares_edge(candidate, selected) for selected in walls):
                    walls.append(candidate)
                    changed = True
        return self._result(
            feature=feature,
            operation=operation,
            history_version=history_version,
            role="wall",
            shape=shape,
            topology_kind="Face",
            expected="many",
            candidates=walls,
            candidate_count=len(shape.Faces),
            steps=[
                *cap.steps,
                ResolutionStep(
                    "lateral_faces",
                    len(shape.Faces) - 1,
                    len(lateral),
                    "exclude axis-normal planar caps and floors",
                ),
                ResolutionStep(
                    "boundary_component",
                    len(lateral),
                    len(walls),
                    "connected to the selected outer boundary through lateral-face adjacency",
                ),
            ],
            reason=reason,
        )

    def _groove_floor(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        shape: Any,
        axis: Any,
    ) -> ResolvedSubshape:
        """Resolve the deepest cylindrical surface of an axisymmetric groove."""
        faces = list(shape.Faces)
        cylinders = [face for face in faces if getattr(face.Surface, "TypeId", "") == "Part::GeomCylinder"]
        coaxial = []
        for face in cylinders:
            surface_axis = face.Surface.Axis.normalize()
            if surface_axis.cross(axis).Length <= self._TOLERANCE:
                coaxial.append(face)
        selected: list[Any] = []
        if coaxial:
            minimum_radius = min(float(face.Surface.Radius) for face in coaxial)
            selected = [
                face
                for face in coaxial
                if abs(float(face.Surface.Radius) - minimum_radius) <= self._TOLERANCE
            ]
        return self._result(
            feature=feature,
            operation=operation,
            history_version=history_version,
            role="floor",
            shape=shape,
            topology_kind="Face",
            expected="one",
            candidates=selected,
            candidate_count=len(faces),
            steps=[
                ResolutionStep(
                    "cylindrical",
                    len(faces),
                    len(cylinders),
                    "surface type is Part::GeomCylinder",
                ),
                ResolutionStep(
                    "coaxial",
                    len(cylinders),
                    len(coaxial),
                    "cylinder axis is parallel to the feature axis",
                ),
                ResolutionStep(
                    "minimum_radius",
                    len(coaxial),
                    len(selected),
                    "deepest coaxial cylindrical groove surface",
                ),
            ],
            reason="unique deepest coaxial cylindrical groove floor",
        )

    def _groove_walls(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        shape: Any,
        axis: Any,
    ) -> ResolvedSubshape:
        floor = self._groove_floor(
            feature=feature,
            operation=operation,
            history_version=history_version,
            shape=shape,
            axis=axis,
        )
        floor_face = floor.require_one()
        walls = [
            face
            for face in shape.Faces
            if not self._same(face, floor_face) and self._shares_edge(face, floor_face)
        ]
        return self._result(
            feature=feature,
            operation=operation,
            history_version=history_version,
            role="wall",
            shape=shape,
            topology_kind="Face",
            expected="many",
            candidates=walls,
            candidate_count=len(shape.Faces),
            steps=[
                *floor.steps,
                ResolutionStep(
                    "floor_adjacency",
                    len(shape.Faces) - 1,
                    len(walls),
                    "faces share a boundary edge with the groove floor",
                ),
            ],
            reason="faces bounding both sides of the resolved groove floor",
        )

    def resolve(
        self,
        *,
        feature: str,
        operation: str,
        history_version: int,
        role: str,
        shape: Any,
        axis: Any,
    ) -> ResolvedSubshape:
        """Resolve a v1 role and enforce that role's cardinality contract."""
        direction = axis.normalize()
        common = {
            "feature": feature,
            "operation": operation,
            "history_version": history_version,
            "shape": shape,
            "axis": direction,
        }
        if role == "face_top":
            return self._cap(role=role, maximum=True, **common)
        if role == "face_bottom":
            return self._cap(role=role, maximum=False, **common)
        if role == "edge_top":
            cap = self._cap(role="face_top", maximum=True, **common)
            return self._boundary_edges(
                feature=feature,
                operation=operation,
                history_version=history_version,
                role=role,
                shape=shape,
                cap=cap,
            )
        if role == "edge_bottom":
            cap = self._cap(role="face_bottom", maximum=False, **common)
            return self._boundary_edges(
                feature=feature,
                operation=operation,
                history_version=history_version,
                role=role,
                shape=shape,
                cap=cap,
            )
        if role == "floor":
            if operation == "pocket":
                return self._floor(**common)
            if operation == "groove":
                return self._groove_floor(**common)
        if role == "wall":
            if operation == "pocket":
                floor = self._floor(**common)
                return self._adjacent_walls(
                    feature=feature,
                    operation=operation,
                    history_version=history_version,
                    shape=shape,
                    cap=floor,
                    axis=direction,
                    reason="faces adjacent to the pocket floor outer boundary",
                )
            if operation == "groove":
                return self._groove_walls(**common)
            top = self._cap(role="face_top", maximum=True, **common)
            return self._adjacent_walls(
                feature=feature,
                operation=operation,
                history_version=history_version,
                shape=shape,
                cap=top,
                axis=direction,
                reason="outer faces adjacent to the top cap outer boundary",
            )
        raise SubshapeResolutionError(
            f"kernel subshape role is not implemented for {operation}: {feature}.{role}"
        )
