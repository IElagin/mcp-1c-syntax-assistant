"""Чтение книги справки: контейнер V8 и zip внутри него."""

from pathlib import Path

import pytest

from src.parsers.v8_container import HelpBookArchive, HelpBookArchiveError
from tests.conftest import build_container, write_book

REAL_BOOK = Path(__file__).resolve().parents[1] / "data" / "hbk" / "shcntx_ru.hbk"


@pytest.fixture
def book(tmp_path):
    def make(files: dict, page_size: int = 512, extra: dict = None) -> Path:
        return write_book(tmp_path / "test_ru.hbk", files, page_size=page_size, extra=extra)
    return make


def test_archive_lists_every_file_of_the_book(book):
    path = book({"root.html": b"<html/>", "objects/Array.html": b"<html/>"})
    with HelpBookArchive(path) as archive:
        assert sorted(archive.names()) == ["objects/Array.html", "root.html"]


def test_archive_reads_file_content_by_name(book):
    path = book({"struct_For": "<h1>Для (For)</h1>".encode("utf-8")})
    with HelpBookArchive(path) as archive:
        assert archive.read("struct_For").decode("utf-8") == "<h1>Для (For)</h1>"


def test_archive_reads_content_split_across_pages(book):
    """Крупный элемент лежит цепочкой страниц, а не одним куском."""
    big = ("<p>" + "я" * 4000 + "</p>").encode("utf-8")
    path = book({"big.html": big}, page_size=64)
    with HelpBookArchive(path) as archive:
        assert archive.read("big.html") == big


def test_archive_tolerates_element_without_data(book):
    path = book({"root.html": b"<html/>"}, extra={"IndexMainData": b""})
    with HelpBookArchive(path) as archive:
        assert archive.names() == ["root.html"]


def test_archive_refuses_a_file_that_is_not_a_container(tmp_path):
    path = tmp_path / "not_a_book.hbk"
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 200)
    with pytest.raises(HelpBookArchiveError):
        HelpBookArchive(path)


def test_archive_refuses_a_container_without_file_storage(tmp_path):
    path = tmp_path / "empty_ru.hbk"
    path.write_bytes(build_container({"Book": b'{7,"Test"}'}))
    with pytest.raises(HelpBookArchiveError):
        HelpBookArchive(path)


@pytest.mark.slow
def test_archive_reads_the_whole_syntax_helper_book():
    """Настоящая книга: 48 682 файла, из них 23 125 карточек объектов."""
    if not REAL_BOOK.exists():
        pytest.skip(f"книга {REAL_BOOK} не найдена на этой машине")
    with HelpBookArchive(REAL_BOOK) as archive:
        names = archive.names()
    assert len(names) == 48682
    assert sum(1 for n in names if n.startswith("objects/") and n.endswith(".html")) == 23125
