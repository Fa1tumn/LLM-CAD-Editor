"""
3-level instruction generation (VLM).

As in prior work: feed the original/edited model's render-image pair +
DSL pair to a VLM, synthesizing instructions at three levels of
abstraction — parameter / operation / functional. This work adds
compound-edit-specific types (replace / restructure / constraint-preserving).

The levels correspond to proposal Figure 2: parameter level is easiest,
functional level is hardest.
"""
from __future__ import annotations


def generate_instructions(before_dsl: str, after_dsl: str,
                          before_png: bytes, after_png: bytes) -> dict:
    """Return {parameter:.., operation:.., functional:..} three-level instructions."""
    # TODO(M3): render-image pair + DSL pair → VLM → three-level instructions
    raise NotImplementedError
