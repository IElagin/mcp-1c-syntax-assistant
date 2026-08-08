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

PACKAGES = set(ALLOWED_IMPORTS)


def _relative_target(path: Path, level: int, module: str | None) -> str | None:
    base = path.parent.relative_to(SRC).parts
    trimmed = base[: max(0, len(base) - (level - 1))]
    if trimmed:
        return trimmed[0]
    return module.split(".")[0] if module else None


def _package_of(path: Path) -> str:
    relative = path.relative_to(SRC)
    return relative.parts[0] if len(relative.parts) > 1 else relative.stem


def _imported_packages(path: Path, tree: ast.Module) -> list[tuple[str, int]]:
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                target = _relative_target(path, node.level, node.module)
                targets = [target] if target else [alias.name for alias in node.names]
                imported.extend(
                    (name, node.lineno) for name in targets if name in PACKAGES
                )
            elif node.module == "src":
                imported.extend(
                    (alias.name, node.lineno)
                    for alias in node.names if alias.name in PACKAGES
                )
            elif node.module and node.module.startswith("src."):
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
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for imported, line in _imported_packages(path, tree):
            if imported not in allowed:
                violations.append(
                    f"{path.relative_to(SRC.parent).as_posix()}:{line}: "
                    f"{package} -> {imported}"
                )
    assert not violations, (
        "forbidden cross-package imports (see docs/dev/ARCHITECTURE.md):\n"
        + "\n".join(violations)
    )


def test_a_relative_import_resolves_to_the_package_it_lands_in():
    module = SRC / "search" / "anything.py"
    assert _relative_target(module, 1, "helpers") == "search"
    assert _relative_target(module, 2, "handlers") == "handlers"
    nested = SRC / "infrastructure" / "background" / "anything.py"
    assert _relative_target(nested, 2, "indexing") == "infrastructure"


def test_every_spelling_of_a_cross_package_import_is_seen():
    module = SRC / "search" / "anything.py"
    for source in (
        "from src.handlers import x",
        "import src.handlers.x",
        "from src import handlers",
        "from ..handlers import x",
        "from .. import handlers",
    ):
        seen = [package for package, _ in _imported_packages(module, ast.parse(source))]
        assert seen == ["handlers"], source
