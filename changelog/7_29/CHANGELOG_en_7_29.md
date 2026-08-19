# M1 Progress Report — Project Kickoff & DSL v1 Grammar Freeze

**Project**: Reference-Stable DSL based LLM CAD Editing System
**Status**: built from scratch this week; M1 milestone complete
**中文版**: [`CHANGELOG.md`](CHANGELOG.md)

---

## 1. Milestone status

Per the project's 12-month plan (`README.md`), M1's deliverable is the **DSL v1 grammar** — the foundation the rest of the system builds on: what the LLM will be trained to generate, what the four-stage verification loop will check against, and what the real conveyor parts (RQ4) will eventually be formalized into.

**M1 is complete** — all 4 planned weeks, tracked in `docs/weekly_plan_en.md`, are checked off.

## Background — what is this DSL, and why build one?

An engineer's instruction is natural language ("extend the shaft to 250mm"), which is too ambiguous for software to execute or verify directly. Having the LLM generate raw CAD-kernel API calls (FreeCAD/OCCT Python) directly would be too complex and error-prone for it to produce reliably. So this project defines a small custom language — a **DSL (Domain-Specific Language)** — as the middle layer between the two:

```
natural-language instruction   →   [LLM]   →        DSL text            →   [dsl/compiler.py]   →   runs on the CAD kernel
"extend the shaft to 250mm"              edit(target=body, set=length, value=250);                FreeCAD actually lengthens the shaft
```

The LLM only has to learn to generate this small, fixed-format text (`sketch(...)`, `extrude(...)`, `replace(...)`, ...) instead of full CAD API calls. And because the DSL's grammar is fixed and simple, everything it generates can be automatically checked — parsed, re-run on the kernel, measured against dimension rules, etc. — before it is trusted. `dsl/grammar.md` is this DSL's specification: what operations exist (its "verbs"), how they combine into statements (its "sentence structure"), and — its most distinctive design choice — how one statement refers to a feature created by an earlier one.

**Why references matter — the Topological Naming Problem**: in most parametric CAD software, a face or edge you want to modify is addressed by its position (e.g. "the 3rd face") or by coordinates. If an earlier step in the model changes, those positions can silently shift, and a later edit ends up touching the wrong geometry — this is a well-known failure mode called the Topological Naming Problem. This project's DSL instead names geometry with permanent symbolic tags, e.g. `body.face_top`, that keep working even after `body` itself is heavily modified. Concretely, from `grammar.md` §6:

```dsl
# before
body = extrude(profile=circle_sk, length=200);
h    = pocket(on=body.face_top, ...);          # h refers to body's top face

# instruction: "swap the body from a cylinder to a hexagonal prism"
replace(target=body, with=extrude(profile=hex_sk, length=200));
# body.face_top is still valid → h automatically re-targets the new solid's top face
```

Even though `body` completely changed shape (cylinder → hexagonal prism), `h`'s reference to `body.face_top` is never invalidated — this is the concrete problem the reference-stability design solves.

This week's work, detailed below, delivered exactly this: the grammar frozen, and a real parser that reads this DSL text and turns it into a structured object a program can execute and check.

## 2. What was built

**a. Full project skeleton**, organized around the four research questions:

- `dsl/` — DSL definition & parser (RQ1)
- `editor/`, including `context/` — the editing engine and sequential-edit context management (RQ2)
- `verify/` — the four-stage verification loop (RQ3): kernel / rules / visual / type_check / repair
- `eval/` — the evaluation framework: harness / metrics / benchmarks
- `data/` — compound-edit synthesis, instruction generation, and real-part data (RQ4)
- `deploy/` — on-prem deployment (RQ4): quantization + review UI
- `scripts/`, `config/default.yaml` — training/inference entry points and global config

Aside from `dsl/ast.py` and `dsl/parser.py` (below), each module is scaffolded with a clear interface and milestone-tagged TODOs (M3/M6/M8/M10), to be filled in as the project reaches those milestones.

**b. A week-by-week execution plan** (`docs/weekly_plan.md` / `weekly_plan_en.md`) expanding the 12-month milestones into a checkable, per-week task list.

**c. The DSL v1 grammar is frozen** (`dsl/grammar.md`), specifying:

