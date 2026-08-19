"""
Type-preservation check — stage 4 of the four-stage loop (a unique
contribution of this work).

Reuses the "stage 1 of the evolution roadmap" part classifier to confirm,
e.g., that an edited shaft is still a shaft and an edited bracket is still
a bracket. Only holds under this roadmap's cumulative structure; absent
from prior work.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TypeResult:
    ok: bool
    before_type: str
    after_type: str


def check(before_solid, after_solid, classifier) -> TypeResult:
    # TODO(M6): call the prior-stage classifier, compare types before/after the edit
    raise NotImplementedError
