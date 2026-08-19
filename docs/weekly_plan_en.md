# Week-by-Week Execution Plan

> This document expands the 12-month milestones (M1–M12) in `README.md` into weekly granularity (W1–W4 per month), to track progress against concrete files and TODOs, without pinning to specific calendar dates.
>
> Four research questions: RQ1 `dsl/`,`data/` · RQ2 `editor/context/` · RQ3 `verify/` · RQ4 `data/real_parts/`,`deploy/`
>
> 中文版: [`docs/weekly_plan.md`](weekly_plan.md)

---

## M1 — DSL v1 Grammar Freeze

Corresponds to README "Where to Start" steps 1–2.

**W1**
- [ ] Kickoff
- [ ] Freeze design principles (`grammar.md` §1)
- [ ] Check base op set §4.1 against the conveyor-part vocabulary (shaft/roller/pulley/sprocket/bracket/frame)

Deliverable & Files: `dsl/grammar.md` §1, §4.1

**W2**
- [x] Design new ops replace/pattern/mirror/constraint (§4.2)
- [x] Resolve §8 open item: edit vs. replace boundary
- [x] Resolve §8 open item: minimal constraint set

Deliverable & Files: `dsl/grammar.md` §4.2, §8

**W3**
- [x] Implement `dsl/ast.py`: dedicated nodes & validation for replace/pattern/mirror/constraint (clears TODO(M1))
- [x] Finalize the derived-name ROLES enum in `dsl/registry.py`

Deliverable & Files: `dsl/ast.py`, `dsl/registry.py`

**W4**
- [x] Implement the `dsl/parser.py` recursive-descent parser
- [x] Unit-test against the §7 5-step example chain (see `tests/test_dsl_parser.py`)
- [x] Close out hand-written-vs-lark/antlr (last §8 item)

Deliverable & Files: `dsl/parser.py`

---

## M2 — Compiler + Eval Harness v1

**W1**
- [ ] Implement `dsl/compiler.py`: AST → FreeCAD Part/PartDesign calls
- [ ] Get the §3 example (sketch/extrude/pocket/fillet) running end to end

Deliverable & Files: `dsl/compiler.py`

**W2**
- [x] Flesh out `dsl/registry.py` `rebind()`: actually rewrite the dependency graph and downstream Refs (not just return conflicts)
- [x] Wire into the compiler

Deliverable & Files: `dsl/registry.py`

**W3**
- [x] Implement `eval/harness.py` `score_chain()` (TODO(M1))
- [x] Per-step parse_ok / refs_valid / prior_preserved scoring

Deliverable & Files: `eval/harness.py`

**W4**
- [x] Build `chains_3step/_5step/_10step` scenarios
- [x] Smoke-test the harness against hand-written DSL chains → **sequential-edit benchmark v1**
- [x] Append the frozen-spec addendum to `grammar.md`

Deliverable & Files: `eval/benchmarks/`, `dsl/grammar.md`

- [ ] **Milestone (end of M2)**: Extended DSL v1 spec + sequential-edit benchmark v1

---

## M3 — Compound-Edit Data Synthesis Kickoff

**W1**
- [ ] `data/synth/synthesize.py`: implement `synthesize_pairs()` for the cylinder→prism replace transform
- [ ] Kernel filtering stubbed until M6 lands

Deliverable & Files: `data/synth/synthesize.py`

**W2**
- [ ] Add the fillet↔chamfer transform
- [ ] Add the hole-pattern-change transform
- [ ] Target throughput for the 30k-instruction dataset v1

Deliverable & Files: `data/synth/synthesize.py`

**W3**
- [ ] `data/instruct/generate.py`: wire render-pair + DSL-pair into the VLM
- [ ] Produce parameter-level instructions first (easiest tier)

Deliverable & Files: `data/instruct/generate.py`

**W4**
- [ ] Extend to operation-level instructions
- [ ] Extend to functional-level instructions
- [ ] Add the compound-edit-specific types (replace / restructure / constraint-preserving)

Deliverable & Files: `data/instruct/generate.py`

---

## M4 — Scale Synthesis + Fine-Tune Infra

**W1**
- [ ] Scale up `synthesize_pairs()` runs toward the dataset v1 volume target
- [ ] Track the kernel-validity pass rate

Deliverable & Files: `data/synth/`

**W2**
- [ ] `editor/model.py`: implement `EditModel.__init__` (transformers load + peft LoRA attach)
- [ ] Stub the bitsandbytes quantized-load path for reuse in M10

