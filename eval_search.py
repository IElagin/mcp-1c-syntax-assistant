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
    """Частотные вызовы из реальной конфигурации 1С — хоть что-то находится?"""
    itogi = Counter()
    pustye = []
    for imya in COMMON_1C_CALLS:
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


async def vzyat_vse_dokumenty(polya):
    """Выгружает весь индекс постранично через search_after."""
    docs, posle = [], None
    while True:
        zapros = {
            "size": 1000,
            "query": {"match_all": {}},
            "_source": polya,
            "sort": [{"id": "asc"}],
        }
        if posle:
            zapros["search_after"] = posle
        otvet = await es_client.search(zapros)
        hits = (otvet or {}).get("hits", {}).get("hits", [])
        if not hits:
            return docs
        docs.extend(h["_source"] for h in hits)
        posle = hits[-1]["sort"]


def _pohozhe_na_tip(znachenie):
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
    tekst = (znachenie or "").strip()
    if not tekst:
        return False
    elementy = [e.strip() for e in tekst.rstrip(".").split(",")]
    return all(e and " " not in e for e in elementy)


def _varianty(doc):
    """Варианты вызова; у старой модели их нет, тогда — пустой список."""
    return doc.get("variants") or []


def _parametry(doc):
    """Параметры из вариантов, а у старой модели — с верхнего уровня."""
    iz_variantov = [p for v in _varianty(doc) for p in (v.get("parameters") or [])]
    return iz_variantov or (doc.get("parameters") or [])


def _uchest_vozvrat(itogi, return_type):
    """Классифицирует один непустой return_type и прибавляет в itogi.

    Общая точка для обеих моделей (тип внутри варианта и тип на верхнем
    уровне старой модели), чтобы правило классификации не разъезжалось
    между двумя копипастами при будущих правках.
    """
    if not return_type:
        return
    if _pohozhe_na_tip(return_type):
        itogi["vozvrat_tip"] += 1
    else:
        itogi["vozvrat_abzats"] += 1


def zamer_polnoty(docs):
    """Считает, чего в карточке не хватает и что в ней искажено."""
    itogi = Counter()
    for d in docs:
        tip = d.get("type") or ""
        itogi["vsego"] += 1

        if d.get("availability"):
            itogi["s_dostupnostyu"] += 1

        if tip == "object_property":
            itogi["svoystv"] += 1
            if d.get("value_type"):
                itogi["svoystv_s_tipom"] += 1
            if d.get("usage"):
                itogi["svoystv_s_dostupom"] += 1

        for p in _parametry(d):
            itogi["param_vsego"] += 1
            opisanie = (p.get("description") or "").lstrip()
            # Метка обязательности относится к самому параметру, только если
            # стоит префиксом его описания. Та же метка встречается и внутри
            # описания — 1С так помечает обязательность вложенных ключей
            # структуры-аргумента ('...ВыборГруппИЭлементов (необязательный) -
            # тип...'), и это не характеризует параметр, к которому она
            # приклеена вхождением где угодно.
            neobyazatelnyy_prefiks = opisanie.startswith("(необязательный)")
            obyazatelnyy_prefiks = opisanie.startswith("(обязательный)")
            if p.get("required") is True and neobyazatelnyy_prefiks:
                itogi["param_protivorechie"] += 1
            if not p.get("type"):
                itogi["param_bez_tipa"] += 1
            if obyazatelnyy_prefiks or neobyazatelnyy_prefiks:
                itogi["param_dubl_v_opisanii"] += 1
            # Отдельно от противоречия: после чистки описаний противоречие
            # исчезнет само, а вот известна ли обязательность — вопрос
            # положительный, и его надо мерить прямо.
            if p.get("required") is None:
                itogi["param_bez_obyazatelnosti"] += 1

        for v in _varianty(d):
            _uchest_vozvrat(itogi, v.get("return_type"))

        # Старая модель: тип возврата лежал на верхнем уровне
        if not _varianty(d):
            _uchest_vozvrat(itogi, d.get("return_type"))

        if len(_varianty(d)) > 1:
            itogi["mnogo_variantov"] += 1

    return itogi


