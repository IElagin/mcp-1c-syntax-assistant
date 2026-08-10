"""Чтение книги справки: контейнер V8 и zip внутри него."""

import struct
from pathlib import Path

import pytest

import src.parsers.v8_container as v8_container
from src.parsers.v8_container import FILE_HEADER_SIZE, NO_PAGE, HelpBookArchive, HelpBookArchiveError
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


def test_archive_opens_a_book_whose_element_has_an_empty_data_block(book):
    """Пустой служебный элемент не мешает читать файлы книги."""
    path = book({"root.html": b"<html/>"}, extra={"IndexMainData": b""})
    with HelpBookArchive(path) as archive:
        assert archive.names() == ["root.html"]
        assert archive.read("root.html") == b"<html/>"


def test_archive_opens_a_book_whose_element_has_no_data_address(tmp_path):
    """Элемент, объявленный в таблице без адреса данных (data_address == NO_PAGE)."""
    from tests.conftest import build_container, zip_of

    files = {"root.html": b"<html/>"}
    elements = {
        "Book": b'{7,"Test"}',
        "FileStorage": zip_of(files),
        "IndexMainData": None,
    }
    path = tmp_path / "with_no_data_address.hbk"
    path.write_bytes(build_container(elements))
    with HelpBookArchive(path) as archive:
        assert archive.names() == ["root.html"]
        assert archive.read("root.html") == b"<html/>"


def _container_with_a_self_referencing_block(data_size: int, page_size: int) -> bytes:
    """Контейнер, чей единственный блок объявляет себя же следующей страницей."""
    file_header = struct.pack("<IIII", NO_PAGE, page_size or 512, 1, 0)
    return file_header + b"\r\n%08x %08x %08x \r\n" % (data_size, page_size, FILE_HEADER_SIZE)


def test_archive_refuses_a_block_that_declares_a_zero_length_page(tmp_path):
    """Страница нулевой длины не добавляет байтов — раньше чтение крутилось вечно."""
    path = tmp_path / "zero_page_ru.hbk"
    path.write_bytes(_container_with_a_self_referencing_block(data_size=100, page_size=0))
    with pytest.raises(HelpBookArchiveError, match="нулевого размера"):
        HelpBookArchive(path)


def test_archive_refuses_a_page_chain_that_never_ends(tmp_path):
    """Цепочка страниц, замкнутая на себя, обязана кончиться ошибкой, а не зависанием."""
    path = tmp_path / "looping_ru.hbk"
    path.write_bytes(_container_with_a_self_referencing_block(data_size=100, page_size=64))
    with pytest.raises(HelpBookArchiveError, match="не кончается"):
        HelpBookArchive(path)


def test_archive_refuses_a_file_bigger_than_the_size_limit(book, monkeypatch):
    """Читатель книги защищает себя сам, а не полагается на проверку в HBKParser."""
    path = book({"root.html": b"<html/>"})
    monkeypatch.setattr(v8_container, "MAX_FILE_SIZE_MB", 0)
    with pytest.raises(HelpBookArchiveError, match="МБ"):
        HelpBookArchive(path)


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
