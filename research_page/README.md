# Research project page

A static page introducing the project: the grammar, what reference-stability buys, and an honest
status table. `index.html` has no build step and no external assets beyond Google Fonts — open it
directly, or serve the folder:

```bash
python -m http.server 8000 --directory research_page
```

## The figures are compiled, not drawn

Every render is the actual OCCT solid `dsl/compiler.py` produces from the DSL source shown beside it.
`render_figures.py` compiles each program, tessellates the resulting shape and renders it, so the page
cannot drift from the compiler:

```bash
.venv/bin/pip install matplotlib        # deliberately not in requirements.txt
.venv/bin/python research_page/render_figures.py
```

This needs the FreeCAD-backed venv described in `CLAUDE.md`. Without the kernel the script cannot run
at all, which is the point — there is no fallback that would quietly produce a mock-up.

The script prints the measured geometry it renders, so the numbers quoted on the page can be checked
against it:

```
hero            volume   173778.8
stab-a          w=80   boss centre (40, 40)
stab-b          w=128  boss centre (64, 64)
planes          (0,0,0)-(14,14,70) (0,-70,0)-(14,0,14) (0,0,0)-(70,14,14)
planes-before   (0,0,0)-(14,14,70) (0,0,0)-(14,14,70) (0,0,0)-(14,14,70)
```

`planes-before` reproduces the pre-fix compiler by compiling the same three bodies on `plane=XY` —
which is exactly what the old code did with any plane — so the "before" panel is a real output rather
than an illustration.

## Two things to keep in mind when editing

**Compared figures must share one canvas.** `stab-a`/`stab-b` and `planes`/`planes-before` are rendered
with `tight=False` and a fixed `radius`, then cropped together by `crop_pair_to_union`. The page scales
every image to the same width, so cropping each to its own content would rescale them independently and
silently destroy the comparison the figure exists to make.

**The status and target sections are deliberately unflattering.** The targets in §07 have not been
measured — the model layer does not exist yet — and the page says so. If that changes, change the page;
do not let it imply results it does not have.
