"""
Metric computation.

- IoU: mesh IoU between the edit result and the reference
- parse rate
- reference-break rate (G3)
- defect recall & false-positive (G4)

Corresponds to proposal §4.2 quantitative targets G1–G6.
All metrics are measured only on held-out real parts.
"""
from __future__ import annotations


def iou(result_solid, reference_solid) -> float:
    # TODO(M3): voxelize with trimesh, then compute IoU
    raise NotImplementedError


def parse_rate(results: list[bool]) -> float:
    return sum(results) / len(results) if results else 0.0


def defect_recall(detected: int, injected: int) -> float:
    """Injected-defect recall (target ≥95%, G4)."""
    return detected / injected if injected else 0.0
