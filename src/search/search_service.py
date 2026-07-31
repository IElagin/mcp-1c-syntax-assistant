"""Основной сервис поиска по документации 1С."""

from typing import List, Dict, Any, Optional
import time

from src.core.elasticsearch import ElasticsearchClient
from src.core.logging import get_logger
from src.search.query_builder import QueryBuilder
from src.search.ranker import SearchRanker
from src.search.formatter import SearchFormatter

logger = get_logger(__name__)

# Сколько кандидатов показать при омонимии. Перечень нужен, чтобы агент выбрал
# объект, а не чтобы прочитать все 275 — полный список он получит запросом.
KANDIDATOV_V_OTVETE = 5

# Сколько совпадений упорядочивать при омонимии. Самое многозначное имя
# справки — «Количество», 275 документов, поэтому 500 покрывает индекс целиком:
# порядок строится по всем совпадениям, а не по произвольному окну. Если
# однажды имя перевалит за потолок, ответ об этом скажет (poryadok_polnyy).
POTOLOK_KANDIDATOV = 500

# Поля, которых хватает строке списка. Карточке нужен документ целиком, а
# перечню кандидатов — нет: тянуть 275 полных документов с параметрами всех
# вариантов ради пяти строк расточительно.
POLYA_STROKI_SPISKA = [
    "type", "element_kind", "name_ru", "object", "object_ru",
    "full_path", "call_primary", "description", "variants.variant",
]

# Настоящие виды членов объекта — в отличие от документа-описания самого
# объекта (type="object"), у которого поле object тоже равно имени объекта.
# Без фильтра по этому списку members="all" ловил и этот документ, выдавая
# объекту без единого метода/свойства/события total=1 вместо 0 — ветка
# "объект есть, но пуст" для all после этого не срабатывала никогда, а у
# обычных объектов (ТаблицаЗначений) счётчик был завышен на единицу.
VIDY_CHLENOV_OBEKTA = [
    "object_function", "object_procedure", "object_constructor",
    "object_property", "object_event",
]


def _nastoyashchiy_tip(imya_obekta) -> bool:
    """Похоже ли имя объекта на тип языка, а не на заголовок раздела справки.

    В справке под object лежат и типы («ТаблицаЗначений»), и разделы вида
    «ОбъектМетаданных: Измерение» — последние в коде не пишут.
    """
    imya = imya_obekta or ""
    return bool(imya) and " " not in imya and ":" not in imya


