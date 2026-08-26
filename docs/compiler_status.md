# FreeCAD Compiler Status

This document records the implemented compiler scope and the limitations that must remain visible
while the rest of grammar.md §4 is developed.

## Implemented Kernel Operations

The current FreeCAD backend supports the complete grammar.md §3 example:

| Operation | Implemented scope |
|---|---|
| `sketch` | XY/XZ/YZ circle and rectangle profiles |
| `extrude` | Positive linear extrusion normal to the sketch plane |
| `pocket` | Circular axial pocket from `face_top`, centered on `origin` or `<feature>.axis` |
| `fillet` | Outer `edge_top` fillet for the current terminal solid |

All linear dimensions accept bare values or `mm`. Supplying `deg` to a linear dimension is a compile
error. Operation names, duplicate arguments, identifiers, and references are validated before kernel
execution where the frozen grammar defines them.

## Operations Not Yet Implemented

The following grammar.md §4 operations still raise `CompileError` in `FreeCADBackend`:

- `revolve`
- `chamfer`
- `groove`
- `edit`
- `replace`
- `pattern`
- `mirror`
- `constraint`

Polygon sketches are also not compiled by the FreeCAD backend yet.

## Known Geometry Limitations

### Symbolic roles are not a general subshape resolver yet

`face_top` and `edge_top` are currently resolved using the feature axis and geometric extrema. This
works for the §3 shaft, but it is not sufficient for non-convex parts, multiple top faces, or several
equivalent top edges. A dedicated role-to-subshape resolver must retain role bindings after every
history rebuild.

### Pocket profiles are restricted

The current `pocket` implementation accepts only an inline circular profile. Arbitrary sketch
profiles, off-axis placement, face-local coordinates, and multiple target faces remain future work.

### Use optimal bounds for dimension verification

OCCT's ordinary `Shape.BoundBox` may conservatively include the control geometry of a fillet surface.
For the 40 mm diameter §3 shaft, it can report approximately 43.296 mm before tessellation. Use
`Shape.optimalBoundingBox()` or analytic geometry measurements for dimensional verification. The
optimal result for the example is exactly `40 × 40 × 200 mm`.

### PartDesign history is not parametric yet

The backend stores generated B-reps in `PartDesign::Feature` objects, but pocket and fillet are
currently direct Part boolean/fillet operations. Native Sketcher constraints, PartDesign feature
links, and parameter-driven history rebuild are required before `edit` and `replace` can work.

## Required Next Work

1. Implement a stable role-to-subshape resolver.
2. Define per-operation argument and unit schemas for the complete §4 operation set.
3. Add native or explicit feature-history rebuild support for `edit` and `replace`.
4. Add negative and multi-plane geometry tests for each newly supported operation.
5. Implement `verify/kernel.py` and ensure dimension checks use optimal or analytic measurements.
