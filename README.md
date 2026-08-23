# Reference-Stable DSL based LLM CAD Editing System

> Integrating Compound Editing, Sequential Editing & Geometric Verification Loops, Applied to Real Part Domains

Duration: 2026.09 ~ 2027.08 (12 months)

---

## In One Sentence

An engineer states an edit in plain language ("extend the shaft to 250, move the hole 10mm right"); the system rewrites the CAD model automatically, a four-stage loop verifies it for errors, and only the uncertain ~20% is escalated to a human. Everything runs offline on an air-gapped intranet.

---

## Four Research Questions

| Subtask | Research Question | Module |
|---|---|---|
| RQ1 | Can compound edits (replace / restructure / constraint-preserving) be expressed, learned and evaluated at the DSL level? | `dsl/`, `data/` |
| RQ2 | Does reference consistency hold across multi-step edit chains, and which context strategy works? | `editor/context/` |
| RQ3 | How much failure can the kernel / dimension / visual / type four-stage loop detect and auto-repair? | `verify/` |
| RQ4 | Do results reproduce on real conveyor parts, and can a small model deploy on-prem? | `data/real_parts/`, `deploy/` |

---

## Directory Layout

```
LLM-CAD-Editor/
├── README.md              # this file
├── CLAUDE.md              # working notes for Claude Code (env, invariants, style)
├── changelog/             # one folder per session, named <month>_<day> (e.g. 8_19)
│   └── 8_19/              #   CHANGELOG_8_19.md (zh) + _en, presentation_*.md (zh/en/ko)
├── requirements.txt       # Python dependencies (FreeCAD is NOT pip-installable — see below)
├── pytest.ini             # test config (adds repo root to pythonpath)
├── tests/                 # unit tests (pytest)
├── docs/
│   ├── weekly_plan.md     # week-by-week execution plan, Chinese (expands the milestones below)
│   └── weekly_plan_en.md  # same plan, English
├── config/
│   └── default.yaml       # config: model, paths, verification thresholds
├── dsl/                   # [RQ1] DSL definition & parser
│   ├── grammar.md         #   DSL v1 spec (read first)
│   ├── ast.py             #   AST nodes
│   ├── parser.py          #   DSL text → AST
│   ├── compiler.py        #   AST → FreeCAD/OCCT execution
│   └── registry.py        #   reference registry: symbolic names + dependency graph
├── data/
│   ├── synth/             #   compound edit-pair synthesis
│   ├── instruct/          #   3-level instruction generation (VLM)
│   └── real_parts/        #   [RQ4] real conveyor parts DSL
├── editor/                # editing engine
│   ├── model.py           #   7~14B LoRA model wrapper
│   ├── infer.py           #   single-edit inference
│   └── context/           #   [RQ2] sequential context management
├── verify/                # [RQ3] four-stage verification loop
│   ├── kernel.py          #   1. kernel re-run (B-rep validity)
│   ├── rules.py           #   2. dimension rules
│   ├── visual.py          #   3. VLM visual review
│   ├── type_check.py      #   4. type preservation (reuse stage-1 classifier)
│   └── repair.py          #   self-repair + HITL handoff
├── eval/                  # evaluation
│   ├── harness.py         #   sequential-edit scoring
│   ├── metrics.py         #   IoU / parse rate / break rate / recall
│   └── benchmarks/        #   3/5/10-step chains
├── deploy/                # [RQ4] on-prem offline deployment
│   ├── quantize.py        #   quantization (single 24GB GPU)
│   └── ui/                #   approve-reject review UI
└── scripts/
    ├── train.py           #   training entry
    └── run_edit.py        #   end-to-end single edit
```

---

## 12-Month Milestones (Proposal §8)

See `docs/weekly_plan.md` for the week-by-week breakdown of each milestone below.

| Period | Work | Milestone |
|---|---|---|
| **M1–M2** | DSL extension + eval harness | Extended DSL v1 spec + sequential-edit benchmark v1 ← **current** |
| **M3–M5** | Compound-edit data synthesis + first fine-tune | Dataset v1 (30k instructions), G1 mid-term check |
| **M6–M7** | Four-stage verification loop + self-repair | Mid-term demo (first G4 test) |
| **M8–M9** | Sequential-edit experiments + second fine-tune round | G2 · G3 measurement |
| **M10–M11** | Real-part comprehensive evaluation + on-prem inference optimization + UI pilot | G1~G6 final measurement |
| **M12** | Results write-up / paper & docs | Final report + system v1.0 |

---

## Quantitative Targets

| Metric | Target |
|---|---|
| param-level edit IoU / parse | ≥ 0.93 / ≥ 96% |
| compound edit IoU / parse | ≥ 0.80 / ≥ 85% |
| 5-step ref-break rate | < 5% |
| defect recall / false-positive | ≥ 95% / ≤ 10% |
| auto-confirm rate (human ≤20%) | ≥ 80% |
| latency / edit (single 24GB GPU) | ≤ 30s |

> All targets are measured on a held-out real-part set; synthetic-data scores do not count as passing.

---

## Where to Start

1. Read `dsl/grammar.md` — pin down the DSL v1 grammar (first M1 deliverable).
2. Fill in the AST and parser: `dsl/ast.py` and `dsl/parser.py`.
3. Get DSL → FreeCAD running end-to-end with `dsl/compiler.py`.
4. Then synthesize the first edit pairs in `data/synth/`.

---

## Setup

FreeCAD is a required dependency and is **not** pip-installable, so the venv must be created from
FreeCAD's own bundled Python — a venv built from system Python cannot import `FreeCAD` / `Part`.

```bash
# macOS (brew install --cask freecad); on Linux use the prefix containing FreeCAD.so
FC=/Applications/FreeCAD.app/Contents/Resources

"$FC/bin/python" -m venv .venv                      # FreeCAD ships conda-forge Python 3.11
echo "$FC/lib" > .venv/lib/python3.11/site-packages/freecad.pth
.venv/bin/pip install -r requirements.txt
```

Verify all three before starting work:

```bash
.venv/bin/python -c "import FreeCAD, Part; print(Part.makeBox(10,20,30).Volume)"   # 6000.0
.venv/bin/python -c "from dsl.compiler import FreeCADBackend; FreeCADBackend()"    # no error
.venv/bin/python -m pytest -q
```

`SymbolicBackend` is a fallback for machines without the kernel, not the target backend. The heavy ML
stack (torch, transformers, peft, bitsandbytes) targets the 24GB-GPU training host and is not needed
for DSL or verification work.

The `/setup-env` skill runs and checks all of the above.
