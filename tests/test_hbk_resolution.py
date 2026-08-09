"""Выбор книги справки для индексации.

В каталоге может лежать несколько .hbk: русская книга, английская, книги по
языку запросов. Индексироваться должна ровно та, что задана настройкой, —
иначе сервер молча отвечает карточками не на том языке.
"""

from pathlib import Path

import pytest

from src.infrastructure.indexing import resolve_hbk_file
from src.parsers.dialects import RU_DIALECT
from src.parsers.hbk_parser import HBKParser


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


@pytest.mark.integration
@pytest.mark.parser
def test_single_page_is_parsed_from_the_archive():
    """Разбор одной страницы архива обязан отдавать документ, а не список ошибок.

    Метод не звали ни из кода, ни из тестов, и он не работал ни на одной
    странице сразу по трём причинам: искал команду 7zip через несуществующий
    _get_7zip_command (AttributeError на первом же вызове), отдавал парсеру
    декодированную строку вместо байтов (разбор кодировки на строке возвращает
    None — «не удалось распарсить HTML» на странице, которая при обычной
    индексации разбирается молча) и складывал результат в поле documents,
    которого у модели ParsedHBK нет.

    Каждая из трёх ошибок маскировала следующую, поэтому тест проверяет
    результат, а не отсутствие исключения.
    """
    book = Path("data/hbk/shcntx_ru.hbk")
    if not book.exists():
        pytest.skip("книга справки недоступна")

    parsed = HBKParser(dialect=RU_DIALECT).parse_single_file_from_archive(
        str(book), "objects/Global context/methods/catalog20/StrTemplate4527.html"
    )

    assert parsed is not None and not parsed.errors, parsed.errors if parsed else None
    assert len(parsed.documentation) == 1
    doc = parsed.documentation[0]
    assert doc.name == "СтрШаблон (StrTemplate)"
    assert doc.full_path == "СтрШаблон"
