# Assembly mating — proposed `grammar.md` §9 addendum

> Status: prototype implemented in `assembly/mates.py`, 24 tests, no kernel required.
> The grammar itself is unchanged; this is a proposal for the vocabulary and the checks.

## The finding that decides the design

**Fastener mating is parameter algebra, not geometry.** Whether an M8×1.25 bolt accepts an
M8×1.25 nut is decidable from the declarations alone — no solid, no boolean, no solver. That
puts it in the cheapest possible tier: a closed-form check that runs at compile time and
either passes or names the reason it did not.

The second finding is that it is cheaper still than expected:

```dsl
t_b = thread(form=M, d=8, pitch=1.25, hand=right, fit="6g");
i_b = interface(on=shank.wall, kind=male_thread, thread=t_b, engage=25);
m1  = mate(a=i_b, b=i_n, kind=threaded);
```

**This already parses under DSL v1.** `thread`, `interface` and `mate` are ordinary
`name = op(args);` statements (`grammar.md` §3), and `[key=value]` lists and nested op calls
are already in the value grammar. No parser change is needed.

The only blocker is vocabulary: `M`, `right`, `male_thread` and `threaded` are bare
identifiers, so `registry.validate_refs` currently rejects them as dangling references —
exactly the `LITERAL_ROOTS` trap `CLAUDE.md` warns about. That is a one-line data change,
not a language change.

## Two levels, and only one of them is free

| | Level A — interface algebra | Level B — geometric admissibility |
|---|---|---|
| Decides | thread form, diameter, pitch, hand, tolerance class, engagement, grip length | clearance hole, interference, wrench access, wall thickness at the boss |
| Needs | the declarations | the compiled solid |
| Cost | microseconds, runs in CI without FreeCAD | a kernel run per candidate |
| Status | **implemented** (`assembly/mates.py`) | not started |

Level A is where "the compiler refuses to build an assembly that cannot be assembled" is
genuinely achievable. It is implemented and every rule is covered by a test that asserts the
specific failure message, so the message is usable as self-repair feedback rather than just a
rejection.

## The rules Level A applies

For `kind=threaded`, in the order they are checked:

1. exactly one `male_thread` and one `female_thread`
2. `form` equal (M vs UNC is not a near miss, it is a different thread)
3. nominal diameter `d` equal
4. `pitch` equal
5. `hand` equal
6. tolerance class written for the correct side — ISO 965 writes external classes lowercase
   (`6g`) and internal uppercase (`6H`), so `6g` on a nut is a specification error, not a
   tight fit
7. thread engagement ≥ `min_engagement_ratio × d` (`config/default.yaml`, default 0.8)

For `kind=clearance`: the hole must be larger than the fastener, and — once the plant supplies
a table — at least the recommended clearance. `clearance_hole_mm` in the config is
**deliberately empty**: it is standards data and must be entered and signed off by an
engineer, not guessed. Until then, clearance checking asserts only that the fastener fits
through at all, and says so.

`check_grip` covers the stack: bolt length ≥ clamped thickness + nut height + protrusion.

## The soundness gap, stated plainly

Level A verifies that two **declarations** are compatible. It does not verify that the
geometry implements its own declaration. An interface whose `on=` face is really 7.9 mm across
while the declaration says `d=8` passes every check.

This is pinned by a test (`test_the_check_believes_the_declaration_not_the_geometry`) so that
a passing mate is never read as more than it is. Closing the gap means checking each interface
against the solid its `on=` reference resolves to — which needs the kernel, and needs the
role-to-geometry resolution that the fillet/chamfer work has to build anyway.

## What this costs the language

Three new operations and four small closed sets of vocabulary. Weighed against
`grammar.md` §1.4 — the DSL must stay easy for a 7–14B model to emit — this is favourable:
the statements have the same shape as every other statement, and the vocabulary is closed, so
it is checkable rather than free text.

## Consequences elsewhere

- **`finish()` fusing every solid is wrong for assemblies.** A bolt and a nut must stay
  separate bodies; fusing them produces a single solid that is not the assembly. The current
  behaviour is right for a single part and has to become part-aware before assemblies compile.
- **Assembly needs a part concept.** Today one program is one model, and `registry.py` tracks
  features within it. Parts, placements and cross-part references do not exist.
- **`replace` re-binding extends to interfaces.** If a replacement drops the face an interface
  is `on=`, the mate must fail — this is RQ2's reference-stability problem appearing in
  assembly, and it is an argument that the two should be designed together.

## Suggested sequencing

1. Add the vocabulary to `LITERAL_ROOTS` so these statements survive `compile_program` — the
   checker already exists and would then run inside the normal pipeline.
2. Bind interfaces to geometry, closing the soundness gap, alongside the edge/face role
   resolution work.
3. Introduce parts and placements; revisit `finish()`.
4. Level B geometric admissibility.
