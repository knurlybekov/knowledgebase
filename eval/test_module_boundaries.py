"""Cross-app imports must come from `<app>.api`. Walks every production .py
file with `ast`; tests, migrations and management commands are out of scope."""

import ast
import pathlib
from collections.abc import Iterable

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
APPS = {
    "accounts", "organizations", "connectors", "knowledge", "retrieval", "answers",
    "investigations", "mcp_server", "decisions", "web", "infra", "eval",
}


def _excluded(path: pathlib.Path) -> bool:
    parts = path.parts
    return (
        "tests" in parts
        or path.name.startswith("test_")
        or ("management" in parts and "commands" in parts)
        or "migrations" in parts
        or "__pycache__" in parts
    )


def _iter_py_files() -> Iterable[pathlib.Path]:
    for app in APPS:
        for path in (PROJECT_ROOT / app).rglob("*.py"):
            if not _excluded(path):
                yield path


def _type_checking_ranges(tree: ast.AST) -> list[tuple[int, int]]:
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if is_tc and node.body:
                ranges.append((node.lineno, getattr(node.body[-1], "end_lineno", node.lineno)))
    return ranges


def _imports(tree: ast.AST) -> Iterable[str]:
    ranges = _type_checking_ranges(tree)
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", None)
        if lineno is not None and any(a <= lineno <= b for a, b in ranges):
            continue
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name


def _violation(path: pathlib.Path, source_app: str, imported: str) -> str | None:
    if not any(imported == app or imported.startswith(app + ".") for app in APPS):
        return None
    target = imported.split(".")[0]
    if target == source_app:
        return None
    parts = imported.split(".")
    if len(parts) == 1 or parts[1] == "api":
        return None
    return f"{path}: {source_app}/ imports `{imported}` (internal of {target}/). Use `{target}.api`."


def test_no_cross_app_internal_imports():
    violations = []
    for path in _iter_py_files():
        source_app = path.relative_to(PROJECT_ROOT).parts[0]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for imported in _imports(tree):
            v = _violation(path, source_app, imported)
            if v:
                violations.append(v)
    assert not violations, "Module-boundary violations:\n  " + "\n  ".join(violations)
