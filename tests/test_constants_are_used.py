"""A constant nothing reads is a claim of a shared value that nothing shares."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parent.parent / "src"
CONSTANTS = SRC / "core" / "constants.py"


def _declared_names() -> set[str]:
    return {
        node.targets[0].id
        for node in ast.parse(CONSTANTS.read_text(encoding="utf-8-sig")).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }


def _names_mentioned_elsewhere() -> set[str]:
    mentioned = set()
    for path in sorted(SRC.rglob("*.py")):
        if path == CONSTANTS or "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Name):
                mentioned.add(node.id)
            elif isinstance(node, ast.alias):
                mentioned.add(node.name.split(".")[-1])
    return mentioned


def test_every_constant_is_read_somewhere():
    unread = sorted(_declared_names() - _names_mentioned_elsewhere())
    assert not unread, unread
