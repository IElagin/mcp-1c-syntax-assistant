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
IMYA_RU_EN = re.compile(r"^(.+?)\s+\(([A-Za-z][A-Za-z0-9.]*)\)$")

# Реальная частотность вызовов из рабочей конфигурации (rg по *.bsl)
CHASTOTNYE_VYZOVY = [
    "Добавить", "Вставить", "УстановитьПараметр", "Выполнить", "Количество",
    "Выбрать", "Следующий", "Записать", "Найти", "Свойство", "Выгрузить",
    "Получить", "НайтиПоКоду", "Очистить", "Сообщить", "ПолучитьОбъект",
    "НайтиСтроки", "ВыгрузитьКолонку", "УникальныйИдентификатор", "Удалить",
    "ЗаписатьКонецЭлемента", "Прочитать", "СрезПоследних", "Содержит",
    "Закрыть", "Метаданные", "СоздатьНаборЗаписей", "УстановитьСтроку",
    "Свернуть", "СоздатьМенеджерЗаписи", "ПолучитьМакет", "Присоединить",
]


def razobrat_imya(name):
    """Возвращает (русское, английское) из 'Добавить (Add)'."""
    m = IMYA_RU_EN.match(name or "")
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return (name or "").strip(), None


async def vzyat_etalon(razmer=150, seed=20260728):
    """Случайная выборка документов объектов — эталон для замера."""
    otvet = await es_client.search({
        "size": 4000,
        "query": {"bool": {"filter": [
            {"terms": {"type": ["object_function", "object_procedure",
                                "object_property", "object_method"]}}
        ]}},
        "_source": ["name", "object", "type", "full_path"],
    })
    hits = (otvet or {}).get("hits", {}).get("hits", [])
    docs = []
    for h in hits:
        s = h["_source"]
        ru, en = razobrat_imya(s.get("name"))
        if s.get("object") and ru:
            docs.append({"ru": ru, "en": en, "object": s["object"]})
    random.Random(seed).shuffle(docs)
    return docs[:razmer]


def rang_popadaniya(rezultaty, ru, obj):
    """Позиция нужного документа (1-based) или None."""
    for i, r in enumerate(rezultaty, 1):
        r_ru, _ = razobrat_imya(r.get("name"))
        if r_ru == ru and r.get("object") == obj:
            return i
    return None


async def zamer_po_etalonu(service, etalon, limit=10):
    """Ищем по имени и смотрим, на каком месте правильный документ."""
    itogi = Counter()
    promahi = []

    for d in etalon:
        # Запрос ровно так, как его задаёт разработчик: голое имя метода
        res = await service.find_help_by_query(d["ru"], limit=limit)
        rezultaty = res.get("results", []) if not res.get("error") else []

        rang = rang_popadaniya(rezultaty, d["ru"], d["object"])
        if rang == 1:
            itogi["rank1"] += 1
        if rang and rang <= 5:
            itogi["rank5"] += 1
        if rang:
            itogi["rank10"] += 1
        else:
            itogi["promah"] += 1
            if not rezultaty:
                itogi["pusto"] += 1
            promahi.append(d)
        itogi["vsego"] += 1

    return itogi, promahi


async def zamer_angliyskih(service, etalon, limit=10):
    """Поиск по английскому имени — ValueIsFilled вместо ЗначениеЗаполнено."""
    itogi = Counter()
    for d in etalon:
        if not d["en"]:
            continue
        res = await service.find_help_by_query(d["en"], limit=limit)
        rezultaty = res.get("results", []) if not res.get("error") else []
        rang = rang_popadaniya(rezultaty, d["ru"], d["object"])
        itogi["vsego"] += 1
        if rang and rang <= 5:
            itogi["rank5"] += 1
        if not rezultaty:
            itogi["pusto"] += 1
    return itogi


def realnyy_tip(obj):
    """Похоже ли имя объекта на тип встроенного языка, а не на раздел справки.

    В справке под object лежат и настоящие типы (ТаблицаЗначений), и заголовки
    разделов вроде 'Расширение поля формы для поля флажка' или
    'ОбъектМетаданных: Измерение'. Последние в коде не пишут, и мерить качество
    поиска по ним — вводить себя в заблуждение.
    """
    return obj and " " not in obj and ":" not in obj


async def zamer_tochechnoy_zapisi(service, etalon, limit=10):
    """Запрос вида 'ТаблицаЗначений.Добавить' — как пишут в коде.

    Считаем отдельно по настоящим типам: только их и пишут в коде точкой.
    """
    itogi = Counter()
    for d in etalon:
        res = await service.find_help_by_query(f"{d['object']}.{d['ru']}", limit=limit)
        rezultaty = res.get("results", []) if not res.get("error") else []
        rang = rang_popadaniya(rezultaty, d["ru"], d["object"])
        nastoyashchiy = realnyy_tip(d["object"])

        itogi["vsego"] += 1
        if nastoyashchiy:
            itogi["vsego_realnyh"] += 1
        if rang and rang <= 5:
            itogi["rank5"] += 1
            if nastoyashchiy:
                itogi["rank5_realnyh"] += 1
        if not rezultaty:
            itogi["pusto"] += 1
    return itogi


