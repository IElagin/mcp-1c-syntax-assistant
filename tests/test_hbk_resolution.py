"""Выбор книги справки для индексации.

В каталоге может лежать несколько .hbk: русская книга, английская, книги по
языку запросов. Индексироваться должна ровно та, что задана настройкой, —
иначе сервер молча отвечает карточками не на том языке.
"""

import pytest

from src.infrastructure.indexing import resolve_hbk_file


@pytest.mark.unit
def test_picks_configured_file_not_first_alphabetically(tmp_path):
    """shcntx_root.hbk идёт раньше по алфавиту, но индексировать надо не его."""
    (tmp_path / "shcntx_root.hbk").write_bytes(b"")
    (tmp_path / "shcntx_ru.hbk").write_bytes(b"")

    assert resolve_hbk_file(str(tmp_path), "shcntx_ru.hbk").name == "shcntx_ru.hbk"


@pytest.mark.unit
def test_returns_none_when_configured_file_is_absent(tmp_path):
    """Чужая книга в каталоге не должна подменять собой отсутствующую нужную."""
    (tmp_path / "shquery_ru.hbk").write_bytes(b"")

    assert resolve_hbk_file(str(tmp_path), "shcntx_ru.hbk") is None


@pytest.mark.unit
def test_returns_none_when_directory_is_missing(tmp_path):
    """Отсутствие каталога — не повод падать с исключением."""
    assert resolve_hbk_file(str(tmp_path / "net-takogo"), "shcntx_ru.hbk") is None
