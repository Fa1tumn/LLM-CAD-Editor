"""
Programmatic compound edit-pair synthesis (RQ1).

Goes beyond prior work's "delete ↔ add" augmentation to synthesize
"delete + add simultaneously" transforms:
- cylinder → prism replacement
- fillet → chamfer conversion
- hole-pattern change

Each pair is kept only if it passes kernel re-run verification
(verify/kernel.py), guaranteeing validity.
"""

from __future__ import annotations


def synthesize_pairs(n: int, out_dir: str) -> int:
    """Synthesize n compound-edit pairs, return #kernel-valid pairs."""
    # TODO(M3): programmatically generate (before_dsl, after_dsl), filter through the kernel
    raise NotImplementedError