class SearchService:
    """Сервис поиска по документации 1С."""
    
    def __init__(self, es_client: ElasticsearchClient):
        self.es_client = es_client
        self.query_builder = QueryBuilder()
        self.ranker = SearchRanker()
        self.formatter = SearchFormatter()
    
    async def find_help_by_query(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Универсальный поиск справки по любому элементу 1С."""
        start_time = time.time()
        
        try:
            # Проверяем подключение к Elasticsearch
            if not await self.es_client.is_connected():
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "search_time_ms": 0,
                    "error": "Elasticsearch недоступен"
                }
            
            # Строим запрос
            es_query = self.query_builder.build_search_query(
                query=query,
                limit=limit,
                search_type="auto"
            )

            # Выполняем поиск
            response = await self.es_client.search(es_query)

            # Прежде здесь стоял повторный поиск по одному имени элемента, если
            # объект из запроса «Объект.Метод» не опознан. Он возвращал элементы
            # чужих объектов, не сообщая об этом, — агент принимал их за
            # запрошенные. Теперь пустая выдача остаётся пустой, а объяснение
            # даёт kartochka_elementa через kind="object_not_found".

            if not response:
                return {
                    "results": [],
                    "total": 0,
                    "query": query,
                    "search_time_ms": int((time.time() - start_time) * 1000),
                    "error": "Ошибка выполнения поиска"
                }
            
            # Извлекаем результаты
            hits = response.get("hits", {}).get("hits", [])
            total = response.get("hits", {}).get("total", {})
            total_count = total.get("value", 0) if isinstance(total, dict) else total
            
            # Ранжируем результаты
            ranked_results = self.ranker.rank_results(hits, query)
            
            # Форматируем для вывода
            formatted_results = self.formatter.format_search_results(ranked_results)
            
            search_time = int((time.time() - start_time) * 1000)
            
            logger.info(f"Поиск '{query}' завершен за {search_time}ms. Найдено: {len(formatted_results)}")
            
            return {
                "results": formatted_results,
                "total": total_count,
                "query": query,
                "search_time_ms": search_time
            }
            
        except Exception as e:
            search_time = int((time.time() - start_time) * 1000)
            logger.error(f"Ошибка поиска '{query}': {e}")
            
            return {
                "results": [],
                "total": 0,
                "query": query,
                "search_time_ms": search_time,
                "error": str(e)
            }
    
    async def find_help_by_query_s_filtrom(
        self,
        query: str,
        tipy: list,
        object_name: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Поиск с фильтром по видам элементов и объекту.

        Заменил пару find_help_by_query и search_with_context_filter: две точки
        входа с почти одинаковым смыслом заставляли агента угадывать, какая
        нужна.
        """
        zapros = self.query_builder.build_search_query(query, limit, "auto")

        filtry = []
        if tipy:
            filtry.append({"terms": {"type": tipy}})
        if object_name:
            filtry.append({"term": {"object": object_name}})

        if filtry:
            zapros["query"] = {"bool": {"must": [zapros["query"]], "filter": filtry}}

        otvet = await self.es_client.search(zapros)
        if not otvet:
            return {"results": [], "total": 0, "query": query,
                    "error": "Ошибка выполнения поиска"}

        hits = otvet.get("hits", {}).get("hits", [])
        vsego = otvet.get("hits", {}).get("total", {})
        vsego = vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)

        return {
            "results": self.formatter.format_search_results(
                self.ranker.rank_results(hits, query)
            ),
            "total": vsego,
            "query": query,
        }

    async def kolichestvo_chlenov(self, object_name: str) -> Dict[str, int]:
        """Сколько у объекта методов, свойств и событий.

        Списки methods/properties/events модели Documentation в Elasticsearch не
        переносятся, поэтому считаем документы с этим object.
        """
        gruppy = {
            "methods": ["object_function", "object_procedure", "object_constructor"],
            "properties": ["object_property"],
            "events": ["object_event"],
        }
        itogi = {}
        for nazvanie, tipy in gruppy.items():
            otvet = await self.es_client.search({
                "query": {"bool": {"filter": [
                    {"term": {"object": object_name}},
                    {"terms": {"type": tipy}},
                ]}},
                "size": 0,
            })
            vsego = (otvet or {}).get("hits", {}).get("total", {})
            itogi[nazvanie] = vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)
        return itogi

    async def stroki_konstruktorov(self, object_name: str) -> List[str]:
        """Строки вызова конструкторов объекта — «Новый ТаблицаЗначений».

        В документе самого объекта конструкторов нет: у справки конструктор —
        отдельная страница (type="object_constructor", 385 документов у 307
        объектов), и variants у всех 2 506 документов объектов пусты. Карточка
        читала эти пустые variants и печатала «Конструкторы: в справке не
        указано» — про 307 объектов это была неправда.

        Имя варианта добавляется, только когда конструкторов несколько: тогда
        оно и различает страницы, и годится в аргумент variant=… у
        get_1c_element.
        """
        otvet = await self.es_client.search({
            "query": {"bool": {"filter": [
                {"term": {"object": object_name}},
                {"term": {"type": "object_constructor"}},
            ]}},
            "size": 50,
            "sort": [{"name.keyword": {"order": "asc"}}],
            "_source": ["call_primary", "name_ru", "variants.variant"],
        })

        hits = (otvet or {}).get("hits", {}).get("hits", [])
        stroki = []
        for h in hits:
            doc = h["_source"]
            vyzov = doc.get("call_primary") or ""
            if not vyzov:
                continue
            varianty = doc.get("variants") or []
            imya_varianta = (varianty[0].get("variant") if varianty else "") \
                or doc.get("name_ru") or ""
            if len(hits) > 1 and imya_varianta:
                stroki.append(f"{vyzov} — вариант «{imya_varianta}»")
            else:
                stroki.append(vyzov)
        return stroki

    async def get_object_members_list(
        self, 
        object_name: str, 
        member_type: str = "all", 
        limit: int = 50
    ) -> Dict[str, Any]:
        """Получить список элементов объекта с фильтрацией по типу."""
        try:
            # Базовый фильтр по объекту
            query_filters = [{"term": {"object": object_name}}]
            
            # Добавляем фильтры по типу элементов. "all" тоже фильтруется —
            # без ограничения по VIDY_CHLENOV_OBEKTA запрос ловил документ
            # самого объекта (type="object"), у которого object тоже равен
            # имени объекта.
            if member_type == "all":
                query_filters.append({"terms": {"type": VIDY_CHLENOV_OBEKTA}})
            elif member_type == "methods":
                type_filters = [
                    {"term": {"type": "object_function"}},
                    {"term": {"type": "object_procedure"}},
                    {"term": {"type": "object_constructor"}}
                ]
                query_filters.append({"bool": {"should": type_filters}})
            elif member_type == "properties":
                query_filters.append({"term": {"type": "object_property"}})
            elif member_type == "events":
                query_filters.append({"term": {"type": "object_event"}})
            elif member_type == "constructors":
                query_filters.append({"term": {"type": "object_constructor"}})
            
            # Строим запрос
            elasticsearch_query = {
                "query": {
                    "bool": {
                        "filter": query_filters
                    }
                },
                "size": limit,
                "sort": [{"name.keyword": {"order": "asc"}}]
            }
            
            response = await self.es_client.search(elasticsearch_query)
            
            # Группируем результаты
            methods = []
            properties = []
            events = []
            
            for hit in response.get('hits', {}).get('hits', []):
                doc = hit['_source']
                doc_type = doc.get('type', '').lower()
                
                if 'function' in doc_type or 'procedure' in doc_type or 'constructor' in doc_type:
                    methods.append(doc)
                elif 'property' in doc_type:
                    properties.append(doc)
                elif 'event' in doc_type:
                    events.append(doc)
            
            # total — сколько элементов в индексе, а не сколько поместилось в
            # ответ. Раньше здесь стояла сумма вернувшихся списков, поэтому по
            # ответу нельзя было понять, что limit срезал хвост.
            vsego = response.get("hits", {}).get("total", {})
            vsego_v_indekse = (
                vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)
            )
            itogovyi_total = max(
                vsego_v_indekse,
                len(methods) + len(properties) + len(events)
            )

            rezultat = {
                "object": object_name,
                "member_type": member_type,
                "methods": methods,
                "properties": properties,
                "events": events,
                "total": itogovyi_total,
            }

            # total=0 неоднозначен: объекта может не быть вовсе, а может — он
            # есть, просто у него нет элементов запрошенного вида (например,
            # "события" у объекта без событий, или "конструкторы" почти у
            # любого объекта, кроме считаных типов). Раньше оба случая
            # выглядели одинаково — агент слышал «не найден» про объект,
            # который есть, и тут же видел его в списке «похожих».
            if itogovyi_total == 0:
                rezultat["object_exists"] = await self.obekt_sushchestvuet(object_name)

            return rezultat

        except Exception as e:
            logger.error(f"Ошибка получения элементов объекта '{object_name}': {e}")
            return {
                "object": object_name,
                "member_type": member_type,
                "methods": [],
                "properties": [],
                "events": [],
                "total": 0,
                "error": str(e)
            }

    async def kartochka_elementa(
        self,
        name: str,
        object_name: Optional[str] = None,
        variant: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Находит элемент по точному имени, не выбирая молча при омонимии.

        Все обращения к Elasticsearch собраны под одним try/except: остальные
        публичные методы класса (find_help_by_query и другие) не дают
        исключению вылететь наружу, а превращают его в структурированный
        ответ. kind="error" отличим от пяти обычных значений — обработчик
        (Task 13) должен уметь отличить сбой связи от честного "не найдено".
        """
        try:
            if object_name:
                est_obekt = await self.obekt_sushchestvuet(object_name)
                if not est_obekt:
                    return {
                        "kind": "object_not_found",
                        "object": object_name,
                        "similar": await self.pohozhie_obekty(object_name),
                    }

            filtry = [{
                "bool": {
                    "should": [
                        {"term": {"name_ru.keyword": name}},
                        {"term": {"name_en.keyword": name}},
                    ],
                    "minimum_should_match": 1,
                }
            }]
            if object_name:
                filtry.append({"term": {"object": object_name}})

            otvet = await self.es_client.search({
                "query": {"bool": {"filter": filtry}},
                "size": 50,
            })
            hits = (otvet or {}).get("hits", {}).get("hits", [])
            vsego = (otvet or {}).get("hits", {}).get("total", {})
            vsego = vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)

            if not hits:
                return {
                    "kind": "not_found",
                    "name": name,
                    "similar": await self._pohozhie_elementy(name),
                }

            dokumenty = [h["_source"] for h in hits]

            if len(dokumenty) > 1:
                kandidaty = await self._uporyadochit_kandidatov(filtry, vsego)
                return {
                    "kind": "ambiguous",
                    "name": name,
                    "candidates": kandidaty[:KANDIDATOV_V_OTVETE],
                    "total": vsego,
                    "poryadok_polnyy": vsego <= POTOLOK_KANDIDATOV,
                }

            doc = dokumenty[0]

            if variant:
                imena = [v.get("variant", "") for v in (doc.get("variants") or [])]
                if variant not in imena:
                    return {"kind": "variant_not_found", "document": doc, "variants": imena}
                doc = dict(doc)
                doc["variants"] = [
                    v for v in doc["variants"] if v.get("variant") == variant
                ]

            return {"kind": "card", "document": doc}
        except Exception as e:
            logger.error(f"Ошибка дизамбигуации элемента '{name}': {e}")
            return {"kind": "error", "name": name, "error": str(e)}

    async def _uporyadochit_kandidatov(self, filtry: list, vsego: int) -> List[Dict[str, Any]]:
        """Кандидаты при омонимии в защитимом порядке.

        Порядок: сначала настоящие типы языка, внутри — объекты, у которых в
        справке больше элементов. Прежний порядок был заявкой без покрытия:
        окно из 50 документов набиралось фильтрующим запросом, где у всех
        совпадений одинаковая оценка (то есть окно произвольно), и
        сортировалось по имени объекта — по алфавиту. Для «Количество» это
        давало АгрегатыРегистраНакопления и ВсеЭлементыФормы под заголовком
        «Наиболее вероятные», а ТаблицаЗначений, Массив и Структура не
        показывались вовсе: агент делал вывод, что у обычных коллекций
        «Количество» нет.

        Число членов объекта — дешёвый и проверяемый признак: одна агрегация на
        все объекты-владельцы сразу. Ранжирование по релевантности сюда не
        годится: запрос фильтрующий, оценки равны у всех.
        """
        otvet = await self.es_client.search({
            "query": {"bool": {"filter": filtry}},
            "size": min(max(vsego, 1), POTOLOK_KANDIDATOV),
            "_source": {"includes": POLYA_STROKI_SPISKA},
        })
        dokumenty = [h["_source"] for h in (otvet or {}).get("hits", {}).get("hits", [])]

        chleny = await self._chislo_chlenov(
            [d.get("object") for d in dokumenty]
        )
        dokumenty.sort(key=lambda d: (
            not _nastoyashchiy_tip(d.get("object")),
            -chleny.get(d.get("object") or "", 0),
            d.get("object") or "",
        ))
        return dokumenty

    async def _chislo_chlenov(self, imena_obektov: list) -> Dict[str, int]:
        """Сколько элементов справки у каждого из перечисленных объектов.

        Одной агрегацией: пять сотен отдельных запросов ради сортировки пяти
        строк ответа не окупились бы.
        """
        imena = sorted({i for i in imena_obektov if i})
        if not imena:
            return {}

        otvet = await self.es_client.search({
            "query": {"bool": {"filter": [
                {"terms": {"object": imena}},
                {"terms": {"type": VIDY_CHLENOV_OBEKTA}},
            ]}},
            "size": 0,
            "aggs": {"po_obektu": {"terms": {"field": "object", "size": len(imena)}}},
        })
        buckets = (otvet or {}).get("aggregations", {}).get("po_obektu", {}).get("buckets", [])
        return {b["key"]: b["doc_count"] for b in buckets}

    async def obekt_sushchestvuet(self, object_name: str) -> bool:
        """Есть ли в справке объект с таким именем.

        Публичный метод: его зовёт и kartochka_elementa, и обработчик поиска —
        пустая выдача find_1c_help при заданном object обязана отличать «нет
        такого элемента» от «нет такого объекта».

        Исключение здесь намеренно не глушится: False означает «объекта в
        справке нет», а при сбое ES мы этого не знаем — подмена сбоя на False
        выдала бы kind="object_not_found" за достоверный факт. Пусть
        исключение всплывёт к вызывающему и станет честной ошибкой.
        """
        otvet = await self.es_client.search({
            "query": {"bool": {"filter": [{"term": {"object": object_name}}]}},
            "size": 0,
        })
        vsego = (otvet or {}).get("hits", {}).get("total", {})
        vsego = vsego.get("value", 0) if isinstance(vsego, dict) else (vsego or 0)
        return vsego > 0

    async def pohozhie_obekty(self, object_name: str, limit: int = 5) -> List[str]:
        """Объекты с близким именем — вместо молчаливой подмены запроса.

        Искать нужно среди имён объектов, а не имён элементов: name_ru у
        элемента — это имя метода/свойства, и нечёткий поиск по нему находит
        случайное совпадение корня в чужой фразе (например, «Строка» входит в
        «Из строки» у конструктора), после чего в подсказку попадал владелец
        найденного элемента, никак не похожий на запрос. Документы объектов
        (type="object", 2506 штук) хранят имя объекта прямо в name_ru — их и
        матчим.

        Публичный метод: его вызывает и kartochka_elementa, и напрямую
        обработчик состава объекта (Task 13). Исключение ES здесь не
        перехватывается: пустой список — это ответ "похожих объектов нет",
        и подмена им сбоя связи сделала бы сбой неотличимым от честного
        отсутствия данных — ровно тот дефект, ради которого написана вся
        задача. Пусть исключение поднимется к вызывающему: kartochka_elementa
        превратит его в kind="error", а обработчик Task 13, вызывающий этот
        метод напрямую, получит то же исключение и не примет обрыв связи за
        "похожих нет, проверь написание".
        """
        otvet = await self.es_client.search({
            "query": {
                "bool": {
                    "must": [{"match": {"name_ru": {"query": object_name, "fuzziness": "AUTO"}}}],
                    "filter": [{"term": {"type": "object"}}],
                }
            },
            "size": 50,
            "_source": ["name_ru"],
        })

        vidennye = []
        for h in (otvet or {}).get("hits", {}).get("hits", []):
            imya = h["_source"].get("name_ru")
            if imya and imya not in vidennye:
                vidennye.append(imya)
            if len(vidennye) >= limit:
                break
        return vidennye

    async def _pohozhie_elementy(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Элементы с близким именем для ответа «точного совпадения нет».

        Вызывается только из kartochka_elementa, внутри её try/except.
        Исключение здесь не перехватывается по той же причине, что и в
        pohozhie_obekty: пустой список — это утверждение "похожих элементов
        нет", и подменять им сбой связи значит выдавать ложь за факт. Пусть
        поднимется наверх и станет честным kind="error".
        """
        otvet = await self.es_client.search({
            "query": {"match": {"name_ru": {"query": name, "fuzziness": "AUTO"}}},
            "size": limit,
        })
        return [h["_source"] for h in (otvet or {}).get("hits", {}).get("hits", [])]
