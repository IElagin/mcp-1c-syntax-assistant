"""Замер качества поиска по справке 1С.

Не тест, а измерительный инструмент: гоняет наборы запросов через тот же
SearchService, что стоит за MCP-инструментами, и считает попадания.

Эталон берётся из самого индекса: у документа известны object и name, значит
известен и правильный ответ на запрос по этому имени.

Запуск:  docker compose exec -T mcp-server python eval_search.py
"""

import asyncio
import random
import re
import sys
from collections import Counter

from src.core.elasticsearch import es_client
from src.search.search_service import SearchService

# name в индексе хранится как "Добавить (Add)" — русское и английское имя слитно
NAME_RU_EN_RE = re.compile(r"^(.+?)\s+\(([A-Za-z][A-Za-z0-9.]*)\)$")

# Частотные вызовы из реальной конфигурации 1С: список собран поиском по *.bsl
# рабочей базы и отсортирован по убыванию числа вхождений. Замер на нём ближе к
# практике, чем равномерная выборка по индексу.
COMMON_1C_CALLS = [
    "Добавить", "Вставить", "УстановитьПараметр", "Выполнить", "Количество",
    "Выбрать", "Следующий", "Записать", "Найти", "Свойство", "Выгрузить",
    "Получить", "НайтиПоКоду", "Очистить", "Сообщить", "ПолучитьОбъект",
    "НайтиСтроки", "ВыгрузитьКолонку", "УникальныйИдентификатор", "Удалить",
    "ЗаписатьКонецЭлемента", "Прочитать", "СрезПоследних", "Содержит",
    "Закрыть", "Метаданные", "СоздатьНаборЗаписей", "УстановитьСтроку",
    "Свернуть", "СоздатьМенеджерЗаписи", "ПолучитьМакет", "Присоединить",
]


def split_name(name):
    """Возвращает (русское, английское) из 'Добавить (Add)'."""
    m = NAME_RU_EN_RE.match(name or "")
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return (name or "").strip(), None


async def take_reference(size=150, seed=20260728):
    """Случайная выборка документов объектов — эталон для замера."""
    response = await es_client.search({
        "size": 4000,
        "query": {"bool": {"filter": [
            {"terms": {"type": ["object_function", "object_procedure",
                                "object_property", "object_method"]}}
        ]}},
        "_source": ["name", "object", "type", "full_path"],
    })
    hits = (response or {}).get("hits", {}).get("hits", [])
    docs = []
    for h in hits:
        s = h["_source"]
        ru_name, en_name = split_name(s.get("name"))
        if s.get("object") and ru_name:
            docs.append({"ru_name": ru_name, "en_name": en_name,
                         "object": s["object"]})
    random.Random(seed).shuffle(docs)
    return docs[:size]


def hit_rank(results, ru_name, obj):
    """Позиция нужного документа (1-based) или None."""
    for i, r in enumerate(results, 1):
        r_ru_name, _ = split_name(r.get("name"))
        if r_ru_name == ru_name and r.get("object") == obj:
            return i
    return None


async def measure_against_reference(service, reference, limit=10):
    """Ищем по имени и смотрим, на каком месте правильный документ."""
    totals = Counter()
    misses = []

    for d in reference:
        # Запрос ровно так, как его задаёт разработчик: голое имя метода
        res = await service.find_help_by_query(d["ru_name"], limit=limit)
        results = res.get("results", []) if not res.get("error") else []

        rank = hit_rank(results, d["ru_name"], d["object"])
        if rank == 1:
            totals["rank1"] += 1
        if rank and rank <= 5:
            totals["rank5"] += 1
        if rank:
            totals["rank10"] += 1
        else:
            totals["miss"] += 1
            if not results:
                totals["empty"] += 1
            misses.append(d)
        totals["total"] += 1

    return totals, misses


async def measure_english_names(service, reference, limit=10):
    """Поиск по английскому имени — ValueIsFilled вместо ЗначениеЗаполнено."""
    totals = Counter()
    for d in reference:
        if not d["en_name"]:
            continue
        res = await service.find_help_by_query(d["en_name"], limit=limit)
        results = res.get("results", []) if not res.get("error") else []
        rank = hit_rank(results, d["ru_name"], d["object"])
        totals["total"] += 1
        if rank and rank <= 5:
            totals["rank5"] += 1
        if not results:
            totals["empty"] += 1
    return totals


