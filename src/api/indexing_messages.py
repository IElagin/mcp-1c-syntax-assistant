"""Исход индексации словами для оператора — одним местом на оба эндпоинта."""

from src.models.indexing_outcome import IndexingOutcome, OutcomeKind

_MESSAGES = {
    OutcomeKind.INDEXED: (
        "Индексация завершена: документов {documents}, из них статей {articles}."
    ),
    OutcomeKind.PARSE_FAILED: (
        "Книга {file_path} не разобрана: файл не открылся или не является книгой "
        "справки. Индекс не тронут."
    ),
    OutcomeKind.NOTHING_TO_INDEX: (
        "Книга {file_path} разобрана, но документов в ней не нашлось. "
        "Индекс не тронут."
    ),
    OutcomeKind.PAGE_LOSS_TOO_HIGH: (
        "Книга прочитана не полностью: разобрано {parsed} страниц из {attempted} "
        "({share:.0%} потеряно). Это больше допустимого, поэтому индекс не тронут."
    ),
    OutcomeKind.INDEX_WRITE_FAILED: (
        "Elasticsearch отказал в записи индекса {index}. Разбор книги прошёл, "
        "запись — нет."
    ),
    OutcomeKind.ERROR: "Индексация прервана ошибкой: {error}",
}

_WITHOUT_DETAILS = {
    OutcomeKind.INDEXED: "Индексация завершена.",
    OutcomeKind.PARSE_FAILED: "Книга не разобрана.",
    OutcomeKind.NOTHING_TO_INDEX: "В книге не нашлось документов.",
    OutcomeKind.PAGE_LOSS_TOO_HIGH: "Книга потеряла при разборе слишком много страниц.",
    OutcomeKind.INDEX_WRITE_FAILED: "Elasticsearch отказал в записи индекса.",
    OutcomeKind.ERROR: "Индексация прервана ошибкой.",
}


def describe_outcome(outcome: IndexingOutcome) -> str:
    """Одна строка для оператора: что случилось и что стало с индексом."""
    try:
        return _MESSAGES[outcome.kind].format(**outcome.details)
    except KeyError:
        return _WITHOUT_DETAILS[outcome.kind]
