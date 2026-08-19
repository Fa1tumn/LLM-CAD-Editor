# DSL v1 Grammar Specification

> First M1 deliverable. This is the foundation of the whole project — what the LLM learns, what the verification loop checks, and what real parts are formalized into.

---

## 1. Design Principles

1. **Reference-stability first**: geometry is named by stable symbolic references (`hole_1.axis`), never absolute coordinates. This is the core of side-stepping the Topological Naming Problem.
2. **Composable**: every feature a statement produces can be referenced by name later; `replace` must re-bind all downstream references of the replaced feature.
3. **Verifiable**: every statement is executable by the kernel and checkable by dimension rules; no un-verifiable free text at the grammar level.
4. **LLM-friendly**: few keywords, regular structure, whitespace-insensitive — lowers the model's syntax error rate.

---

## 2. Lexical Elements

```
identifier   ::= [a-zA-Z_][a-zA-Z0-9_]*
number       ::= -?[0-9]+(\.[0-9]+)?
unit         ::= "mm" | "deg"         # default, omittable
reference    ::= identifier ("." identifier)* ("[" (number | "*") "]")?
                                               # e.g. hole_1.axis, face_top, pat1[*], pat1[2] (§5)
comment      ::= "#" .* to end of line
```

---

## 3. Program Structure

A CAD model = an **ordered** list of statements. Each creates or modifies a named feature.

```
program   ::= statement*
statement ::= feature_def | edit_op
feature_def ::= identifier "=" operation "(" args ")" ";"
edit_op     ::= operation "(" args ")" ";"
args        ::= (key "=" value ("," key "=" value)*)?
value       ::= number unit? | reference | string
              | "[" value* "]"              # bare list, e.g. spacing=[10, 20, 30]
              | "[" args "]"                # key=value list, e.g. circle=[center=origin, r=20]
              | operation "(" args ")"      # nested op call, e.g. with=extrude(...) (§6)
```

Example:

```dsl
# a shaft with an axial hole
sk1   = sketch(plane=XY, circle=[center=origin, r=20]);
body  = extrude(profile=sk1, length=200);
hole1 = pocket(on=body.face_top, circle=[center=body.axis, r=6], depth=180);
edge1 = fillet(on=body.edge_top, radius=2);
```

---

## 4. Operation Set

### 4.1 Base Operations (inherited from prior work)

| Op | Purpose | Key args |
|---|---|---|
| `sketch`  | 2D sketch | `plane`, `circle`/`rect`/`polygon` |
| `extrude` | extrude | `profile`, `length`, `dir` |
| `revolve` | revolve | `profile`, `axis`, `angle` |
| `fillet`  | fillet | `on` (edge ref), `radius` |
| `chamfer` | chamfer | `on` (edge ref), `dist` |
| `pocket`  | pocket | `on` (face ref), profile, `depth` |
| `groove`  | groove | `on`, `profile`, `axis` |
| `edit`    | single-value parameter edit — op type unchanged, no re-binding | `target` (feature ref), `set` (field name, bare identifier), `value` |

`edit` is an `edit_op` (§3): it has no `name =`, and unlike the ops above it never introduces a feature or changes derived names — see §8 for the `edit` vs `replace` boundary.

### 4.2 New Operations (this work, core of RQ1)

| Op | Purpose | Key args | Note |
|---|---|---|---|
| `replace`   | feature replacement | `target` (feature ref), `with` (new operation) | **must trigger downstream re-binding** |
| `pattern`   | patterned copy | `feature`, `type`(linear/circular), `count`, `spacing`/`angle` | instances referenced as a group |
| `mirror`    | mirror | `feature`, `plane` | |
| `constraint`| constraint declaration | `type`(dim/geom), `on`, `value` | read by the verify layer |

See §6 for `replace` re-binding rules.

---

## 5. Reference Grammar

Stable symbolic names, never coordinates.

```
body.face_top      # a named face
body.edge_top      # a named edge
body.axis          # feature axis
hole1              # whole feature
hole1.wall         # a derived face
pat1[*]            # all instances of a pattern
pat1[2]            # 3rd instance
```