async def zamer_tochnogo_imeni(service, etalon, limit=10):
    """Побеждает ли точное совпадение имени частичное.

    Метрика A измеряет попадание конкретной пары объект+имя и потому упирается
    в омонимию: 'Количество' есть у сотни объектов, и ждать там конкретный
    ЭлементыZipФайла.Количество бессмысленно. Здесь вопрос иной и проверяемый:
    стоит ли на первом месте элемент ровно с запрошенным именем, чей угодно.
    """
    itogi = Counter()
    for d in etalon:
        res = await service.find_help_by_query(d["ru"], limit=limit)
        rezultaty = res.get("results", []) if not res.get("error") else []
        itogi["vsego"] += 1
        if not rezultaty:
            continue
        if razobrat_imya(rezultaty[0].get("name"))[0] == d["ru"]:
            itogi["tochnoe_pervym"] += 1
        if any(razobrat_imya(r.get("name"))[0] == d["ru"] for r in rezultaty[:5]):
            itogi["tochnoe_v5"] += 1
    return itogi


async def zamer_chastotnyh(service, limit=10):
    """Частотные вызовы из реального кода рабочей конфигурации — хоть что-то находится?"""
    itogi = Counter()
    pustye = []
    for imya in CHASTOTNYE_VYZOVY:
        res = await service.find_help_by_query(imya, limit=limit)
        rezultaty = res.get("results", []) if not res.get("error") else []
        itogi["vsego"] += 1
        if rezultaty:
            itogi["nashlos"] += 1
            # точное совпадение имени в первой пятёрке
            if any(razobrat_imya(r.get("name"))[0] == imya for r in rezultaty[:5]):
                itogi["tochnoe_v5"] += 1
        else:
            pustye.append(imya)
    return itogi, pustye


def protsent(chast, vsego):
    return f"{100.0 * chast / vsego:5.1f}%" if vsego else "    н/д"


async def main():
    if not await es_client.connect():
        print("Elasticsearch недоступен")
        return 1
    try:
        service = SearchService(es_client)
        etalon = await vzyat_etalon()
        print(f"Эталон: {len(etalon)} элементов объектов из индекса\n")

        itogi, promahi = await zamer_po_etalonu(service, etalon)
        v = itogi["vsego"]
        print("== A. Поиск по русскому имени (голое имя метода) ==")
        print(f"  найден на 1-м месте : {protsent(itogi['rank1'], v)}  ({itogi['rank1']}/{v})")
        print(f"  найден в топ-5      : {protsent(itogi['rank5'], v)}  ({itogi['rank5']}/{v})")
        print(f"  найден в топ-10     : {protsent(itogi['rank10'], v)}  ({itogi['rank10']}/{v})")
        print(f"  НЕ найден вовсе     : {protsent(itogi['promah'], v)}  ({itogi['promah']}/{v})")
        print(f"  из них пустой ответ : {itogi['pusto']}")

        ang = await zamer_angliyskih(service, etalon)
        print("\n== B. Поиск по английскому имени ==")
        print(f"  найден в топ-5      : {protsent(ang['rank5'], ang['vsego'])}  ({ang['rank5']}/{ang['vsego']})")
        print(f"  пустой ответ        : {protsent(ang['pusto'], ang['vsego'])}  ({ang['pusto']}/{ang['vsego']})")

        tochnoe = await zamer_tochnogo_imeni(service, etalon)
        print("\n== A2. Точное имя побеждает частичное (без учёта объекта) ==")
        print(f"  точное имя первым   : {protsent(tochnoe['tochnoe_pervym'], tochnoe['vsego'])}  ({tochnoe['tochnoe_pervym']}/{tochnoe['vsego']})")
        print(f"  точное имя в топ-5  : {protsent(tochnoe['tochnoe_v5'], tochnoe['vsego'])}  ({tochnoe['tochnoe_v5']}/{tochnoe['vsego']})")

        tochka = await zamer_tochechnoy_zapisi(service, etalon)
        print("\n== C. Точечная запись 'Объект.Метод' ==")
        print(f"  найден в топ-5      : {protsent(tochka['rank5'], tochka['vsego'])}  ({tochka['rank5']}/{tochka['vsego']})")
        print(f"  пустой ответ        : {protsent(tochka['pusto'], tochka['vsego'])}  ({tochka['pusto']}/{tochka['vsego']})")
        print(f"  только по настоящим типам (как пишут в коде):")
        print(f"    найден в топ-5    : {protsent(tochka['rank5_realnyh'], tochka['vsego_realnyh'])}  ({tochka['rank5_realnyh']}/{tochka['vsego_realnyh']})")

        chastotnye, pustye = await zamer_chastotnyh(service)
        print("\n== D. Частотные вызовы из кода рабочей конфигурации ==")
        print(f"  хоть что-то нашлось : {protsent(chastotnye['nashlos'], chastotnye['vsego'])}  ({chastotnye['nashlos']}/{chastotnye['vsego']})")
        print(f"  точное имя в топ-5  : {protsent(chastotnye['tochnoe_v5'], chastotnye['vsego'])}  ({chastotnye['tochnoe_v5']}/{chastotnye['vsego']})")
        if pustye:
            print(f"  пусто по запросам   : {', '.join(pustye)}")

        if promahi:
            print("\n== Примеры промахов набора A ==")
            for d in promahi[:12]:
                print(f"  {d['object']}.{d['ru']}")
        return 0
    finally:
        await es_client.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
