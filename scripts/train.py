"""
Training entry — LoRA fine-tune the 7~14B model.

Data comes from data/synth (synthetic compound edits) + data/real_parts
(real parts). Corresponds to milestone M3–M5 (first fine-tune round) and
M8–M9 (second round).
"""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(description="LoRA fine-tune")
    ap.add_argument("--config", default="config/default.yaml")
    ap.add_argument("--data", required=True, help="training data dir")
    args = ap.parse_args()
    # TODO(M3): transformers + peft training loop
    raise SystemExit("training loop not implemented yet")


if __name__ == "__main__":
    main()