- **Reference-stability**: geometry is addressed by persistent symbolic names (e.g. `body.face_top`) rather than coordinates or positional indices — the core answer to the **Topological Naming Problem**, the classic failure mode in parametric CAD editors where a downstream reference silently breaks after an upstream edit.
- **The operation set**: base operations (`sketch`/`extrude`/`revolve`/`fillet`/`chamfer`/`pocket`/`groove`/`edit`) plus this project's core contribution — 4 new operations for compound editing: `replace` (feature-type swap with automatic downstream re-binding), `pattern`, `mirror`, `constraint`.
- **Reference grammar**: dotted references (`body.face_top`) and pattern-instance indices (`pat1[*]`, `pat1[2]`).
- **`replace`'s re-binding semantics** — a key difficulty for RQ2: how downstream references automatically follow when a feature is swapped.
- **Derived-name `role` enumeration**: 7 roles finalized (`face_top`, `face_bottom`, `axis`, `wall`, `floor`, `edge_top`, `edge_bottom`), with a table of which operation exposes which.

**d. A working parser** (`dsl/ast.py`, `dsl/parser.py`) — a hand-written recursive-descent parser that turns DSL text into an AST, supporting the full grammar: dotted/indexed references, numeric values with units, both bracket-list forms, and nested operation calls as argument values (e.g. `replace(target=body, with=extrude(...))`). It also validates the 4 new ops' required arguments at parse time.

**e. A test suite** (`tests/test_dsl_parser.py`, 13 tests) — covering every worked example in `grammar.md`, including the 5-step sequential-edit chain slated to become the RQ2 benchmark, plus the new-op validation error cases. All 13 pass.

## 3. Key design decisions

Five design questions central to the grammar were settled, each recorded with its rationale in `grammar.md` §8:

| Question | Decision |
|---|---|
| `edit` vs. `replace` boundary | Same operation type, only a scalar value changes → `edit` (cheap, no re-binding check). The operation type itself changes → `replace` (triggers the re-binding check). |
| Minimal `constraint` set | `dim`: equal / range / ratio; `geom`: concentric / coplanar / parallel — chosen to directly cover the thresholds already defined in `config/default.yaml`. |
| `pat1[*]` count semantics | Expands to `pat1[0]`..`pat1[count-1]`, with `count` read from the originating `pattern` statement. (The expansion logic itself is deferred to the verify layer, M6.) |
| Derived-name `role` enumeration | See item (c) above. |
| Parser implementation strategy | Hand-written recursive descent, no `lark`/`antlr` dependency — the grammar is small enough that a parser generator isn't worth the added dependency. |

## 4. Validation

