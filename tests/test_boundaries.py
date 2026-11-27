"""ADR-002: one-way bounded-context imports, Catalog -> Identity -> Compute -> Decision -> Surface.

Mirrors the import-linter `layers` contract in pyproject.toml (run in CI as `lint-imports`) so the
rule is also enforced wherever only pytest runs.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "spine"
ORDER = ["catalog", "identity", "compute", "decision", "surface"]


def _context_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for n in names:
            parts = n.split(".")
            if parts[0] == "spine" and len(parts) > 1 and parts[1] in ORDER:
                found.add(parts[1])
    return found


def violations(root: Path = SRC) -> list[str]:
    out = []
    for ctx in ORDER:
        for py in sorted((root / ctx).rglob("*.py")):
            for target in _context_imports(py):
                if ORDER.index(target) > ORDER.index(ctx):
                    out.append(f"{py.relative_to(root)} imports higher context spine.{target}")
    return out


def test_all_five_contexts_exist() -> None:
    assert all((SRC / c / "__init__.py").is_file() for c in ORDER)


def test_no_reverse_imports() -> None:
    assert violations() == []


def test_checker_catches_a_reverse_import(tmp_path: Path) -> None:
    for c in ORDER:
        (tmp_path / c).mkdir()
        (tmp_path / c / "__init__.py").write_text("")
    (tmp_path / "catalog" / "bad.py").write_text("from spine.surface.models import Memo\n")
    assert violations(tmp_path) == ["catalog/bad.py imports higher context spine.surface"]


def test_import_linter_contract() -> None:
    lint = shutil.which("lint-imports")
    if lint is None:
        pytest.skip("import-linter not installed")
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([lint], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
