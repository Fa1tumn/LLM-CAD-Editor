# Design Review — Physics-Verified CAD DSL Spec

Review of [`physics-cad-dsl-design-spec.md`](physics-cad-dsl-design-spec.md) against the current
project (`dsl/grammar.md` v1, `dsl/compiler.py`, `verify/`, `README.md`).

**Verdict: adopt as an extension, not as a replacement.** Three of the spec's ideas belong in this
project now. One — Lean 4 as host language — should be declined for this project's timeframe, and the
reasoning matters more than the conclusion.

---

## 1. The two documents attack the same problem, and both call it priority #1

`dsl/grammar.md` §1.1:

> **Reference-stability first**: geometry is named by stable symbolic references (`hole_1.axis`),
> never absolute coordinates. This is the core of side-stepping the Topological Naming Problem.

Spec §3.3:

> **언어 정체성을 결정하는 최우선 설계 항목.** … 인덱스 참조 방식은 경계 조건을 파괴함

Same problem (OCCT does not preserve topological IDs across regeneration), same ranking. This is the
strongest argument that the spec is a continuation of this project rather than a different one.

But the two solve it **differently**, and the difference is not cosmetic:

| | Current DSL | Spec §3.3 |
|---|---|---|
| Mechanism | Symbolic naming registry — features are named at authoring time (`hole1 = pocket(...)`), roles derived (`body.face_top`) | Geometric selectors — `faces(">Z")` resolved from geometry at evaluation time |
| Stable under **parameter** change | Yes — the name is unaffected | Yes — but the match may move to a different face |
| Stable under **structural** change | **No** — `replace` can delete the feature a downstream reference names; `registry.replace_feature` returns conflicts precisely because of this | Yes — the query re-evaluates |
| Ambiguity | None — a name binds to exactly one feature | **Yes** — `faces(">Z")` may match 0 or N faces |

These are complementary. The registry is precise but brittle under restructuring; selectors are robust
under restructuring but imprecise. RQ1 is explicitly about *restructuring* edits, which is exactly
where the registry is weakest — so selectors address a real gap in the current design, not a
hypothetical one.

**Recommendation.** Add selectors as an additional `reference` production that resolves into the same
reference space the registry already manages — not as a replacement for names. Per `CLAUDE.md`,
`grammar.md` is frozen and its worked examples are load-bearing in `tests/test_dsl_parser.py`, so this
must land as a **§9 addendum** — that section already exists and was used for the M2 additions — never
as an edit to existing sections. `registry.py`'s
`validate_refs` becomes the natural place to resolve a selector to a concrete role, and `LITERAL_ROOTS`
must gain the selector keywords or they will read as dangling references.

---

## 2. Dependent types collide with the LLM premise — and the spec does not account for it

`grammar.md` §1.4 lists **LLM-friendly** as a founding design principle: "few keywords, regular
structure … lowers the model's syntax error rate". The quantitative targets assume a 7–14B model
hitting ≥96% parse rate on single edits and ≥85% on compound edits.

Spec §3.2 asks the author to write proof terms:

```
shape Bracket (thickness : Real) (h_proof : thickness >= 5.0) { ... }
```

Explicit proof obligations are close to the hardest thing to get a small quantized model to emit
correctly. Adopting §3.2 as written would push against the metric the whole project is graded on.

**This is resolvable, and the spec itself points the way.** §3.6's tactic layering
(`by solve_analytical` / `by solve_fea_bounds` / `by trust_oracle`) means proofs are *discharged*, not
*authored*. The model should emit geometry and constraints — which is close to what it already emits —
and the constraint layer should discharge obligations automatically. The model never writes `h_proof`.

Concretely: keep `constraint` in its current `grammar.md` §4.2 form, and make it *checked* rather than
*advisory* — §8 records that its minimal set was chosen specifically to cover the `config/default.yaml`
thresholds, so the mapping already exists on paper. That buys most of §3.2's value at nearly zero cost to the generation surface.

---

## 3. The verification tiers are orthogonal to the four-stage loop, not competing with it

Easy to misread these as rival designs. They answer different questions:

| `verify/` (RQ3) | Question |
|---|---|
| `kernel.py` | Is the B-rep valid? |
| `rules.py` | Are dimensional rules satisfied? |
| `visual.py` | Does it look like what was asked? |
| `type_check.py` | Is it still the same kind of part? |

**"Did the edit do what was asked, and is the model still coherent?"**

| Spec §3.6 | Question |
|---|---|
| Tier 1 analytical | Closed-form stress/beam check |
| Tier 2 interval bounds | Conservative safety bound |
| Tier 3 oracle | External FEA verdict |

