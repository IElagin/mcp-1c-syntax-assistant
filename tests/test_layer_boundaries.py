"""Which package may import which — the rule quoted by AGENTS.md."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parent.parent / "src"

ALLOWED_IMPORTS = {
    "core": set(),
    "models": {"core"},
    "parsers": {"core", "models"},
    "search": {"core", "models"},
    "handlers": {"core", "models", "search"},
    "infrastructure": {"core", "models", "parsers"},
    "api": {"core", "models", "parsers", "search", "handlers", "infrastructure"},
    "app": {
        "core", "models", "parsers", "search",
        "handlers", "infrastructure", "api",
    },
}

ROOT_MODULES = {"main", "__init__"}


def _package_of(path: Path) -> str:
    relative = path.relative_to(SRC)
    return relative.parts[0] if len(relative.parts) > 1 else relative.stem


def _imported_packages(tree: ast.Module) -> list[tuple[str, int]]:
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.startswith("src."):
                imported.append((node.module.split(".")[1], node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    imported.append((alias.name.split(".")[1], node.lineno))
    return imported


def _source_files() -> list[Path]:
    return sorted(
        path for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def test_every_package_under_src_has_a_layer_rule():
    unruled = sorted({
        _package_of(path) for path in _source_files()
        if _package_of(path) not in ALLOWED_IMPORTS
        and _package_of(path) not in ROOT_MODULES
    })
    assert not unruled, (
        "packages without a row in ALLOWED_IMPORTS: " + ", ".join(unruled)
    )


def test_no_package_imports_outside_its_allowed_layers():
    violations = []
    for path in _source_files():
        package = _package_of(path)
        if package in ROOT_MODULES:
            continue
        allowed = ALLOWED_IMPORTS.get(package, set()) | {package}
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for imported, line in _imported_packages(tree):
            if imported not in allowed:
                violations.append(
                    f"{path.relative_to(SRC.parent).as_posix()}:{line}: "
                    f"{package} -> {imported}"
                )
    assert not violations, (
        "forbidden cross-package imports (see docs/dev/ARCHITECTURE.md):\n"
        + "\n".join(violations)
    )
