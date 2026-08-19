# M1 Group-Meeting Notes

> Details on file: `CHANGELOG_en_7_29.md`

Here's what got done this week, in a few pieces.

## 1. Project skeleton

Built out the whole project's module structure around the four research questions: `dsl/` handles the DSL definition and parser, `editor/` is the editing engine, `verify/` will be the four-stage verification loop, `eval/` is the evaluation framework, `data/` handles data synthesis and real parts, `deploy/` is on-prem deployment. Aside from the two files implemented this week, everything else is currently a clear interface plus TODOs tagged to a specific milestone, to be filled in as the project gets there.

Also expanded the 12-month milestones into a week-by-week execution plan, each week's tasks written as a checklist, one copy in Chinese and one in English, so progress can be tracked week to week.

## 2. DSL v1 grammar frozen

This is the main thing this week. `dsl/grammar.md` now specifies the whole language:

**Operation set**: the base operations carry over from prior work — `sketch`/`extrude`/`revolve`/`fillet`/`chamfer`/`pocket`/`groove` — plus `edit`, which had been used all along but never formally defined until now (a single-value parameter tweak). The core new additions are 4 compound-editing operations: `replace` (swap a feature, triggers downstream re-binding), `pattern` (patterned copy), `mirror`, and `constraint` (constraint declaration).

**Reference grammar**: dotted references (`body.face_top`) and pattern-instance indices (`pat1[*]`, `pat1[2]`).

**Derived-name roles**: settled on 7 — `face_top`, `face_bottom`, `axis`, `wall`, `floor`, `edge_top`, `edge_bottom` — with a table of which operation produces which.

Also closed out 5 design questions that had been left open:

- The boundary between `edit` and `replace` — same operation type, only a value changes, use `edit`; the operation type itself changes (even if the shape looks similar), use `replace`, which triggers the re-binding check.
- The minimum set for `constraint` — dimension-type: equal/range/ratio; geometry-type: concentric/coplanar/parallel, chosen to line up with the thresholds already defined in `config/default.yaml`.
- How `pat1[*]`-style pattern references expand at the verification layer — expands to `pat1[0]` through `pat1[count-1]`, with count read off the originating `pattern` statement; the actual expansion logic is deferred to the verify layer at M6.
- The full enumeration of derived-name roles — the 7 listed above.
- Whether the parser should use a generator like lark/antlr — no, hand-written recursive descent is enough; the grammar isn't big enough to justify pulling in another dependency.

## 3. Parser implementation + tests

Not just written down as rules — I actually implemented it.

`dsl/ast.py` defines the AST node types — statements, references, numbers with units, nested operation calls — plus a validation function that checks whether the 4 new operations (`replace`/`pattern`/`mirror`/`constraint`) have all their required arguments.

`dsl/parser.py` is the actual parser, done in two steps: first tokenize, cutting the DSL text into individual words; then recursive descent, reassembling those words into structured statements. Recursive descent means each grammar rule gets its own function, and those functions call each other; wherever the grammar itself nests — like an operation call containing another operation call — the corresponding function calls itself too. That's exactly why something like `replace(target=body, with=extrude(profile=hex(r=20), length=250))`, an "operation inside an operation inside an operation," parses correctly — that nesting is handled by this recursion.

Wrote 13 pytest tests, covering every example in the grammar spec (including the 5-step sequential-edit chain for RQ2), all three reference forms, whether 5 kinds of invalid calls get correctly rejected, whether syntax errors report the right line number, and whether values with units parse correctly. All 13 pass.

## 4. What it actually does

A few results worth calling out:

Feeding the trickiest line, `replace(target=body, with=extrude(profile=hex(r=20), length=250))`, into the parser — the `with` argument gets correctly broken into a standalone `extrude` operation node, and that `extrude`'s `profile` nests a further `hex` node inside it. All three levels come out right.

Deliberately feeding it broken input — like `replace` missing its required `with`, or `pattern`'s `type` set to something that isn't valid — and in every case, it gets caught and rejected right at parse time, so a malformed edit never makes it into the modeling pipeline downstream.

Syntax errors also report the exact line — a missing semicolon produces something like "expected RPAREN, got IDENT 'body' (line 2)" — which will matter later for the self-repair loop, which needs a structured error to feed back to the model.

Values with or without a unit (`250` vs. `250 mm`) both parse into the same type, so downstream code never needs two separate code paths.

## Next

M1 is done. Next, M2: wire this language to the actual FreeCAD modeling kernel so it produces a real 3D model, and build out the sequential-edit scoring framework to produce sequential-edit benchmark v1.
