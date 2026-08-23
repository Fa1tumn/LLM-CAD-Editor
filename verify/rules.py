"""
Dimension-rule verification — stage 2 of the four-stage loop.

Automatically measures:
- hole-center to boundary minimum distance
- min wall thickness
- instruction value vs. measured result consistency

Design requirement: the two failure classes from prior work (boundary-crossing
half-circle holes, pipe-joint gaps) must all be caught by this stage.
Thresholds are in config/default.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RuleResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def check(solid, instruction: dict, cfg: dict) -> RuleResult:
    # TODO(M6): measure with trimesh/shapely and check against cfg["verify"]["rules"]
    raise NotImplementedError
