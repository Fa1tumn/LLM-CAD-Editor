# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A 12-month research project (2026.09–2027.08). Natural-language CAD edits → a custom DSL → the
FreeCAD/OCCT kernel → a four-stage verification loop that auto-repairs failures. Everything must
run **offline on an air-gapped intranet**; do not introduce network calls, telemetry, or hosted APIs.

The authoritative spec is `연구계획서_LLM_CAD편집_v2.docx` (Korean) plus `README.md`. Module docstrings
cite the section they implement (`grammar.md §6`, `proposal §4.2`, `RQ2 / G3`) — keep those citations
accurate when editing.

## Environment (required)

The project venv is built **from FreeCAD's bundled Python**, not from system Python, so that
`import FreeCAD` / `import Part` work:

```sh
FC=/Applications/FreeCAD.app/Contents/Resources
"$FC/bin/python" -m venv .venv
echo "$FC/lib" > .venv/lib/python3.11/site-packages/freecad.pth   # makes FreeCAD importable
.venv/bin/pip install -r requirements.txt
```

FreeCAD 1.1.1 is installed at `/Applications/FreeCAD.app`. Verify with:
`.venv/bin/python -c "from dsl.compiler import FreeCADBackend; FreeCADBackend()"`

FreeCAD is a **required** dev dependency — it is deliberately absent from `requirements.txt` because
it is not pip-installable. `SymbolicBackend` is a fallback for machines without the kernel, not the
target backend; do not write code that assumes the kernel is missing.

Heavy ML deps (torch, transformers, peft, bitsandbytes) target the 24GB-GPU training host, not this
Mac. Installing them locally is optional and unnecessary for DSL/verification work.

## Commands

```sh
.venv/bin/python -m pytest          # 20 tests, ~0.05s (pytest.ini sets pythonpath = .)
.venv/bin/python -m pytest -k name  # single test
.venv/bin/ruff check . --fix        # lint
.venv/bin/ruff format .             # format
```

`pytest.ini`'s `pythonpath = .` is what makes `from dsl.parser import parse` work without installing
the package. Do not "fix" this by moving to a src layout. There is no Makefile and no CI.

`scripts/run_edit.py` and `scripts/train.py` are argparse-only stubs that `raise SystemExit` — they
are not runnable entry points yet.

## Invariants that break silently

- **`import FreeCAD` must come before `import Part`.** `Part.so` links against the App layer
  FreeCAD sets up; importing `Part` first **segfaults** instead of raising, so pytest dies during
  collection with no summary and unrelated tests in the run never execute. The root `conftest.py`
  initialises FreeCAD so test modules can write the natural `import Part`;
  `tests/test_import_order.py` guards every other entry point.
- **`dsl/grammar.md` is frozen spec.** `tests/test_dsl_parser.py` is written directly against its
  worked examples (§3, §6, §7). Grammar changes need a §9-style addendum, never a silent edit.
- **`dsl/registry.py` closed sets must stay in sync with `grammar.md` §5**: `ROLES` (7 derived roles),
  `OP_ROLES` (which op exposes which role), and `LITERAL_ROOTS`. Adding a DSL keyword without adding
  it to `LITERAL_ROOTS` makes it look like a dangling reference.
- **`score_chain` is transactional** (`eval/harness.py`): a step failing parse or reference validation
  must not mutate the registry later steps see. Breaking this corrupts every downstream metric.
- **Exception class names are load-bearing.** `ParseError`, `ASTValidationError`, `ReferenceError`,
  `CompileError` are counted per-layer by the metrics (e.g. `ParseError` counts against parse-rate).
  Do not collapse or rename them.
- **Benchmark JSON contract**: `steps` is a non-empty string array and `expected.step_count` must
  equal `len(steps)`, or `load_chain()` raises.
- Verification thresholds live in `config/default.yaml` (wall thickness, hole-edge distance, dim
  tolerance, VLM pass score, `max_self_repair`, auto-confirm target). The grammar's `constraint` set
  was chosen to cover exactly these — read the config before changing either.
- Synthetic data does **not** count toward any target metric; all targets are measured on a held-out
  real-part set. Real conveyor-part drawings are confidential and stay on the intranet.

## Code style

`ruff.toml` enforces most of it (line-length 110, double quotes, import sorting). Beyond ruff:

- Every module opens with `from __future__ import annotations` and a docstring citing its spec section.
- Unimplemented work is `TODO(M3)` / `TODO(M6)` etc. with the **milestone number**, and the function
  `raise NotImplementedError`. These stubs are intentional — do not implement them opportunistically
  while doing unrelated work, and do not delete them to make linters happy.
- `@dataclass` for all result/AST types; `typing.Protocol` for the compiler backend interface.
- Private module helpers are `_`-prefixed (`_tokenize`, `_Parser`, `_Token`).

## Language convention

Code, comments, and docstrings in **English**. Changelogs in Chinese + English; presentation material
in Chinese + English + Korean.

## Per-session ritual (required)

At the end of every working session:

1. Create `changelog/<M_D>/` (month_day, no year, no zero-padding — e.g. `8_19`) with five files:
   `CHANGELOG_<M_D>.md` (zh), `CHANGELOG_en_<M_D>.md`, and presentation material in zh, en, ko.
   Changelogs include mermaid diagrams.
2. Tick the milestone checkboxes in **both** `docs/weekly_plan.md` (zh) and `docs/weekly_plan_en.md` —
   they must stay in sync.

The `/session-changelog` skill does both. Note `README.md` still describes `CHANGELOG.md` at the repo
root; the dated folders under `changelog/` are the real location.

## Current state

M1 done. M2 partially done — the next explicit task is M2 W1: the full FreeCAD Part/PartDesign op set
(`pocket`, `fillet`, `chamfer`, `pattern`, `mirror`, history rebuild). `editor/`, `verify/`, `deploy/`,
and `data/` are stubs with no test coverage.
