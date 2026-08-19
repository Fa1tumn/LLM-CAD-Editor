"""
VLM visual review — stage 3 of the four-stage loop.

Hands the before/after render images to a VLM to judge whether the
instruction was satisfied and whether the edit over-reached.
This turns prior work's "VLM for evaluation" into a stage of the
operating loop itself.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class VisualResult:
    ok: bool
    score: int          # 1~5
    reason: str = ""


def check(before_png: bytes, after_png: bytes, instruction: str, cfg: dict) -> VisualResult:
    # TODO(M6): render before/after images → VLM score, threshold cfg["verify"]["visual"]["vlm_pass_score"]
    raise NotImplementedError