- Every worked example in `grammar.md` (§3 basic example, §6 replace/re-binding example, §7 5-step chain) parses correctly end to end.
- Malformed new-op calls are correctly rejected (missing required args, an invalid `pattern` type, a `replace` whose `with=` isn't a nested operation call).
- All `.py` files pass `py_compile`; `config/default.yaml` parses as valid YAML.

## 5. Next (M2)

- Wire `dsl/compiler.py` to FreeCAD so DSL programs actually execute against the CAD kernel.
- Finish `dsl/registry.py`'s `rebind()` — it currently only detects re-binding conflicts; it needs to actually rewrite the dependency graph and downstream references.
- Build `eval/harness.py`'s chain-scoring logic to produce **sequential-edit benchmark v1**, the other M1–M2 deliverable per the project plan.

---

## Appendix: Deliverable Contents

### A. Project directory structure

```
LLM-CAD-Editor/
├── CHANGELOG.md
├── CHANGELOG_en.md
├── README.md
├── pytest.ini
├── requirements.txt
├── config/
│   └── default.yaml
├── data/
│   ├── instruct/generate.py
│   ├── real_parts/README.md
│   └── synth/synthesize.py
├── deploy/
│   ├── quantize.py
│   └── ui/README.md
├── docs/
│   ├── weekly_plan.md
│   └── weekly_plan_en.md
├── dsl/
│   ├── ast.py
│   ├── compiler.py
│   ├── grammar.md
│   ├── parser.py
│   └── registry.py
├── editor/
│   ├── context/
│   │   ├── __init__.py
│   │   └── strategies.py
│   ├── infer.py
│   └── model.py
├── eval/
│   ├── benchmarks/README.md
│   ├── harness.py
│   └── metrics.py
├── scripts/
│   ├── run_edit.py
│   └── train.py
├── tests/
│   └── test_dsl_parser.py
└── verify/
    ├── kernel.py
    ├── repair.py
    ├── rules.py
    ├── type_check.py
    └── visual.py
```

### B. Key excerpts from `dsl/grammar.md`

**Operation set (§4)**

| Op | Purpose | Key args |
|---|---|---|
| `sketch`  | 2D sketch | `plane`, `circle`/`rect`/`polygon` |
| `extrude` | extrude | `profile`, `length`, `dir` |
| `revolve` | revolve | `profile`, `axis`, `angle` |
| `fillet`  | fillet | `on` (edge ref), `radius` |
| `chamfer` | chamfer | `on` (edge ref), `dist` |
| `pocket`  | pocket | `on` (face ref), profile, `depth` |
| `groove`  | groove | `on`, `profile`, `axis` |
| `edit`    | single-value parameter edit (op type unchanged, no re-binding) | `target` (feature ref), `set` (field name), `value` |
| `replace` | feature replacement | `target` (feature ref), `with` (new operation) — **must trigger downstream re-binding** |
| `pattern` | patterned copy | `feature`, `type`(linear/circular), `count`, `spacing`/`angle` |
| `mirror`  | mirror | `feature`, `plane` |
| `constraint` | constraint declaration | `type`(dim/geom), `on`, `value` |

**Derived-name roles (§5)**: `face_top`, `face_bottom`, `axis`, `wall`, `floor`, `edge_top`, `edge_bottom`

**Full example (§7, the 5-step chain used for the RQ2 benchmark)**

```dsl
# initial
sk1  = sketch(plane=XY, circle=[center=origin, r=20]);
body = extrude(profile=sk1, length=200);

# step1: lengthen  →  body.length: 200 → 250
edit(target=body, set=length, value=250);

# step2: drill top hole
h1 = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);

# step3: pattern the hole
p1 = pattern(feature=h1, type=circular, count=4, angle=90);

# step4: cylinder → hex prism (triggers re-binding)
replace(target=body, with=extrude(profile=hex(r=20), length=250));

# step5: chamfer top edge
chamfer(on=body.edge_top, dist=1.5);
```

### C. How the parser is implemented

`dsl/parser.py` works in two stages — **tokenize first, then recursive-descent parse** — the classic recipe for hand-written parsers.

**Stage 1: tokenizing — cutting the raw text into "words"**

A human reads `body = extrude(profile=sk1, length=200);` and instantly knows which part is a name and which is punctuation. The program first has to cut that string into a sequence of smallest units (tokens): `body`, `=`, `extrude`, `(`, `profile`, `=`, `sk1`, `,`, `length`, `=`, `200`, `)`, `;`.

This is `_TOKEN_RE` (lines 19–37) — a regular expression with named groups, one recognition rule per kind of "word": anything number-shaped is a `NUMBER`, anything starting with a letter is an `IDENT` (identifier — a name or operation), `(`, `)`, `,`, etc. are each their own kind. `_tokenize()` (lines 51–64) scans the text line by line, recording one token per match along with which line it came from (`lineno`) — that line number is exactly where later error locations come from. Whitespace is skipped (`SKIP`); an unrecognized character raises an error immediately (`MISMATCH`).

**Stage 2: recursive-descent parsing — turning the token sequence back into meaningful structure**

"Recursive descent" means: every rule in the grammar (`program`, `statement`, `args`, `value` in grammar.md §3) gets its own function, and these functions call each other. Because the grammar itself nests (a `value` can be another operation call, which has its own `args`, whose values can themselves be further nested), these functions also call themselves — that's the "recursive" part.

The mapping:

| Grammar rule | Function | What it does |
|---|---|---|
| `program ::= statement*` | `parse_program()` (94–99) | Keeps reading statements until it hits the end (EOF) |
| `statement ::= feature_def \| edit_op` | `_parse_statement()` (101–121) | Checks whether the first token is followed by `=` to decide "named statement" vs. "bare operation" |
| `args ::= key=value, ...` | `_parse_args()` (123–136) | Loops reading `key = value`, continuing on a comma, stopping otherwise |
| `value ::= number \| reference \| ...` | `_parse_value()` (138–154) | Branches on whether the next token is a number/string/bracket/identifier |
| references / nested calls / indices after an identifier | `_parse_ident_value()` (156–188) | **Where the recursion happens** (see below) |

The key recursion is in `_parse_ident_value()`: after reading an identifier (e.g. `extrude`), it peeks one token ahead:

- Followed by `(` → this is a **nested operation call** (e.g. the `extrude(...)` inside `with=extrude(...)`), so it **calls `_parse_args()` again** to parse its arguments — and `_parse_args()` may in turn call `_parse_ident_value()` again while parsing one of those values, recursing another level deeper if there's yet another nested call (e.g. `hex(...)` inside `extrude(profile=hex(r=20), ...)`). This is exactly why `replace(target=body, with=extrude(profile=hex(r=20), length=250))` — "an operation nested inside an operation nested inside an operation" — parses correctly.
- Followed by `[` → a pattern-instance index (`pat1[*]`/`pat1[2]`)
- Neither → a plain reference (`body.face_top`)

Three small helpers are shared by every parsing function: `_peek()` (look at the next token without consuming it), `_advance()` (consume the current token and move forward), `_expect(kind)` (require the next token to be a specific kind, raising a line-numbered error if not). `_validate()` (87–92) calls `dsl/ast.py`'s `validate_new_op()` right after parsing each `replace`/`pattern`/`mirror`/`constraint` statement — validation is woven into parsing itself, not a separate pass afterward.

**Tracing one real statement through the pipeline**, using `body = extrude(profile=sk1, length=200);`:

```
_parse_statement()
  reads "body", peeks "=" next → this is a feature_def
  reads the operation name "extrude", reads "("
  → calls _parse_args("RPAREN")
       reads "profile" "=" → calls _parse_value() → reads identifier "sk1", not followed by "(" or "[" → returns Ref(["sk1"])
       reads ",", continues
       reads "length" "=" → calls _parse_value() → reads number "200" → returns Quantity(200.0)
       reads ")" → _parse_args returns {"profile": Ref(["sk1"]), "length": Quantity(200.0)}
  reads ")", reads ";"
  → returns Statement(name="body", op="extrude", args={...})
```

The top-level `parse()` function (line 210) chains tokenizing and this whole recursive parse together in one line: `_Parser(_tokenize(text)).parse_program()`.

### D. What the parser actually produces (results, not source)

**D1. Feeding the §7 5-step chain into the parser**

```
Statement(name='sk1', op='sketch', args={'plane': Ref(path=['XY']), 'circle': {'center': Ref(path=['origin']), 'r': Quantity(value=20.0)}})
Statement(name='body', op='extrude', args={'profile': Ref(path=['sk1']), 'length': Quantity(value=200.0)})
Statement(name=None, op='edit', args={'target': Ref(path=['body']), 'set': Ref(path=['length']), 'value': Quantity(value=250.0)})
Statement(name='h1', op='pocket', args={'on': Ref(path=['body', 'face_top']), 'circle': {'center': Ref(path=['body', 'axis']), 'r': Quantity(value=6.0)}, 'depth': Quantity(value=180.0)})
Statement(name='p1', op='pattern', args={'feature': Ref(path=['h1']), 'type': Ref(path=['circular']), 'count': Quantity(value=4.0), 'angle': Quantity(value=90.0)})
Statement(name=None, op='replace', args={'target': Ref(path=['body']), 'with': OpCall(op='extrude', args={'profile': OpCall(op='hex', args={'r': Quantity(value=20.0)}), 'length': Quantity(value=250.0)})})
Statement(name=None, op='chamfer', args={'on': Ref(path=['body', 'edge_top']), 'dist': Quantity(value=1.5)})
```

**What this shows**: the parser isn't just a grammar defined on paper — it genuinely digests the full 5-step chain. Statement 6 (`replace`) is the interesting one: its `with` argument is correctly broken out into a standalone `extrude` operation node, and that `extrude`'s `profile` nests a further `hex` operation node inside it. This "operation nested inside operation" form (§6's re-binding semantics) is exactly where a naive parser would be most likely to fail, and it doesn't here.

**Code location**: the pipeline is `dsl/parser.py`'s `parse()` (lines 210–220) → `_tokenize()` (51–64) → `_Parser.parse_program()` (94–99) → `_parse_statement()` (101–121) → `_parse_args()` (123–136) → `_parse_value()` (138–154); the nested-operation-call detection for `replace`'s `with=` lives in `_parse_ident_value()` (156–188, specifically 162–171). The AST node types (`Statement`/`Ref`/`Quantity`/`OpCall`) are defined in `dsl/ast.py` lines 12–53.

**D2. What the validation logic actually catches**

| Input | What rule it breaks | Actual error raised |
|---|---|---|
| `replace(target=body);` | `replace` is missing the required `with` | `replace(...) missing required arg(s): with` |
| `replace(target=body, with=hex_sk);` | `with` must be a nested op call, not a plain reference | ``replace(...): `with` must be a nested operation call`` |
| `pattern(feature=h1, type=triangular, count=4);` | `type` must be `linear` or `circular` | `pattern(...): type must be one of ['circular', 'linear'], got triangular` |
| `mirror(feature=h1);` | missing the required `plane` | `mirror(...) missing required arg(s): plane` |
| `constraint(type=dim, on=body.length);` | missing the required `value` | `constraint(...) missing required arg(s): value` |

**What this shows**: all 5 are syntactically well-formed but semantically invalid. The parser rejects each one immediately, before it can reach the compiler or verification stages — this is `dsl/ast.py`'s `validate_new_op()` doing its job.

**Code location**: the validation logic is `dsl/ast.py`'s `validate_new_op()` (lines 73–95); the required-args table is `NEW_OP_REQUIRED_ARGS` in the same file (59–64). It's called from `dsl/parser.py`'s `_Parser._validate()` (87–92) at three call sites: parsing `name = op(...)` (line 112), parsing a bare operation statement (line 120), and parsing a nested operation call (line 170).

**D3. Syntax errors point at an exact line**

Input (missing semicolon on the first statement):
```dsl
sk1 = sketch(plane=XY
body = extrude(profile=sk1, length=200);
```
Actual error:
```
ParseError: expected RPAREN, got IDENT 'body' (line 2)
```

**What this shows**: errors carry a precise line number, which matters both for a human debugging a DSL script and for the M6 self-repair loop, which needs a structured failure reason to feed back to the model.

**Code location**: line numbers come from `dsl/parser.py`'s `_tokenize()` (lines 51–64, tracking `lineno` while scanning line by line) and the `_Token` class (44–48); the error itself is raised in `_expect()` (81–85).

**D4. Units are optional, and parse to one consistent type**

Input: `edit(target=body, set=length, value=250 mm);`
Parsed `value` argument: `250.0mm` (i.e. `Quantity(value=250.0, unit='mm')`)

**What this shows**: units (mm/deg) are optional per grammar.md §2, and both the unit and no-unit forms (like `value=250` in the §7 example) parse to the same `Quantity` type — downstream code never needs two code paths depending on whether a unit was given.

**Code location**: `dsl/parser.py`'s `_parse_value()` lines 141–146 (after reading a number, checks whether the next token is `mm`/`deg`); the `_UNITS` set is defined at line 17; `Quantity` is defined in `dsl/ast.py` lines 24–31.

### E. Test results

The 13 tests in `tests/test_dsl_parser.py`, and what each one checks:

- `test_section3_basic_example` (`tests/test_dsl_parser.py:16-36`) — grammar.md §3's basic example (sketch/extrude/pocket/fillet) parses into the right statements and args
- `test_section6_replace_rebinding_example` (`tests/test_dsl_parser.py:39-54`) — §6's replace example: `with` correctly parses as a nested operation
- `test_section7_five_step_chain` (`tests/test_dsl_parser.py:57-102`) — §7's 5-step chain (the RQ2 benchmark chain): all 7 statements structurally correct
- `test_parse_ref` (`tests/test_dsl_parser.py:105-116`, 3 parametrized cases) — all three reference forms (`body.face_top`, `pat1[*]`, `pat1[2]`) parse correctly
- `test_new_op_validation_errors` (`tests/test_dsl_parser.py:119-131`, 5 parametrized cases) — the 5 invalid calls from D2 above are all correctly rejected
- `test_syntax_error_reports_line_number` (`tests/test_dsl_parser.py:134-137`) — a syntax error reports the correct line number
- `test_quantity_unit_parsing` (`tests/test_dsl_parser.py:140-142`) — a value with a unit parses correctly

Actual run:

```
$ python -m pytest -v
collected 13 items

tests/test_dsl_parser.py::test_section3_basic_example PASSED
tests/test_dsl_parser.py::test_section6_replace_rebinding_example PASSED
tests/test_dsl_parser.py::test_section7_five_step_chain PASSED
tests/test_dsl_parser.py::test_parse_ref[body.face_top-expected_path0-None] PASSED
tests/test_dsl_parser.py::test_parse_ref[pat1[*]-expected_path1-*] PASSED
tests/test_dsl_parser.py::test_parse_ref[pat1[2]-expected_path2-2] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[replace(target=body);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[replace(target=body, with=hex_sk);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[pattern(feature=h1, type=triangular, count=4);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[mirror(feature=h1);] PASSED
tests/test_dsl_parser.py::test_new_op_validation_errors[constraint(type=dim, on=body.length);] PASSED
tests/test_dsl_parser.py::test_syntax_error_reports_line_number PASSED
tests/test_dsl_parser.py::test_quantity_unit_parsing PASSED

============================= 13 passed in 0.08s ==============================
```
