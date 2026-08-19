"""
End-to-end single edit — entry point for manually running the pipeline.

Flow: read current DSL → model generates draft → four-stage verification
→ self-repair/HITL → output.
"""
from __future__ import annotations
import argparse


def main() -> None:
    ap = argparse.ArgumentParser(description="run one CAD edit")
    ap.add_argument("--dsl", required=True, help="current part DSL file")
    ap.add_argument("--instruction", required=True, help="NL instruction")
    ap.add_argument("--config", default="config/default.yaml")
    args = ap.parse_args()
    # TODO: chain editor.infer → verify.repair → output
    raise SystemExit("pipeline not wired yet — see per-module TODOs")


if __name__ == "__main__":
    main()
