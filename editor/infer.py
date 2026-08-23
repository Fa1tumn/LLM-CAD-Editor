"""
Single-edit inference.

Input: an NL instruction + the current part's DSL + (optionally)
retrieved similar edit examples.
Output: an edited DSL draft (not yet verified).

Corresponds to the "LLM generates edit draft" step in Figure 6, stage 3
of the prior work's roadmap.
"""

from __future__ import annotations

from .model import EditModel


def edit_once(
    instruction: str,
    current_dsl: str,
    model: EditModel,
    retrieved_examples: list[str] | None = None,
    valid_refs: list[str] | None = None,
) -> str:
    """Produce an edit draft (pre-verification)."""
    prompt = _build_prompt(instruction, current_dsl, retrieved_examples)
    return model.generate(prompt, valid_refs=valid_refs)


def _build_prompt(instruction, current_dsl, examples) -> str:
    # TODO(M3): assemble the prompt template (instruction / current DSL / few-shot similar examples)
    raise NotImplementedError
