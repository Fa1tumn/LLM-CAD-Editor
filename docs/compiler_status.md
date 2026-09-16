# FreeCAD Compiler Status

This document records the implemented compiler scope and the limitations that must remain visible
while the rest of grammar.md §4 is developed.

## Implemented Kernel Operations

The current FreeCAD backend supports the complete grammar.md §4 v1 operation set:

| Operation | Implemented scope |
|---|---|
| `sketch` | XY/XZ/YZ circle, rectangle, and polygon profiles |
| `extrude` | Positive linear extrusion of named sketches or inline `hex(r=...)` profiles |
| `revolve` | Closed Profile revolution about `origin` in the sketch plane or `<feature>.axis`, with a `(0, 360] deg` angle |
| `pocket` | Circular axial pocket from `face_top`, centered on `origin` or `<feature>.axis`, using the shared Face compiler |
| `fillet` | Outer `edge_top` fillet for the current terminal solid |
| `chamfer` | Outer `edge_top` chamfer over the resolver's complete edge collection |
| `groove` | Axisymmetric subtractive revolution of a referenced axial-plane Profile |
| `pattern` | Linear or circular solid pattern; pocket/groove patterns replay transformed cutters |
| `mirror` | Solid or pocket/groove-effect reflection across XY/XZ/YZ |
| `constraint` | Validated v1 declaration retained for the verify layer without pretending to modify geometry |
| `edit` | Transactional top-level parameter edit followed by target-and-downstream history replay |
| `replace` | Transactional operation replacement under the original feature name followed by downstream replay |

All linear dimensions accept bare values or `mm`. Supplying `deg` to a linear dimension is a compile
error. Operation names, duplicate arguments, identifiers, and references are validated before kernel
execution where the frozen grammar defines them.

## Unified 2D Profile Pipeline

`ProfileSpec` is the internal representation for every supported 2D profile. Named sketches are
normalized when the `sketch` statement executes: circles retain an analytic radius, while rectangle,
polygon, and hexagon profiles become closed vertex loops. The FreeCAD backend then follows one path:

```text
ProfileSpec -> Edge collection -> closed Wire -> planar Face -> Face.extrude()
```

The same Face compiler creates the circular cutter used by `pocket`; `Part.makeCylinder()` and
`Part.makeBox()` are no longer used as profile-specific shortcuts. Polygon validation rejects malformed
points, duplicates, zero-area loops, self-intersection, and non-linear units before OCCT execution.
Explicitly closed polygon lists are normalized by removing the repeated final point.

Implemented FreeCAD operations reject unknown arguments with `CompileError`, so parsed values are not
silently ignored. Real-kernel tests cover circle/rectangle compatibility, polygon and hexagon volume,
XY/XZ/YZ placement, shared pocket compilation, and invalid-profile behavior.

## Stable Symbolic Role Resolution

`dsl/subshapes.py` resolves authored roles through a shared `ResolvedSubshape` contract. Each result
records the source feature and operation, history version, current B-rep hash, topology kind,
cardinality, candidate/filter counts, selection reason, and geometric signatures. Roles that require
one entity reject both zero and multiple matches; collection roles return every entity in stable
geometric order.

Current role semantics are:

| Role | Cardinality | Selection |
|---|---|---|
| `face_top` / `face_bottom` | one | Unique planar cap at the maximum/minimum feature-axis extent |
| `edge_top` / `edge_bottom` | many, nonempty | Complete outer wire of the resolved cap; hole rims excluded |
| Extrude `wall` | many, nonempty | Connected lateral component from the outer top boundary |
| Pocket `floor` | one | Nearest upward planar face below the top cap |
| Pocket `wall` | many, nonempty | Connected lateral component from the pocket-floor boundary |
| Groove `floor` | one | Deepest coaxial cylindrical face |
| Groove `wall` | many, nonempty | Faces adjacent to both sides of the groove floor |

Pocket and fillet now consume these bindings. A polygon fillet receives the complete top rim rather
than an arbitrary edge, and a pocketed/filleted shaft keeps body-wall and pocket-wall provenance
separate across history versions. See `docs/p0_geometry_fidelity.md` for the acceptance matrix.

## Explicit Feature-History Rebuild

The backend records every successfully compiled named or anonymous feature as a replayable operation.
`edit` updates an existing top-level argument; `replace` swaps the recorded operation and arguments
while preserving the authored feature name. The target and every later record receive a new revision,
then the full history is regenerated in source order so downstream pocket/fillet features bind to the
new geometry.

Rebuild is transactional. If a changed dimension is invalid, a replacement operation is unsupported,
or a replacement introduces a forward history dependency, the backend restores the previous records
and regenerates the last valid B-rep. Failed edits therefore do not leave a partial document or stale
role provenance.

## Known Geometry Limitations

### Pattern/mirror instance selectors remain P2/M6 work

The kernel creates pattern and mirror geometry now. Expansion and verification of `pat1[*].role` and
`pat1[2].role` remain assigned to the verify layer by grammar.md §8. Direct ambiguous group-role
queries still fail cardinality rather than choosing an arbitrary instance.

### Pocket profiles are restricted

The current `pocket` implementation accepts an inline circular profile centered on `origin` or the
target axis. The two centers are geometrically distinct for offset bodies. Arbitrary referenced
pocket sketches and face-local coordinates are future extensions. Through-pockets are explicitly
rejected because v1 promises every pocket has a resolvable `floor` role.

### Checked CSG is a bounded contract

Pocket and groove validate positive/nondegenerate tools, containment or intersection, non-erasure,
valid nonempty results, and measurable volume change. Pattern and mirror reject duplicate/no-op
placements. These checks form the P0 Total-CSG subset; they do not claim arbitrary OCCT Booleans are
mathematically total.

### Use optimal bounds for dimension verification

OCCT's ordinary `Shape.BoundBox` may conservatively include the control geometry of a fillet surface.
For the 40 mm diameter §3 shaft, it can report approximately 43.296 mm before tessellation. Use
`Shape.optimalBoundingBox()` or analytic geometry measurements for dimensional verification. The
optimal result for the example is exactly `40 × 40 × 200 mm`.

### History is explicit replay, not native PartDesign history

The backend stores generated B-reps in `PartDesign::Feature` objects, but pocket and fillet are
currently direct Part boolean/fillet operations. `edit` and `replace` rebuild the explicit DSL history;
native Sketcher constraints and native PartDesign feature links are not constructed.

## Required Next Work

1. Begin P1 typed units and canonical conversion without weakening the completed P0 contracts.
2. Implement P2 selector/instance evidence and wrong-binding-rate benchmarks.
3. Convert retained constraint declarations into P3 pass/fail/unknown obligations.
4. Extend pocket to referenced face-local profiles under an explicit role contract.
5. Implement `verify/kernel.py` and ensure dimension checks use optimal or analytic measurements.