Deliverable & Files: `editor/model.py`

**W3**
- [ ] `scripts/train.py`: implement the LoRA training loop
- [ ] Read from `data/synth` + `data/real_parts`

Deliverable & Files: `scripts/train.py`

**W4**
- [ ] Data QA: dedup
- [ ] Data QA: validity spot-check
- [ ] Freeze dataset v1

Deliverable & Files: `data/synth/`, `data/real_parts/`

---

## M5 — First Fine-Tune Round + G1 Mid-Term Check

**W1**
- [ ] Launch the first LoRA fine-tune run on dataset v1 (parameter + compound edits)

Deliverable & Files: `scripts/train.py`

**W2**
- [ ] `editor/model.py` `generate()`: implement the valid_refs constrained-decoding hook
- [ ] This is RQ2 groundwork, reused later by context strategies

Deliverable & Files: `editor/model.py`

**W3**
- [ ] `editor/infer.py` `_build_prompt()`: assemble the instruction/current-DSL/few-shot template
- [ ] Run `edit_once()` end-to-end via `scripts/run_edit.py`

Deliverable & Files: `editor/infer.py`, `scripts/run_edit.py`

**W4**
- [ ] G1 mid-term measurement: parameter-level edit IoU / parse rate on the held-out real-part set (target ≥0.93 / ≥96%)
- [ ] Write up the mid-term check

Deliverable & Files: `eval/metrics.py`

- [ ] **Milestone (end of M5)**: Dataset v1 (30k instructions) + G1 mid-term check

---

## M6 — Four-Stage Verification Loop

**W1**
- [ ] `verify/kernel.py` `check()`: re-run via `dsl/compiler.py`
- [ ] Validate B-rep (self-intersection, open shell)

Deliverable & Files: `verify/kernel.py`

**W2**
- [ ] `verify/rules.py` `check()`: measure min wall thickness via trimesh/shapely
- [ ] Measure hole-edge distance
- [ ] Measure instruction-vs-result dimension against `config/default.yaml` thresholds

Deliverable & Files: `verify/rules.py`

**W3**
- [ ] `verify/visual.py` `check()`: VLM scoring of before/after renders (1–5)
- [ ] Pass threshold ≥4 (per config)

Deliverable & Files: `verify/visual.py`

**W4**
- [ ] `verify/type_check.py` `check()`: reuse the prior-stage part classifier
- [ ] Confirm the type is preserved pre/post edit

Deliverable & Files: `verify/type_check.py`

---

## M7 — Self-Repair Loop + Mid-Term Demo

**W1**
- [ ] `verify/repair.py` `run()`: chain kernel→rules→visual→type_check
- [ ] Structure failures and feed back into `editor/infer.py` regeneration

Deliverable & Files: `verify/repair.py`

**W2**
- [ ] Enforce `verify.repair.max_self_repair` (3 rounds) → HITL handoff
- [ ] Wire into the pending-review queue (precursor to `deploy/ui`)

Deliverable & Files: `verify/repair.py`, `config/default.yaml`

**W3**
- [ ] Inject `defect_injection/` cases (boundary-crossing holes, pipe-joint gaps, over-editing)
- [ ] Run the first G4 test via `eval/metrics.py` `defect_recall()`

Deliverable & Files: `eval/benchmarks/defect_injection/`, `eval/metrics.py`

**W4**
- [ ] Mid-term demo prep: run the full `scripts/run_edit.py` pipeline (editor.infer → verify.repair → output) on real parts
- [ ] Freeze the demo script/slides

Deliverable & Files: `scripts/run_edit.py`

- [ ] **Milestone (end of M7)**: Mid-term demo (first G4 test)

---

## M8 — Sequential-Edit Context Experiments

**W1**
- [ ] `editor/context/strategies.py` `FullHistory.build()`: concatenate the full DSL history (baseline)

Deliverable & Files: `editor/context/strategies.py`

**W2**
- [ ] `SummarizedSubtree.build()`: feature-tree summary + relevant-subtree extraction

Deliverable & Files: `editor/context/strategies.py`

**W3**
- [ ] Run the FullHistory / CurrentOnly / SummarizedSubtree comparison across the 3/5/10-step benchmarks, measure the degradation curve
- [ ] `ref_break_rate` → G3 measurement (5-step target <5%)

Deliverable & Files: `eval/benchmarks/`, `eval/harness.py`

