"""Initialise FreeCAD before any test module is imported.

`Part.so` links against the App layer that `import FreeCAD` sets up. Importing `Part`
into a process where that has not happened does not raise — it **segfaults**, during
collection, so pytest dies with no summary line and unrelated test files in the same
run never execute either.

Doing it here means a test module can write the natural `import Part` and still work.
Without this, the natural spelling is the fatal one.

CI has no kernel, so the import is allowed to fail: the FreeCAD-dependent modules
`importorskip` themselves anyway.
"""

from __future__ import annotations

import contextlib

with contextlib.suppress(ImportError):
    import FreeCAD  # noqa: F401
