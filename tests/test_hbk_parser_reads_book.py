"""Разбор книги справки поверх контейнерного читателя."""

from pathlib import Path

import pytest

from src.parsers.hbk_parser import HBKParser

REAL_BOOK = Path(__file__).resolve().parents[1] / "data" / "hbk" / "shcntx_ru.hbk"


@pytest.mark.real_book
def test_parser_produces_the_same_document_count_as_before():
    """Смена извлечения не меняет состав книги: 23 125 документов."""
    if not REAL_BOOK.exists():
        pytest.skip(f"книга {REAL_BOOK} не найдена на этой машине")
    parsed = HBKParser().parse_file(str(REAL_BOOK))
    assert parsed is not None
    assert parsed.errors == []
    assert len(parsed.documentation) == 23125


@pytest.mark.real_book
def test_parser_page_paths_use_forward_slashes():
    """Разделитель больше не зависит от платформы сборки."""
    if not REAL_BOOK.exists():
        pytest.skip(f"книга {REAL_BOOK} не найдена на этой машине")
    parsed = HBKParser().parse_file(str(REAL_BOOK))
    assert not any("\\" in doc.source_file for doc in parsed.documentation)


def test_parser_reports_a_file_that_is_not_a_book(tmp_path):
    """Испорченный файл — ошибка в отчёте, а не молчаливый пустой разбор."""
    path = tmp_path / "broken_ru.hbk"
    path.write_bytes(b"not a container at all" * 10)
    parsed = HBKParser().parse_file(str(path))
    assert parsed is not None
    assert parsed.errors
    assert parsed.documentation == []
