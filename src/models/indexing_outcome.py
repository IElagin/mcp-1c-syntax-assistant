"""Чем кончилась индексация книги — как данные, а не как булево."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class OutcomeKind(str, Enum):
    """Ветка, которой кончилась индексация."""

    INDEXED = "indexed"
    PARSE_FAILED = "parse_failed"
    NOTHING_TO_INDEX = "nothing_to_index"
    PAGE_LOSS_TOO_HIGH = "page_loss_too_high"
    INDEX_WRITE_FAILED = "index_write_failed"
    ERROR = "error"


@dataclass(frozen=True)
class IndexingOutcome:
    """Исход индексации: вид и то, что к нему прилагается."""

    kind: OutcomeKind
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.kind is OutcomeKind.INDEXED

    @classmethod
    def indexed(cls, documents: int, articles: int) -> "IndexingOutcome":
        return cls(OutcomeKind.INDEXED, {"documents": documents, "articles": articles})

    @classmethod
    def parse_failed(cls, file_path: str) -> "IndexingOutcome":
        return cls(OutcomeKind.PARSE_FAILED, {"file_path": file_path})

    @classmethod
    def nothing_to_index(cls, file_path: str) -> "IndexingOutcome":
        return cls(OutcomeKind.NOTHING_TO_INDEX, {"file_path": file_path})

    @classmethod
    def page_loss_too_high(cls, parsed: int, attempted: int, share: float) -> "IndexingOutcome":
        return cls(
            OutcomeKind.PAGE_LOSS_TOO_HIGH,
            {"parsed": parsed, "attempted": attempted, "share": share},
        )

    @classmethod
    def index_write_failed(cls, index: str) -> "IndexingOutcome":
        return cls(OutcomeKind.INDEX_WRITE_FAILED, {"index": index})

    @classmethod
    def error(cls, text: str) -> "IndexingOutcome":
        return cls(OutcomeKind.ERROR, {"error": text})