**"Is the resulting part physically safe?"**

Nothing in the current loop asks the second question. The spec's tiers therefore slot in as a **fifth
stage**, or more naturally as a deepening of `rules.py` from dimensional rules to physical rules.

Worth noting: `config/default.yaml` already carries `min_wall_thickness_mm: 1.0` and
`min_hole_edge_dist_mm: 2.0`. Those are exactly the Total CSG preconditions of spec §3.4 — the current
rules layer is already a degenerate tier-1. This is an extension of existing code, not a new subsystem.

---

## 4. Decline Lean 4 as host language for this project

The spec nominates Lean 4 as "가장 유력한 호스트 언어" (§4.1). Three reasons not to, in this project:

1. **Air-gapped deployment.** `README.md`: "Everything runs offline on an air-gapped intranet",
   single 24GB GPU, int4. Lean 4 plus Gmsh plus CalculiX plus their toolchains is a substantial
   offline packaging burden on top of an already constrained target (RQ4, M10–M11).
2. **Stack fit.** Everything here is Python — parser, compiler, FreeCAD binding, and the entire LLM
   training and inference path (torch/transformers/peft). A Lean front-end puts a language boundary
   between the model's output and the kernel, in the exact place RQ2 measures reference consistency.
3. **The spec's own pipeline already concedes it.** §6 routes B-rep work through
   "Python + CadQuery/OCP". This project has that layer already, built on FreeCAD/OCCT.

**Recommendation.** Take the *semantics* — dimensional types, refinement constraints, tactic tiers —
and implement them as a checked constraint layer in the existing Python DSL. Revisit a proof assistant
only if tier 2 (verified numerics / interval arithmetic) turns out to need real proof infrastructure,
which is an M8+ question and can be answered with evidence by then rather than assumed now.

What *should* be adopted from §4.1 immediately is much cheaper: an SMT backend (Z3) for discharging
the geometric constraints in §3.4. That is a pip install, not a language migration.

---

## 5. Blocking prerequisite: the compiler does not build the geometry the DSL describes

The kernel regression tests added in #1 exposed defects that make any physics layer premature. Most
serious:

- **`sketch(plane=...)` and `extrude(dir=...)` are parsed, stored, then discarded.** Every solid is
  built on XY and extruded along +Z regardless of what the program says.
- **`circle center=` is discarded**, so a profile the DSL anchors on another feature's axis is built
  at the global origin instead.
- **`finish()` returns one arbitrary body** — `solids[-1]`, by name-binding order — with no fusion.

A stress computed on that geometry would be a stress for a different part. Spec §3.5's boundary
conditions (`fix : faces("<X")`) are meaningless while orientation is discarded — and note that this
also blocks §3.3, since a selector like `faces(">Z")` cannot mean anything stable if every body is
silently rebuilt on XY.

These are filed as separate issues. **They gate the whole physics track.**

---

## 6. Recommended sequencing

| Stage | Work | Rationale |
|---|---|---|
| 0 | Fix geometry fidelity (plane, dir, center, fusion) | Gates everything below |
| 1 | Dimensional units in the type system (spec §3.1) | Cheapest win; `grammar.md` §2 already has a `unit` production and `ast.py:25` already has `Quantity` |
| 2 | Selectors as a §9 grammar addendum (spec §3.3) | Directly serves RQ1 restructuring edits and RQ2 reference stability |
| 3 | `constraint` becomes checked, discharged by Z3 (spec §3.2/§3.4) | Turns an advisory clause into a real guarantee without changing what the LLM emits |
| 4 | `rules.py` extended to closed-form physical checks (spec §3.6 tier 1) | Extends an existing stage; no new dependency |
| 5 | Gmsh + CalculiX oracle (spec §3.6 tier 3) | Highest cost, highest packaging risk — defer past the mid-term G4 check |

Tier 2 (interval arithmetic / verified numerics) is deliberately absent: it is the least proven part
of the spec and should only be scheduled once tier 1 and tier 3 are both working and their gap is
measured.

---

## 7. Open questions for the author

1. Do the spec's physical-safety targets need to appear in the README's quantitative-targets table? All
   current targets are edit-accuracy metrics; there is no physical-correctness metric to grade against.
2. Does the real conveyor-part domain (RQ4) actually carry load cases? If the parts are not
   structurally loaded, tier 1 is the whole physics story and tiers 2–3 have no customer.
3. Is the spec intended to change the deliverable of the 12-month plan, or to be a follow-on project
   scoped after M12? The milestone table currently has no room for stages 3–5 above.
