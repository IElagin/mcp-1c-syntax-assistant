"""Версии платформы: у каждой своя книга справки и свой индекс (docs/CONFIGURATION.md#версии-платформы)."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.core.config import settings, split_versions

UNVERSIONED = ""


class UnknownVersionError(ValueError):
    """Запрошена версия, которой нет в HELP_VERSIONS."""

    def __init__(self, version: str, available: List[str]):
        super().__init__(version)
        self.version = version
        self.available = available


@dataclass(frozen=True)
class HelpVersion:
    """Версия платформы, каталог её книг справки и её индекс."""

    name: str
    hbk_directory: str
    index: str

    @property
    def hbk_file(self) -> Path:
        return Path(self.hbk_directory) / settings.data.hbk_filename


def configured_versions() -> List[str]:
    """Версии из HELP_VERSIONS; пусто — одна книга без версии."""
    return split_versions(settings.help_versions)


def default_version() -> str:
    """DEFAULT_HELP_VERSION, иначе первая из HELP_VERSIONS, иначе книга без версии."""
    versions = configured_versions()
    if not versions:
        return UNVERSIONED
    return settings.default_help_version.strip() or versions[0]


def help_version(name: str) -> HelpVersion:
    """Книга без версии — data/hbk и help1c_docs; версия — data/hbk/<версия> и help1c_docs_<версия>."""
    if name == UNVERSIONED:
        return HelpVersion(UNVERSIONED, settings.data.hbk_directory, settings.elasticsearch_index)
    return HelpVersion(
        name,
        str(Path(settings.data.hbk_directory) / name),
        f"{settings.elasticsearch_index}_{name.replace('.', '_')}",
    )


def resolve_version(requested: Optional[str]) -> HelpVersion:
    """Версия запроса; None или пусто — версия по умолчанию. Неизвестная — UnknownVersionError."""
    name = (requested or "").strip() or default_version()
    versions = configured_versions()
    if name != UNVERSIONED and name not in versions:
        raise UnknownVersionError(name, versions)
    return help_version(name)


def all_versions() -> List[HelpVersion]:
    """Все книги, которые сервер индексирует: по версиям или одна без версии."""
    return [help_version(name) for name in configured_versions() or [UNVERSIONED]]
