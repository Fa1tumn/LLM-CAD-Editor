# FreeCAD Visual Test Guide

This guide explains how to generate and open the HTML visual test report for the DSL §3 example:

```text
sketch -> extrude -> pocket -> fillet
```

The report uses geometry produced by the real FreeCAD/OCCT kernel. It includes full-model renders,
enlarged top views, longitudinal sections, geometry measurements, test code, and live pytest output.

## Prerequisites

Run all commands from the repository root:

```bash
cd /home/ts01088978343/LLM-CAD-Editor
```

Create the Linux CAD development environment if it does not exist yet:

```bash
micromamba create -y -p "$PWD/.venv" -f environment.yml
echo "$PWD/.venv/lib" > .venv/lib/python3.11/site-packages/freecad.pth
```

The project environment contains FreeCAD, pytest, NumPy, and Matplotlib. Verify that FreeCAD is
available:

```bash
.venv/bin/python -c "import FreeCAD, Part; print(FreeCAD.Version())"
```

## Generate the Visual Test Report

Run:

```bash
.venv/bin/python scripts/render_section3_report.py
```

The command performs the following actions:

1. Compiles the DSL programs with `FreeCADBackend`.
2. Runs the real pocket and fillet pytest cases.
3. Tessellates the resulting OCCT solids.
4. Generates full-model, enlarged-top, and longitudinal-section PNG images.
5. Exports each stage as an STL file.
6. Writes the test code, pytest output, geometry data, and images into an HTML report.

A successful run prints:

```text
wrote visual report to .../artifacts/section3_visual/index.html
```

## Open the Report on Desktop Linux

If Linux has a desktop environment, run:

```bash
xdg-open artifacts/section3_visual/index.html
```

## Open the Report Through a Local Web Server

Start a web server from the repository root:

```bash
.venv/bin/python -m http.server 8000
```

Open the following address in a browser on the same machine:

```text
http://localhost:8000/artifacts/section3_visual/
```

Stop the server with `Ctrl+C`.

## Open the Report on a Remote Linux Server

Create an SSH tunnel from the local computer:

```bash
ssh -L 8000:localhost:8000 USER@SERVER_IP
```

In that SSH session, enter the repository and start the server:

```bash
cd /home/ts01088978343/LLM-CAD-Editor
.venv/bin/python -m http.server 8000
```

Open this address in the local browser:

```text
http://localhost:8000/artifacts/section3_visual/
```

## Run the Tests Without Generating the Report

Run only the two §3 kernel tests:

```bash
.venv/bin/python -m pytest -q \
  tests/test_kernel_geometry.py::test_section_3_pocket_removes_the_requested_axial_volume \
  tests/test_kernel_geometry.py::test_section_3_example_runs_through_fillet_on_the_pocketed_body
```

Run the complete test suite:

```bash
.venv/bin/python -m pytest -q
```

Run the linter:

```bash
.venv/bin/ruff check .
```

## Generated Files

All report files are written to `artifacts/section3_visual/`:

| File | Description |
|---|---|
| `index.html` | Visual test dashboard |
| `01-extrude.png` | Full extruded shaft |
| `02-pocket.png` | Full shaft after pocket cutting |
| `03-fillet.png` | Full shaft after top-edge filleting |
| `*-top.png` | Enlarged top 32 mm of each stage |
| `*-section.png` | Longitudinal section of each stage |
| `*.stl` | Geometry that can be opened in FreeCAD or another CAD viewer |

## Refresh After Code Changes

Regenerate the report after changing the compiler or tests:

```bash
.venv/bin/python scripts/render_section3_report.py
```

If the browser still displays old images, use `Ctrl+Shift+R` to perform a hard refresh.

## Troubleshooting

### `ModuleNotFoundError: No module named 'FreeCAD'`

Use `.venv/bin/python`, not the system `python` command:

```bash
.venv/bin/python scripts/render_section3_report.py
```

### Port 8000 is already in use

Use another port:

```bash
.venv/bin/python -m http.server 8080
```

Then open:

```text
http://localhost:8080/artifacts/section3_visual/
```

### The report shows `FAIL`

Read the `Live pytest output` section in the HTML page, then run the failing command directly in a
terminal for the complete traceback.