def is_real_type(obj):
    """Похоже ли имя объекта на тип встроенного языка, а не на раздел справки.

    В справке под object лежат и настоящие типы (ТаблицаЗначений), и заголовки
    разделов вроде 'Расширение поля формы для поля флажка' или
    'ОбъектМетаданных: Измерение'. Последние в коде не пишут, и мерить качество
    поиска по ним — вводить себя в заблуждение.
    """
    return obj and " " not in obj and ":" not in obj


async def measure_dotted_notation(service, reference, limit=10):
    """Запрос вида 'ТаблицаЗначений.Добавить' — как пишут в коде.

    Считаем отдельно по настоящим типам: только их и пишут в коде точкой.
    """
    totals = Counter()
    for d in reference:
        res = await service.find_help_by_query(
            f"{d['object']}.{d['ru_name']}", limit=limit
        )
        results = res.get("results", []) if not res.get("error") else []
        rank = hit_rank(results, d["ru_name"], d["object"])
        is_real = is_real_type(d["object"])

        totals["total"] += 1
        if is_real:
            totals["total_real"] += 1
        if rank and rank <= 5:
            totals["rank5"] += 1
            if is_real:
                totals["rank5_real"] += 1
        if not results:
            totals["empty"] += 1
    return totals


async def measure_exact_name(service, reference, limit=10):
    """Побеждает ли точное совпадение имени частичное.

    Метрика A измеряет попадание конкретной пары объект+имя и потому упирается
    в омонимию: 'Количество' есть у сотни объектов, и ждать там конкретный
    ЭлементыZipФайла.Количество бессмысленно. Здесь вопрос иной и проверяемый:
    стоит ли на первом месте элемент ровно с запрошенным именем, чей угодно.
    """
    totals = Counter()
    for d in reference:
        res = await service.find_help_by_query(d["ru_name"], limit=limit)
        results = res.get("results", []) if not res.get("error") else []
        totals["total"] += 1
        if not results:
            continue
        if split_name(results[0].get("name"))[0] == d["ru_name"]:
            totals["exact_first"] += 1
        if any(split_name(r.get("name"))[0] == d["ru_name"] for r in results[:5]):
            totals["exact_in5"] += 1
    return totals


async def measure_common_calls(service, limit=10):
    """Частотные вызовы из реальной конфигурации 1С — хоть что-то находится?"""
    totals = Counter()
    empty_queries = []
    for name in COMMON_1C_CALLS:
        res = await service.find_help_by_query(name, limit=limit)
        results = res.get("results", []) if not res.get("error") else []
        totals["total"] += 1
        if results:
            totals["found"] += 1
            # точное совпадение имени в первой пятёрке
            if any(split_name(r.get("name"))[0] == name for r in results[:5]):
                totals["exact_in5"] += 1
        else:
            empty_queries.append(name)
    return totals, empty_queries


async def take_all_documents(fields):
    """Выгружает весь индекс постранично через search_after."""
    docs, after = [], None
    while True:
        query = {
            "size": 1000,
            "query": {"match_all": {}},
            "_source": fields,
            "sort": [{"id": "asc"}],
        }
        if after:
            query["search_after"] = after
        response = await es_client.search(query)
        hits = (response or {}).get("hits", {}).get("hits", [])
        if not hits:
            return docs
        docs.extend(h["_source"] for h in hits)
        after = hits[-1]["sort"]


def _looks_like_type(value):
    """Тип — перечисление типов через запятую, не абзац пояснения.

    Длину не мерим: настоящие имена типов 1С сами по себе бывают длиннее
    сорока символов ('ПериодРазделенияХраненияДанныхЖурналаРегистрации' — 48),
    а перечисление возможных типов возврата («Тип: Строка, Число.») по спеке
    §4.2 сохраняется целиком, сколько бы типов в нём ни было — выбирать один
    сервер не вправе. Абзац отличают не длина и не точка, а слова с пробелами
    внутри: каждый элемент перечисления типов — одно слово ('Булево',
    'ТабличныйДокумент'), а во фразе вроде 'другой объект, который может быть
    макетом' у элементов внутри пробелы.
    """
    text = (value or "").strip()
    if not text:
        return False
    elements = [e.strip() for e in text.rstrip(".").split(",")]
    return all(e and " " not in e for e in elements)


def _variant_list(doc):
    """Варианты вызова; у старой модели их нет, тогда — пустой список."""
    return doc.get("variants") or []


