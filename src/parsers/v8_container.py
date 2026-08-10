"""Чтение книги справки 1С: контейнер V8 и zip внутри него."""

import io
import struct
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

from src.core.logging import get_logger

logger = get_logger(__name__)

NO_PAGE = 0x7FFFFFFF
FILE_HEADER_SIZE = 16
BLOCK_HEADER_SIZE = 31
ELEMENT_NAME_OFFSET = 20
ADDRESS_RECORD_SIZE = 12
CONTENT_ELEMENT = "FileStorage"


class HelpBookArchiveError(Exception):
    """Файл не является книгой справки 1С или испорчен."""


def _block_header(data: bytes, offset: int) -> Tuple[int, int, int]:
    """Размер данных, размер страницы и адрес следующей страницы."""
    header = data[offset:offset + BLOCK_HEADER_SIZE]
    if len(header) < BLOCK_HEADER_SIZE or header[:2] != b"\r\n" or header[-2:] != b"\r\n":
        raise HelpBookArchiveError(f"Нет заголовка блока по смещению {offset}")
    try:
        return int(header[2:10], 16), int(header[11:19], 16), int(header[20:28], 16)
    except ValueError as error:
        raise HelpBookArchiveError(
            f"Нечитаемый заголовок блока по смещению {offset}"
        ) from error


def _read_block(data: bytes, offset: int) -> bytes:
    data_size, page_size, next_page = _block_header(data, offset)
    body = bytearray()
    start = offset + BLOCK_HEADER_SIZE
    while True:
        body += data[start:start + min(page_size, data_size - len(body))]
        if len(body) >= data_size or next_page == NO_PAGE:
            break
        _, page_size, following = _block_header(data, next_page)
        start = next_page + BLOCK_HEADER_SIZE
        next_page = following
    if len(body) < data_size:
        raise HelpBookArchiveError(
            f"Блок по смещению {offset} обрывается: {len(body)} байт из {data_size}"
        )
    return bytes(body[:data_size])


def _element_name(header: bytes) -> str:
    raw = header[ELEMENT_NAME_OFFSET:].split(b"\x00\x00")[0]
    if len(raw) % 2:
        raw += b"\x00"
    return raw.decode("utf-16-le", "replace").rstrip("\x00")


def _elements(data: bytes) -> Dict[str, bytes]:
    table = _read_block(data, FILE_HEADER_SIZE)
    found: Dict[str, bytes] = {}
    for position in range(0, len(table) - len(table) % ADDRESS_RECORD_SIZE, ADDRESS_RECORD_SIZE):
        header_address, data_address, _ = struct.unpack_from("<III", table, position)
        if header_address == NO_PAGE:
            continue
        name = _element_name(_read_block(data, header_address))
        found[name] = b"" if data_address == NO_PAGE else _read_block(data, data_address)
    return found


class HelpBookArchive:
    """Файлы книги справки 1С, читаемые по имени."""

    def __init__(self, path: Path):
        path = Path(path)
        raw = path.read_bytes()
        if len(raw) < FILE_HEADER_SIZE + BLOCK_HEADER_SIZE:
            raise HelpBookArchiveError(f"Файл слишком мал для книги справки: {path}")

        elements = _elements(raw)
        if CONTENT_ELEMENT not in elements:
            raise HelpBookArchiveError(
                f"В книге {path} нет элемента {CONTENT_ELEMENT}, "
                f"есть только {sorted(elements)}"
            )
        try:
            self._files = zipfile.ZipFile(io.BytesIO(elements[CONTENT_ELEMENT]))
        except zipfile.BadZipFile as error:
            raise HelpBookArchiveError(
                f"Содержимое книги {path} не читается: {error}"
            ) from error

    def names(self) -> List[str]:
        """Имена файлов книги, без каталогов."""
        return [item.filename for item in self._files.infolist() if not item.is_dir()]

    def read(self, name: str) -> bytes:
        """Содержимое одного файла книги."""
        return self._files.read(name)

    def close(self) -> None:
        self._files.close()

    def __enter__(self) -> "HelpBookArchive":
        return self

    def __exit__(self, *exception) -> None:
        self.close()
