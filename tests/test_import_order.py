"""Guard the FreeCAD/Part import order across the whole repository.

Importing `Part` into a process that has not imported `FreeCAD` segfaults — it does not
raise, so there is no traceback and no failing test, just a dead interpreter. The root
`conftest.py` initialises FreeCAD before collection, which covers pytest; this test covers
everything else, including modules run as scripts, and it needs no kernel so it runs in CI
where the FreeCAD suites are skipped.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", ".git", "__pycache__", "checkpoints"}


def _python_files() -> list[Path]:
    return sorted(
        path
        for path in REPO.rglob("*.py")
        if not any(part in SKIP_DIRS for part in path.relative_to(REPO).parts)
    )


def _first_import_line(tree: ast.AST, module: str) -> int | None:
    """Line of the earliest `import <module>` / `from <module> import ...`, anywhere in the file."""
    lines = [
        node.lineno
        for node in ast.walk(tree)
        if (isinstance(node, ast.Import) and any(a.name.split(".")[0] == module for a in node.names))
        or (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == module)
    ]
    return min(lines) if lines else None


def test_the_repository_has_python_files_to_check():
    """Guard the guard: a broken discovery would make every assertion below vacuous."""
    files = _python_files()
    assert len(files) > 10
    assert REPO / "dsl" / "compiler.py" in files


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_part_is_never_imported_before_freecad(path: Path):
    tree = ast.parse(path.read_text(), filename=str(path))
    part = _first_import_line(tree, "Part")
    if part is None:
        return

    freecad = _first_import_line(tree, "FreeCAD")
    relative = path.relative_to(REPO)
    assert freecad is not None, (
        f"{relative}:{part} imports Part without importing FreeCAD. Part.so links against "
        "the App layer FreeCAD sets up; without it this segfaults instead of raising."
    )
    assert freecad < part, (
        f"{relative} imports Part at line {part} but FreeCAD only at line {freecad}. "
        "The order is load-bearing — reversing it segfaults the interpreter."
    )


def test_the_compiler_still_orders_its_lazy_imports_correctly():
    """dsl/compiler.py is the one place that actually imports Part, so pin it explicitly."""
    tree = ast.parse((REPO / "dsl" / "compiler.py").read_text())
    freecad = _first_import_line(tree, "FreeCAD")
    part = _first_import_line(tree, "Part")
    assert freecad is not None and part is not None
    assert freecad < part