Derived-name convention: `<feature>.<role>`, `role` ∈ {`face_top`, `face_bottom`, `axis`, `wall`, `floor`, `edge_top`, `edge_bottom`}. This is the full v1 set (registry.py `ROLES`, finalized in §8).

Which op produces which roles:

| Op | Roles it exposes |
|---|---|
| `sketch` | none — referenced only as a whole (used as a `profile` input) |
| `extrude` | `face_top`, `face_bottom`, `wall`, `axis`, `edge_top`, `edge_bottom` |
| `revolve` | `face_top`, `face_bottom`, `wall`, `axis`, `edge_top`, `edge_bottom` (v1 assumes a closed, capped profile — open-profile revolves are future work) |
| `pocket` / `groove` | `wall`, `floor` |
| `fillet` / `chamfer` | none new — they act on an existing edge ref, they don't name a new one |
| `replace` | inherits whatever roles the new feature (`with=`) exposes — see §6 |
| `pattern` / `mirror` | each instance conceptually carries the roles of the templated/mirrored feature; how `verify/` resolves `pat1[*].<role>` is still open (see §8) |

---

## 6. Replace & Re-binding (key difficulty for RQ2)

`replace` is the most central addition of this work relative to prior work. Semantics:

1. `replace(target=X, with=op(...))` substitutes a new feature X' for X at the same position in the sequence.
2. Every downstream statement that referenced `X.*` is auto-redirected to the **same-named derivation** of X' if it exists.
3. If X' lacks a derived name that X had, the parser raises a **re-binding conflict**, handled in `verify/` or falling back to the two-step "delete → verify → add" path (proposal risk R1).

Example: cylinder → prism

```dsl
# before
body = extrude(profile=circle_sk, length=200);
h    = pocket(on=body.face_top, ...);       # references body.face_top

# edit instruction: "swap the body from cylinder to hexagon"
replace(target=body, with=extrude(profile=hex_sk, length=200));
# body.face_top is still valid → h auto re-binds
```

---

## 7. Full Example

A 5-step chain (for the RQ2 benchmark):

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

---

## 8. Decisions (formerly "Open Items", closed out during M1)

- [x] **`edit` vs `replace` boundary**: if the op type is unchanged and only a scalar arg changes, use `edit` (no re-binding, see §4.1); if the op type itself changes (even to a similar-looking shape), use `replace` (triggers re-binding, §6).
- [x] **Minimal `constraint` set**: `type=dim` → `equal` / `range` / `ratio`; `type=geom` → `concentric` / `coplanar` / `parallel`. Chosen to directly cover the thresholds already in `config/default.yaml` (`min_wall_thickness_mm`, `min_hole_edge_dist_mm`, `dim_tolerance_mm`).
- [x] **`pat1[*]` count expansion**: expands to `pat1[0]` .. `pat1[count-1]`, where `count` is read from the originating `pattern` statement's `count` arg. The actual expansion logic lives in `verify/` (M6); this only fixes the semantics.
- [x] **Derived-name `role` enumeration**: finalized as `{face_top, face_bottom, axis, wall, floor, edge_top, edge_bottom}` — see the per-op table in §5. Mirrored in `dsl/registry.py`'s `ROLES`.
- [x] **Hand-written vs lark/antlr**: hand-written recursive descent — implemented in `dsl/parser.py`, no external parser-generator dependency.

---

## 9. Frozen-Spec Addendum (M2)

DSL v1 is frozen for the sequential-edit benchmark. Implementations must:

1. validate references before kernel execution and reject dangling derived roles;
2. preserve a replaced feature's public symbolic name and reject replacements
   that remove roles already required by downstream features;
3. treat benchmark steps as atomic—failed parse/reference checks do not mutate
   the registry used by later steps;
4. report `parse_ok`, `refs_valid`, and `prior_preserved` per step.

Benchmark-v1 fixtures live under `eval/benchmarks/chains_{3,5,10}step/`.
