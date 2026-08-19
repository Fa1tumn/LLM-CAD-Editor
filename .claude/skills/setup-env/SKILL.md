---
name: setup-env
description: Build or repair the project venv so FreeCAD/OCCT is importable, then verify the kernel actually works. Use on a fresh clone, a new machine, or when FreeCAD imports fail / FreeCADBackend raises CompileError.
disable-model-invocation: true
---

The project venv must be created **from FreeCAD's bundled Python**, not system Python. FreeCAD ships
its own conda-forge Python (3.11) and its `FreeCAD.so` / `Part.so` are built against it — a venv from
any other interpreter cannot import them.

## Steps

### 1. Locate FreeCAD

macOS: `/Applications/FreeCAD.app/Contents/Resources` (bundled `bin/python`, `bin/freecadcmd`, `lib/`).
If absent, install it — `brew install --cask freecad` or `conda install -c conda-forge freecad` — and
stop to tell the user, since the download is large.

Linux: find the install prefix that contains `FreeCAD.so`, and use its Python.

### 2. Create the venv from that Python

```sh
FC=/Applications/FreeCAD.app/Contents/Resources
"$FC/bin/python" -m venv .venv
.venv/bin/python -V    # expect 3.11.x
```

### 3. Put FreeCAD's lib dir on the venv path

A `.pth` file, so plain `pytest` and `python` work with no `PYTHONPATH` juggling:

```sh
SP=$(.venv/bin/python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
echo "$FC/lib" > "$SP/freecad.pth"
```

### 4. Install dependencies

```sh
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install ruff
```

`requirements.txt` deliberately omits FreeCAD (not pip-installable). If the heavy ML stack (torch,
transformers, peft, bitsandbytes) fails or is unwanted on this machine, install only
`pytest pyyaml numpy ruff` — those targets the 24GB GPU training host, not a laptop. Say which path
you took.

### 5. Verify — all three must pass

```sh
.venv/bin/python -c "import FreeCAD, Part; print(FreeCAD.Version()[:3], Part.makeBox(10,20,30).Volume)"
.venv/bin/python -c "from dsl.compiler import FreeCADBackend; FreeCADBackend(); print('backend ok')"
.venv/bin/python -m pytest -q
```

Expected: a version triple and `6000.0`; `backend ok`; all tests passing.

If `FreeCADBackend()` raises `CompileError`, the `.pth` from step 3 is wrong or missing — that error
message intentionally suggests `SymbolicBackend`, but for this project the kernel is required, so fix
the path instead of switching backends.

## Report

State the FreeCAD version, the venv Python version, whether the ML stack was installed, and the
output of all three verification commands. Do not claim success without pasting them.