def _params(doc):
    """Параметры из вариантов, а у старой модели — с верхнего уровня."""
    from_variants = [p for v in _variant_list(doc) for p in (v.get("parameters") or [])]
    return from_variants or (doc.get("parameters") or [])


def _count_return_value(totals, return_type):
    """Классифицирует один непустой return_type и прибавляет в totals.

    Общая точка для обеих моделей (тип внутри варианта и тип на верхнем
    уровне старой модели), чтобы правило классификации не разъезжалось
    между двумя копипастами при будущих правках.
    """
    if not return_type:
        return
    if _looks_like_type(return_type):
        totals["return_as_type"] += 1
    else:
        totals["return_as_paragraph"] += 1


def measure_completeness(docs):
    """Считает, чего в карточке не хватает и что в ней искажено."""
    totals = Counter()
    for d in docs:
        type_name = d.get("type") or ""
        totals["total"] += 1

        if d.get("availability"):
            totals["with_availability"] += 1

        if type_name == "object_property":
            totals["properties"] += 1
            if d.get("value_type"):
                totals["properties_with_type"] += 1
            if d.get("usage"):
                totals["properties_with_usage"] += 1

        for p in _params(d):
            totals["param_total"] += 1
            description = (p.get("description") or "").lstrip()
            # Метка обязательности относится к самому параметру, только если
            # стоит префиксом его описания. Та же метка встречается и внутри
            # описания — 1С так помечает обязательность вложенных ключей
            # структуры-аргумента ('...ВыборГруппИЭлементов (необязательный) -
            # тип...'), и это не характеризует параметр, к которому она
            # приклеена вхождением где угодно.
            optional_prefix = description.startswith("(необязательный)")
            required_prefix = description.startswith("(обязательный)")
            if p.get("required") is True and optional_prefix:
                totals["param_contradiction"] += 1
            if not p.get("type"):
                totals["param_without_type"] += 1
            if required_prefix or optional_prefix:
                totals["param_duplicated_in_description"] += 1
            # Отдельно от противоречия: после чистки описаний противоречие
            # исчезнет само, а вот известна ли обязательность — вопрос
            # положительный, и его надо мерить прямо.
            if p.get("required") is None:
                totals["param_without_required"] += 1

        for v in _variant_list(d):
            _count_return_value(totals, v.get("return_type"))

        # Старая модель: тип возврата лежал на верхнем уровне
        if not _variant_list(d):
            _count_return_value(totals, d.get("return_type"))

        if len(_variant_list(d)) > 1:
            totals["many_variants"] += 1

    return totals


def ambiguous_names(docs):
    """Имена, встречающиеся больше одного раза, и сколько раз."""
    counter = Counter(d.get("name_ru") for d in docs if d.get("name_ru"))
    return {name: n for name, n in counter.items() if n > 1}


async def measure_disambiguation(service, docs, size=40, seed=20260730):
    """Сообщает ли сервер о неоднозначности вместо молчаливого выбора.

    Берём имена-омонимы и просим карточку без указания объекта. Правильный
    ответ — не карточка, а перечень кандидатов: выбрать за агента один из
    275 одноимённых элементов сервер не вправе.
    """
    homonyms = sorted(ambiguous_names(docs).items(), key=lambda p: -p[1])
    sample = [name for name, _ in homonyms[:200]]
    random.Random(seed).shuffle(sample)
    sample = sample[:size]

    totals = Counter()
    for name in sample:
        totals["total"] += 1
        response = await service.element_card(name)
        kind = (response or {}).get("kind")
        if kind == "ambiguous":
            totals["reported"] += 1
        elif kind == "card":
            totals["chose_silently"] += 1
        else:
            totals["not_found"] += 1
    return totals


def percent(part, total):
    return f"{100.0 * part / total:5.1f}%" if total else "    н/д"


