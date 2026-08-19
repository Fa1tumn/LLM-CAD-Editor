"""Stable symbolic-reference registry used by compilation and evaluation."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .ast import OpCall, Ref, Statement

ROLES = {"face_top", "face_bottom", "axis", "wall", "floor", "edge_top", "edge_bottom"}
OP_ROLES: dict[str, set[str]] = {
    "sketch": set(),
    "extrude": {"face_top", "face_bottom", "wall", "axis", "edge_top", "edge_bottom"},
    "revolve": {"face_top", "face_bottom", "wall", "axis", "edge_top", "edge_bottom"},
    "pocket": {"wall", "floor"}, "groove": {"wall", "floor"},
    "fillet": set(), "chamfer": set(),
}
LITERAL_ROOTS = {
    "XY", "XZ", "YZ", "origin", "linear", "circular", "dim", "geom",
    "equal", "range", "ratio", "concentric", "coplanar", "parallel",
    "length", "radius", "depth", "dist", "angle", "count", "spacing",
}


class ReferenceError(ValueError):
    """A statement contains a dangling or conflicting symbolic reference."""


def iter_refs(value: Any) -> Iterable[Ref]:
    if isinstance(value, Ref):
        yield value
    elif isinstance(value, OpCall):
        yield from iter_refs(value.args)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_refs(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_refs(item)


def _rewrite_refs(value: Any, old: str, new: str) -> None:
    for ref in iter_refs(value):
        if ref.path and ref.path[0] == old:
            ref.path[0] = new


class ReferenceRegistry:
    def __init__(self) -> None:
        self._features: dict[str, set[str]] = {}
        self._deps: dict[str, set[str]] = {}  # owner -> referenced feature roots

    def clone(self) -> "ReferenceRegistry":
        return deepcopy(self)

    def add_feature(self, name: str, roles: set[str], dependencies: Iterable[str] = ()) -> None:
        if name in self._features:
            raise ReferenceError(f"feature already exists: {name}")
        unknown = set(roles) - ROLES
        if unknown:
            raise ReferenceError(f"unknown derived role(s): {', '.join(sorted(unknown))}")
        self._features[name] = set(roles)
        self._deps[name] = set(dependencies)

    def is_valid(self, ref_path: list[str]) -> bool:
        if not ref_path or ref_path[0] not in self._features:
            return False
        return len(ref_path) == 1 or (len(ref_path) == 2 and ref_path[1] in self._features[ref_path[0]])

    def valid_refs(self) -> list[str]:
        out: list[str] = []
        for feat in sorted(self._features):
            out.append(feat)
            out.extend(f"{feat}.{role}" for role in sorted(self._features[feat]))
        return out

    def validate_refs(self, value: Any) -> set[str]:
        dependencies: set[str] = set()
        for ref in iter_refs(value):
            if not ref.path:
                raise ReferenceError("empty reference")
            root = ref.path[0]
            if root in LITERAL_ROOTS:
                continue
            if not self.is_valid(ref.path):
                raise ReferenceError(f"dangling reference: {ref}")
            if ref.index is not None and len(ref.path) != 1:
                raise ReferenceError(f"instance selector must follow a feature name: {ref}")
            dependencies.add(root)
        return dependencies

    def register(self, statement: Statement) -> None:
        if statement.op == "replace":
            target, replacement = statement.args.get("target"), statement.args.get("with")
            if not isinstance(target, Ref) or len(target.path) != 1 or target.index is not None:
                raise ReferenceError("replace target must be a whole-feature reference")
            if not isinstance(replacement, OpCall):
                raise ReferenceError("replace `with` must be an operation call")
            self.validate_refs(replacement.args)
            conflicts = self.replace_feature(target.path[0], OP_ROLES.get(replacement.op, set()))
            if conflicts:
                raise ReferenceError(
                    f"re-binding conflict for {target.path[0]}: missing roles {', '.join(conflicts)}"
                )
            return

        dependencies = self.validate_refs(statement.args)
        if statement.name is not None:
            roles = OP_ROLES.get(statement.op, set())
            if statement.op in {"pattern", "mirror"}:
                source = statement.args.get("feature")
                if isinstance(source, Ref) and source.path[0] in self._features:
                    roles = set(self._features[source.path[0]])
            self.add_feature(statement.name, roles, dependencies)

    def replace_feature(self, name: str, new_roles: set[str]) -> list[str]:
        if name not in self._features:
            raise ReferenceError(f"cannot replace missing feature: {name}")
        # Any old role used downstream must still be exposed by the replacement.
        used_roles: set[str] = set()
        # Dependency roots alone cannot retain role granularity, so conservatively
        # require the old role set whenever there is a downstream dependent.
        if any(name in dependencies for dependencies in self._deps.values()):
            used_roles = self._features[name]
        conflicts = sorted(used_roles - new_roles)
        self._features[name] = set(new_roles)
        return conflicts

    def rebind(self, old: str, new: str, statements: Iterable[Statement] = ()) -> list[str]:
        """Rename a feature and rewrite dependency edges and downstream AST Refs."""
        if old not in self._features:
            raise ReferenceError(f"cannot rebind missing feature: {old}")
        if new != old and new in self._features:
            raise ReferenceError(f"rebind destination already exists: {new}")
        if new != old:
            self._features[new] = self._features.pop(old)
            self._deps[new] = self._deps.pop(old, set())
        for dependencies in self._deps.values():
            if old in dependencies:
                dependencies.remove(old)
                dependencies.add(new)
        for statement in statements:
            _rewrite_refs(statement.args, old, new)
        return []

    @property
    def features(self) -> frozenset[str]:
        return frozenset(self._features)