def neunikalnye_imena(docs):
    """Имена, встречающиеся больше одного раза, и сколько раз."""
    schetchik = Counter(d.get("name_ru") for d in docs if d.get("name_ru"))
    return {imya: n for imya, n in schetchik.items() if n > 1}


async def zamer_odnoznachnosti(service, docs, razmer=40, seed=20260730):
    """Сообщает ли сервер о неоднозначности вместо молчаливого выбора.

    Берём имена-омонимы и просим карточку без указания объекта. Правильный
    ответ — не карточка, а перечень кандидатов: выбрать за агента один из
    275 одноимённых элементов сервер не вправе.
    """
    omonimy = sorted(neunikalnye_imena(docs).items(), key=lambda p: -p[1])
    vyborka = [imya for imya, _ in omonimy[:200]]
    random.Random(seed).shuffle(vyborka)
    vyborka = vyborka[:razmer]

    itogi = Counter()
    for imya in vyborka:
        itogi["vsego"] += 1
        otvet = await service.kartochka_elementa(imya)
        vid = (otvet or {}).get("kind")
        if vid == "ambiguous":
            itogi["soobshchil"] += 1
        elif vid == "card":
            itogi["molcha_vybral"] += 1
        else:
            itogi["ne_nashel"] += 1
    return itogi


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
        print("\n== D. Частотные вызовы из реальной конфигурации 1С ==")
        print(f"  хоть что-то нашлось : {protsent(chastotnye['nashlos'], chastotnye['vsego'])}  ({chastotnye['nashlos']}/{chastotnye['vsego']})")
        print(f"  точное имя в топ-5  : {protsent(chastotnye['tochnoe_v5'], chastotnye['vsego'])}  ({chastotnye['tochnoe_v5']}/{chastotnye['vsego']})")
        if pustye:
            print(f"  пусто по запросам   : {', '.join(pustye)}")

        vse = await vzyat_vse_dokumenty([
            "type", "object", "name_ru", "parameters", "variants", "return_type",
            "availability", "usage", "value_type", "examples",
        ])
        polnota = zamer_polnoty(vse)
        v = polnota["vsego"]
        print("\n== E. Полнота карточки ==")
        print(f"  с доступностью      : {protsent(polnota['s_dostupnostyu'], v)}  ({polnota['s_dostupnostyu']}/{v})")
        print(f"  свойств с типом     : {protsent(polnota['svoystv_s_tipom'], polnota['svoystv'])}  ({polnota['svoystv_s_tipom']}/{polnota['svoystv']})")
        print(f"  свойств с доступом  : {protsent(polnota['svoystv_s_dostupom'], polnota['svoystv'])}  ({polnota['svoystv_s_dostupom']}/{polnota['svoystv']})")
        print(f"  параметров всего    : {polnota['param_vsego']}")
        print(f"    противоречий      : {polnota['param_protivorechie']}")
        print(f"    без типа          : {polnota['param_bez_tipa']}")
        print(f"    дубль в описании  : {polnota['param_dubl_v_opisanii']}")
        print(f"    обязательность неизвестна: {polnota['param_bez_obyazatelnosti']}")
        print(f"  возврат: тип        : {polnota['vozvrat_tip']}")
        print(f"  возврат: абзац      : {polnota['vozvrat_abzats']}")
        print(f"  элементов с >1 вариантом вызова: {polnota['mnogo_variantov']}")

        try:
            odnozn = await zamer_odnoznachnosti(service, vse)
            print("\n== F. Однозначность ==")
            print(f"  сообщил о выборе    : {protsent(odnozn['soobshchil'], odnozn['vsego'])}  ({odnozn['soobshchil']}/{odnozn['vsego']})")
            print(f"  выбрал молча        : {protsent(odnozn['molcha_vybral'], odnozn['vsego'])}  ({odnozn['molcha_vybral']}/{odnozn['vsego']})")
        except AttributeError:
            print("\n== F. Однозначность == (kartochka_elementa ещё не реализована)")

        if promahi:
            print("\n== Примеры промахов набора A ==")
            for d in promahi[:12]:
                print(f"  {d['object']}.{d['ru']}")
        return 0
    finally:
        await es_client.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
