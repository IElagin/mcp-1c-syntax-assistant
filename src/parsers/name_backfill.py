"""Достройка английских имён по английскому индексу.

У части страниц объектов английского имени или объекта-владельца в русской
книге нет вовсе — «Глобальный контекст», расширения форм, заглушки вида
«<Имя измерения>» и подобные. На момент задачи 13 это 707 документов: 674 с
пустым name_en, 304 без object_en (271 из них — оба сразу). Плановая цифра
брифа (158) устарела: индекс менялся трижды с задачи 11.

Их значения берутся из английской книги по пути страницы (source_file):
внутренние пути совпадают в обеих книгах символ в символ — это измерено на
всём корпусе (48 682 файла, списки путей идентичны построчно) и служит ключом
склейки. Склейка идёт по индексам, а не по архивам: source_file уже
проиндексирован в обеих книгах, и второй разбор 32-мегабайтной книги ради
нескольких сотен страниц не нужен.

Достройка правит СТРОГО те поля, которых не хватает конкретному документу, и
никогда не трогает уже заполненные: у 33 из 707 документов name_en уже
разобран задачей 11 и лексически отличается от заголовка английской книги
(«Массив (Array)» в русской книге против «Array» в английской, у составных
имён форм расхождение сильнее) — переписать его значением из английского
индекса значило бы молча отменить разбор задачи 11.
"""

from typing import Dict, List

from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger

logger = get_logger(__name__)

# С запасом на порядок: реальных кандидатов 707 на момент задачи 13, но
# константа не должна зависеть от текущего состояния книги — index.max_result
# _window по умолчанию 10 000, и обе книги исторически только росли.
MAX_CANDIDATES = 5000

# terms-запрос по source_file чанкуется, а не уходит одним списком: список
# кандидатов может вырасти, а элементы terms не обязаны укладываться в один
# запрос без разумного предела.
LOOKUP_CHUNK = 500


async def _candidates(es_client: ElasticsearchClient, index: str) -> List[Dict]:
    """Документы, которым не хватает name_en или object_en.

    Это два разных случая по форме хранения, не один. Индексатор
    (src/parsers/indexer.py) пишет name_en пустой строкой при неудачном
    расщеплении заголовка — поле всегда присутствует, must_not/exists его не
    поймает, только term по пустой строке. object_en, наоборот, в документ
    просто не попадает, когда у страницы нет объекта-владельца, — здесь
    работает exists. Проверяем оба случая одним bool-запросом.
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
        # size обрезал выдачу — часть кандидатов в этом прогоне не будет
        # даже рассмотрена, не то что достроена. Молчать нельзя: со стороны
        # это неотличимо от «всё достроено, кандидатов больше нет».
        logger.warning(
            f"Кандидатов на достройку {total}, выбрано {len(hits)} "
            f"(предел MAX_CANDIDATES={MAX_CANDIDATES}) — часть не будет "
            f"рассмотрена в этом прогоне"
        )
    return hits


async def _english_by_source_file(
    es_client: ElasticsearchClient, index: str, source_files: List[str]
) -> Dict[str, Dict]:
    """Английские страницы, сматченные по source_file.

    source_file в обеих книгах — поле типа keyword целиком (без под-поля
    .keyword — в отличие от name_en). terms по source_file.keyword у
    несуществующего под-поля не падает с ошибкой, а молча не находит ничего:
    достройка выглядела бы работающей и не обновляла бы ни одного документа.
    """
    result: Dict[str, Dict] = {}
    for start in range(0, len(source_files), LOOKUP_CHUNK):
        chunk = source_files[start : start + LOOKUP_CHUNK]
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
                result[source_file] = hit["_source"]
    return result


def _fields_to_fill(ru_source: Dict, en_source: Dict) -> Dict[str, str]:
    """Какие из name_en/object_en реально можно дописать документу.

    Только недостающие поля, и только когда английская книга сама даёт
    непустое значение. Оба условия обязательны:

    - непустое name_en/object_en в ru_source остаётся как есть — иначе
      достройка отменяла бы разбор задачи 11 (см. докстринг модуля);
    - пустое или отсутствующее значение на английской стороне не пишется —
      иначе пустая заглушка страницы заменила бы «поля нет» на «поле есть,
      но пустое», и документ всё ещё числился бы кандидатом на следующем
      прогоне, но обновлять было бы уже нечего: идемпотентность держится на
      «нечего менять», а не на «поле дописано», и это ожидаемо — прогон
      просто находит те же 21-22 нерешаемых страницы заново, без записи.
    """
    fields: Dict[str, str] = {}

    if not ru_source.get("name_en"):
        name = en_source.get("name")
        if name:
            fields["name_en"] = name

    if ru_source.get("object_en") is None:
        obj = en_source.get("object")
        if obj:
            fields["object_en"] = obj

    return fields


async def backfill_english_names(
    es_client: ElasticsearchClient, ru_index: str, en_index: str
) -> int:
    """Достраивает name_en/object_en в ru_index из en_index по source_file.

    Возвращает число документов, у которых реально изменилось хотя бы одно
    поле — не число найденных кандидатов. Кандидат может остаться кандидатом
    и после успешного прогона: если английская книга сама не даёт значения
    (пустая заглушка) или страница не нашлась в английском индексе вовсе,
    обновлять нечего, и это не ошибка (см. докстринг модуля).
    """
    if not await es_client.index_exists(index=en_index):
        logger.info(f"Индекса {en_index} нет — достройка имён пропущена")
        return 0

    candidates = await _candidates(es_client, ru_index)
    if not candidates:
        return 0

    ru_by_id: Dict[str, Dict] = {}
    source_file_of: Dict[str, str] = {}
    for hit in candidates:
        source_file = hit["_source"].get("source_file")
        if not source_file:
            continue
        ru_by_id[hit["_id"]] = hit["_source"]
        source_file_of[hit["_id"]] = source_file

    if not source_file_of:
        return 0

    english = await _english_by_source_file(
        es_client, en_index, sorted(set(source_file_of.values()))
    )
    if not english:
        return 0

    operations = []
    doc_ids_in_order: List[str] = []
    for doc_id, source_file in source_file_of.items():
        en_source = english.get(source_file)
        if not en_source:
            continue

        fields = _fields_to_fill(ru_by_id[doc_id], en_source)
        if not fields:
            continue

        operations.append({"update": {"_index": ru_index, "_id": doc_id}})
        operations.append({"doc": fields})
        doc_ids_in_order.append(doc_id)

    if not operations:
        return 0

    response = await es_client._client.bulk(body=operations)

    # Число обновлённых считается по фактическому результату bulk, а не по
    # числу подготовленных операций: при частичном отказе ES часть doc_id не
    # запишется, и вернуть «успех» для них значило бы соврать вызывающему,
    # который по этому числу решает, надо ли что-то ещё делать. Документы,
    # чей update не прошёл, останутся кандидатами и будут подобраны заново
    # следующим прогоном — это самолечение, не баг.
    updated = 0
    items = response.get("items", [])
    for doc_id, item in zip(doc_ids_in_order, items):
        error = item.get("update", {}).get("error")
        if error:
            logger.error(f"Ошибка достройки документа {doc_id}: {error}")
            continue
        updated += 1

    if updated:
        await es_client.refresh_index(index=ru_index)
        logger.info(f"Достроено английских имён: {updated}")

    return updated
