"""Достройка name_en/object_en в русском индексе из английского.

Ключ склейки — путь страницы. Правятся строго недостающие поля; уже
заполненные не трогаются.
"""

import re
from typing import Dict, List, Optional, Tuple

from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger

logger = get_logger(__name__)

# «catalog2627», «object464», «method6189» — имена, которые придумывает
# генератор книги, а не автор справки.
_BOOK_IDENTIFIER_RE = re.compile(
    r"(?:catalog|object|method|prop|property|event|ctor|func|page)\d+\Z",
    re.IGNORECASE,
)

MAX_CANDIDATES = 5000
LOOKUP_CHUNK = 500


def _both_separators(source_file: str) -> Tuple[str, str]:
    """Путь страницы в обоих написаниях: индекс мог быть построен до перехода на zipfile."""
    forward = (source_file or "").replace("\\", "/")
    return forward, forward.replace("/", "\\")


async def _candidates(es_client: ElasticsearchClient, index: str) -> List[Dict]:
    """Документы, которым не хватает name_en или object_en.

    Формы хранения разные: пустое name_en ловится term'ом по пустой строке
    (поле присутствует всегда), отсутствующее object_en — через exists.
    """
    response = await es_client.search(
        {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"name_en.keyword": ""}},
                        {"bool": {"must_not": [{"exists": {"field": "object_en"}}]}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "_source": ["source_file", "name_en", "object_en"],
            "size": MAX_CANDIDATES,
        },
        index=index,
    )
    hits = response.get("hits", {}).get("hits", [])
    total = response.get("hits", {}).get("total", {}).get("value", len(hits))
    if total > len(hits):
        logger.warning(
            f"Кандидатов на достройку {total}, выбрано {len(hits)} "
            f"(предел MAX_CANDIDATES={MAX_CANDIDATES}) — часть не будет "
            f"рассмотрена в этом прогоне"
        )
    return hits


async def _english_by_source_file(
    es_client: ElasticsearchClient, index: str, source_files: List[str]
) -> Dict[str, Dict]:
    """Английские страницы по пути, ключ словаря — канонический путь.

    В terms уходят обе записи каждого пути: индексы могли быть собраны на
    разных платформах, а разделитель приходит из вывода 7zip.
    """
    lookup = sorted({
        variant
        for source_file in source_files
        for variant in _both_separators(source_file)
    })

    found: Dict[str, Dict] = {}
    for start in range(0, len(lookup), LOOKUP_CHUNK):
        chunk = lookup[start:start + LOOKUP_CHUNK]
        response = await es_client.search(
            {
                "query": {"terms": {"source_file": chunk}},
                "_source": ["source_file", "name", "object"],
                "size": len(chunk),
            },
            index=index,
        )
        for hit in response.get("hits", {}).get("hits", []):
            source_file = hit["_source"].get("source_file")
            if source_file:
                found[source_file.replace("\\", "/")] = hit["_source"]
    return found


def _page_stem(source_file: Optional[str]) -> str:
    """«objects/catalog2/catalog2627.html» → «catalog2627»."""
    name = (source_file or "").rsplit("/", 1)[-1]
    return name[:-5] if name.endswith(".html") else name


def _is_page_identifier(value: Optional[str], source_file: Optional[str]) -> bool:
    """Значение — имя файла страницы, а не имя элемента справки.

    Проверяются оба признака сразу: одной формы служебного идентификатора мало,
    одного совпадения с именем файла — тоже («Array.html» → «Array» честно
    назван по элементу).
    """
    text = (value or "").strip()
    if not text:
        return False
    return bool(_BOOK_IDENTIFIER_RE.match(text)) and text == _page_stem(source_file)


def _fields_to_fill(ru_source: Dict, en_source: Dict) -> Dict[str, str]:
    """Какие из name_en/object_en можно дописать документу.

    Только недостающие поля, только с непустым значением на английской стороне
    и только если это значение не служебное имя страницы книги.
    """
    source_file = en_source.get("source_file")
    fields: Dict[str, str] = {}

    if not ru_source.get("name_en"):
        name = en_source.get("name")
        if name and not _is_page_identifier(name, source_file):
            fields["name_en"] = name

    if ru_source.get("object_en") is None:
        obj = en_source.get("object")
        if obj and not _is_page_identifier(obj, source_file):
            fields["object_en"] = obj

    return fields


async def backfill_english_names(
    es_client: ElasticsearchClient, ru_index: str, en_index: str
) -> int:
    """Достраивает name_en/object_en в ru_index из en_index.

    Возвращает число документов, у которых реально изменилось хотя бы одно
    поле, — не число найденных кандидатов. Кандидат остаётся кандидатом, когда
    английская книга сама не даёт значения; это не ошибка.
    """
    if not await es_client.index_exists(index=en_index):
        logger.info(f"Индекса {en_index} нет — достройка имён пропущена")
        return 0

    candidates = await _candidates(es_client, ru_index)
    russian = {
        hit["_id"]: hit["_source"]
        for hit in candidates
        if hit["_source"].get("source_file")
    }
    if not russian:
        return 0

    english = await _english_by_source_file(
        es_client, en_index,
        sorted({doc["source_file"] for doc in russian.values()}),
    )
    if not english:
        return 0

    updates = _plan_updates(russian, english, ru_index)
    if not updates:
        return 0

    doc_ids, operations = updates
    response = await es_client._client.bulk(body=operations)
    updated = _count_written(doc_ids, response.get("items", []))

    if updated:
        await es_client.refresh_index(index=ru_index)
        logger.info(f"Достроено английских имён: {updated}")
    return updated


def _plan_updates(
    russian: Dict[str, Dict], english: Dict[str, Dict], ru_index: str
) -> Optional[Tuple[List[str], List[Dict]]]:
    doc_ids: List[str] = []
    operations: List[Dict] = []

    for doc_id, ru_source in russian.items():
        en_source = english.get(ru_source["source_file"].replace("\\", "/"))
        if not en_source:
            continue

        fields = _fields_to_fill(ru_source, en_source)
        if not fields:
            continue

        operations.append({"update": {"_index": ru_index, "_id": doc_id}})
        operations.append({"doc": fields})
        doc_ids.append(doc_id)

    return (doc_ids, operations) if operations else None


def _count_written(doc_ids: List[str], items: List[Dict]) -> int:
    """Сколько операций bulk действительно записались.

    Считаем по результату, а не по числу подготовленных операций: при
    частичном отказе Elasticsearch вернуть «успех» значило бы соврать
    вызывающему. Незаписанные документы останутся кандидатами и будут
    подобраны следующим прогоном.
    """
    written = 0
    for doc_id, item in zip(doc_ids, items):
        error = item.get("update", {}).get("error")
        if error:
            logger.error(f"Ошибка достройки документа {doc_id}: {error}")
            continue
        written += 1
    return written
