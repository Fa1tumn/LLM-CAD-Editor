# P0 Visual Acceptance Report

This report turns the current `docs/p0_geometry_fidelity.md` acceptance matrix into auditable visual
evidence produced by the real FreeCAD/OCCT kernel. It deliberately keeps the overall gate at
**PASS** now that every required P0 row has real-kernel evidence. The page still states the boundary
between P0 geometry fidelity and later P2/P3 selector and enforced-constraint work.

## Generate

From the repository root, run:

```bash
.venv/bin/python scripts/render_p0_report.py
```

The command:

1. renders circle, rectangle, polygon, hex, XZ-plane, and YZ-plane solids;
2. highlights the exact OCCT entities resolved for `face_top`, `edge_top`, `wall`, and `floor`;
3. records provenance, history revision, B-rep hash, cardinality, filter steps, and signatures;
4. demonstrates that an ambiguous unique role raises instead of choosing the first match;
5. renders fixed-scale before/after comparisons for transactional `edit` and `replace`;
6. renders revolve, chamfer, groove, linear/circular pattern, mirror, and constraint cases;
7. runs the focused P0 evidence tests and embeds their live output.

## Open

If the repository web server is already running on port 8000, open:

```text
http://localhost:8000/artifacts/p0_visual/
```

Otherwise start it from the repository root:

```bash
.venv/bin/python -m http.server 8000
```

Then open the same URL in a browser. Use `Ctrl+Shift+R` after regenerating the report if the browser
shows cached images.

The generated HTML, PNG files, and independently inspectable STL models are stored under
`artifacts/p0_visual/`.
