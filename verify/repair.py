"""
Self-repair loop + human handoff.

If any of the four verification stages fails, the failure reason is
structured and fed back to the model, for up to N rounds
(config: verify.repair.max_self_repair); if it still fails, the case is
handed off to the human review queue. Approve/reject labels flow back in
as improvement data (proposal §10, "downstream application").

Extends CADCodeVerify's generate-verify loop for the editing task.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class RepairOutcome:
    resolved: bool
    rounds: int
    final_dsl: str
    escalated_to_human: bool = False
    failure_log: list[str] = field(default_factory=list)


def run(dsl_text: str, instruction: dict, model, cfg: dict) -> RepairOutcome:
    """Run the verify → repair → (human) loop."""
    # TODO(M6): chain kernel/rules/visual/type_check; on failure, structure feedback and regenerate
    raise NotImplementedError