**W4**
- [ ] Collect a second round of real-part variant-design history
- [ ] Widen the round-2 fine-tune set (feeds into M9)

Deliverable & Files: `data/real_parts/`

---

## M9 — Second Fine-Tune Round

**W1**
- [ ] Rebuild the training set: v1 synthetic data
- [ ] Add round-2 real-part edits
- [ ] Add hard cases surfaced in M7–M8

Deliverable & Files: `data/synth/`, `data/real_parts/`

**W2**
- [ ] Launch the second LoRA fine-tune round
- [ ] Target compound-edit and long-chain weaknesses

Deliverable & Files: `scripts/train.py`

**W3**
- [ ] Re-measure G2 (compound IoU/parse, target ≥0.80/≥85%) on the new checkpoint
- [ ] Re-measure G3 (ref-break rate)

Deliverable & Files: `eval/metrics.py`, `eval/harness.py`

**W4**
- [ ] Regression-check that G1 hasn't regressed after round-2 training
- [ ] Write up the G2·G3 measurement

Deliverable & Files: `eval/`

- [ ] **Milestone (end of M9)**: G2 · G3 measured

---

## M10 — Real-Part Evaluation + On-Prem Optimization

**W1**
- [ ] `deploy/quantize.py` `quantize()`: bitsandbytes/GPTQ int4-quantize the round-2 checkpoint
- [ ] Target a single 24GB GPU

Deliverable & Files: `deploy/quantize.py`

**W2**
- [ ] Re-benchmark G1–G3 on the quantized model
- [ ] Check quality loss vs. full precision

Deliverable & Files: `eval/`

**W3**
- [ ] Measure G6 latency/edit (target ≤30s)
- [ ] Tune batch/KV-cache settings if over budget

Deliverable & Files: `deploy/quantize.py`

**W4**
- [ ] Full held-out evaluation pass for G1, G2, G4 on `data/real_parts`
- [ ] This is the only set that counts per README

Deliverable & Files: `data/real_parts/`, `eval/`

---

## M11 — HITL UI Pilot + Final Measurement

**W1**
- [ ] Build the `deploy/ui` approve/reject review UI (streamlit)
- [ ] NL input
- [ ] Before/after 3D diff
- [ ] Approve/reject buttons

Deliverable & Files: `deploy/ui/`

**W2**
- [ ] Wire review decisions back into training data (via `verify/repair.py`'s escalated_to_human / failure_log path)
- [ ] Pilot on a small batch of real edits

Deliverable & Files: `deploy/ui/`, `verify/repair.py`

**W3**
- [ ] Measure G5 auto-confirm rate (target ≥80%) from pilot queue statistics

Deliverable & Files: `deploy/ui/`

**W4**
- [ ] Final G1–G6 measurement pass on the full held-out real-part set
- [ ] Compile result tables

Deliverable & Files: `eval/`

- [ ] **Milestone (end of M11)**: G1–G6 final measurement

---

## M12 — Write-Up + System v1.0

**W1**
- [ ] Consolidate result tables/figures for the four RQs
- [ ] Draft the findings section per RQ

Deliverable & Files: —

**W2**
- [ ] Draft the final report/paper (method, DSL design, verification loop, real-part results)
- [ ] Address risk-register item R1 (re-binding conflict incidence) in the limitations/discussion section
- [ ] Address R2 (incremental-verification overhead)
- [ ] Address R4 (synthetic-vs-real gap)

Deliverable & Files: —

**W3**
- [ ] Tag system v1.0 (freeze `dsl/`, `editor/`, `verify/`, `deploy/` at reviewed state)
- [ ] Polish README/docs
- [ ] Internal review pass

Deliverable & Files: whole repo

**W4**
- [ ] Submit the final report
- [ ] Retrospective on items deferred to future work

Deliverable & Files: —

- [ ] **Milestone (end of M12)**: Final report + system v1.0

---

## Quantitative-Target Timeline

| Metric | First measured | Final measurement |
|---|---|---|
| G1 param IoU/parse | M5 W4 mid-term check | M11 W4 |
| G2 compound IoU/parse | M9 W3 | M11 W4 |
| G3 ref-break rate | M8 W3 | M9 W3 → M11 W4 |
| G4 defect recall/FP | M7 W3 first test | M10 W4 → M11 W4 |
| G5 auto-confirm rate | M11 W3 | M11 W4 |
| G6 latency/edit | M10 W3 | M10 W3 |

All targets are measured on the held-out real-part set; synthetic-data scores do not count as passing (see `README.md`).