async def main():
    if not await es_client.connect():
        print("Elasticsearch недоступен")
        return 1
    try:
        service = SearchService(es_client)
        reference = await take_reference()
        print(f"Эталон: {len(reference)} элементов объектов из индекса\n")

        totals, misses = await measure_against_reference(service, reference)
        v = totals["total"]
        print("== A. Поиск по русскому имени (голое имя метода) ==")
        print(f"  найден на 1-м месте : {percent(totals['rank1'], v)}  ({totals['rank1']}/{v})")
        print(f"  найден в топ-5      : {percent(totals['rank5'], v)}  ({totals['rank5']}/{v})")
        print(f"  найден в топ-10     : {percent(totals['rank10'], v)}  ({totals['rank10']}/{v})")
        print(f"  НЕ найден вовсе     : {percent(totals['miss'], v)}  ({totals['miss']}/{v})")
        print(f"  из них пустой ответ : {totals['empty']}")

        english = await measure_english_names(service, reference)
        print("\n== B. Поиск по английскому имени ==")
        print(f"  найден в топ-5      : {percent(english['rank5'], english['total'])}  ({english['rank5']}/{english['total']})")
        print(f"  пустой ответ        : {percent(english['empty'], english['total'])}  ({english['empty']}/{english['total']})")

        exact = await measure_exact_name(service, reference)
        print("\n== A2. Точное имя побеждает частичное (без учёта объекта) ==")
        print(f"  точное имя первым   : {percent(exact['exact_first'], exact['total'])}  ({exact['exact_first']}/{exact['total']})")
        print(f"  точное имя в топ-5  : {percent(exact['exact_in5'], exact['total'])}  ({exact['exact_in5']}/{exact['total']})")

        dotted = await measure_dotted_notation(service, reference)
        print("\n== C. Точечная запись 'Объект.Метод' ==")
        print(f"  найден в топ-5      : {percent(dotted['rank5'], dotted['total'])}  ({dotted['rank5']}/{dotted['total']})")
        print(f"  пустой ответ        : {percent(dotted['empty'], dotted['total'])}  ({dotted['empty']}/{dotted['total']})")
        print(f"  только по настоящим типам (как пишут в коде):")
        print(f"    найден в топ-5    : {percent(dotted['rank5_real'], dotted['total_real'])}  ({dotted['rank5_real']}/{dotted['total_real']})")

        common_calls, empty_queries = await measure_common_calls(service)
        print("\n== D. Частотные вызовы из реальной конфигурации 1С ==")
        print(f"  хоть что-то нашлось : {percent(common_calls['found'], common_calls['total'])}  ({common_calls['found']}/{common_calls['total']})")
        print(f"  точное имя в топ-5  : {percent(common_calls['exact_in5'], common_calls['total'])}  ({common_calls['exact_in5']}/{common_calls['total']})")
        if empty_queries:
            print(f"  пусто по запросам   : {', '.join(empty_queries)}")

        all_docs = await take_all_documents([
            "type", "object", "name_ru", "parameters", "variants", "return_type",
            "availability", "usage", "value_type", "examples",
        ])
        completeness = measure_completeness(all_docs)
        v = completeness["total"]
        print("\n== E. Полнота карточки ==")
        print(f"  с доступностью      : {percent(completeness['with_availability'], v)}  ({completeness['with_availability']}/{v})")
        print(f"  свойств с типом     : {percent(completeness['properties_with_type'], completeness['properties'])}  ({completeness['properties_with_type']}/{completeness['properties']})")
        print(f"  свойств с доступом  : {percent(completeness['properties_with_usage'], completeness['properties'])}  ({completeness['properties_with_usage']}/{completeness['properties']})")
        print(f"  параметров всего    : {completeness['param_total']}")
        print(f"    противоречий      : {completeness['param_contradiction']}")
        print(f"    без типа          : {completeness['param_without_type']}")
        print(f"    дубль в описании  : {completeness['param_duplicated_in_description']}")
        print(f"    обязательность неизвестна: {completeness['param_without_required']}")
        print(f"  возврат: тип        : {completeness['return_as_type']}")
        print(f"  возврат: абзац      : {completeness['return_as_paragraph']}")
        print(f"  элементов с >1 вариантом вызова: {completeness['many_variants']}")

        try:
            disambig = await measure_disambiguation(service, all_docs)
            print("\n== F. Однозначность ==")
            print(f"  сообщил о выборе    : {percent(disambig['reported'], disambig['total'])}  ({disambig['reported']}/{disambig['total']})")
            print(f"  выбрал молча        : {percent(disambig['chose_silently'], disambig['total'])}  ({disambig['chose_silently']}/{disambig['total']})")
        except AttributeError:
            print("\n== F. Однозначность == (element_card ещё не реализована)")

        if misses:
            print("\n== Примеры промахов набора A ==")
            for d in misses[:12]:
                print(f"  {d['object']}.{d['ru_name']}")
        return 0
    finally:
        await es_client.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
