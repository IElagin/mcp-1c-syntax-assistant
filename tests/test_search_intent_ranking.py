"""Natural-language search distinguishes an action from repeated object words."""

import pytest

from src.core.elasticsearch import ElasticsearchClient
from src.search.search_service import SearchService

pytestmark = [pytest.mark.integration, pytest.mark.elasticsearch, pytest.mark.search]


@pytest.fixture
async def intent_service(isolated_index):
    client = ElasticsearchClient()
    assert await client.connect()
    try:
        await client.create_index(index=isolated_index)
        docs = [
            {'name': 'Удалить (Delete)', 'name_ru': 'Удалить', 'name_en': 'Delete',
             'object': 'Массив', 'object_en': 'Array', 'full_path': 'Массив.Удалить',
             'type': 'object_procedure', 'description': 'Удаляет значение из массива по указанному индексу.',
             'variants': [{'parameters': [{'description': 'Индекс удаляемого элемента.'}]}]},
            {'name': 'Из массива (From array)', 'name_ru': 'Из массива',
             'object': 'COMSafeArray', 'full_path': 'COMSafeArray.Из массива',
             'type': 'object_constructor',
             'description': 'Создает COMSafeArray с заданным типом элемента из элементов массива значений.'},
            {'name': 'По количеству элементов', 'name_ru': 'По количеству элементов',
             'object': 'Массив', 'full_path': 'Массив.По количеству элементов',
             'type': 'object_constructor', 'description': 'Создает массив с заданным количеством элементов.'},
            {'name': 'Удалить (Delete)', 'name_ru': 'Удалить', 'object': 'Структура',
             'full_path': 'Структура.Удалить', 'type': 'object_procedure',
             'description': 'Удаляет значение структуры по ключу.'},
            {'name': 'Число (Number)', 'name_ru': 'Число', 'name_en': 'Number',
             'type': 'global_function',
             'description': 'Преобразует строку в число.',
             'variants': [{'return_type': ['Число']}]},
            {'name': 'Строка (String)', 'name_ru': 'Строка', 'name_en': 'String',
             'type': 'global_function',
             'description': 'Преобразует значение в строку. В число можно преобразовать строку другой функцией. '
                            'Преобразует число в строку.',
             'variants': [{'return_type': ['Строка']}]},
            {'name': 'ЧислоПрописью (NumberInWords)', 'name_ru': 'ЧислоПрописью',
             'type': 'global_function', 'description': 'Формирует представление числа прописью.',
             'variants': [{'return_type': ['Строка'], 'parameters': [
                 {'description': 'Число, которое необходимо преобразовать в строку прописью.'}]}]},
            {'name': 'ПравилоПреобразования', 'name_ru': 'ПравилоПреобразования',
             'type': 'object_property',
             'description': 'Как преобразовать строку в число. Как преобразовать число в строку.'},
        ]
        for doc in docs:
            await client.index_document(doc, index=isolated_index)
        await client.refresh_index(index=isolated_index)
        yield SearchService(client, index=isolated_index)
    finally:
        await client.disconnect()


@pytest.mark.parametrize('query', ['как удалить элемент массива', 'удалить элемент массива'])
async def test_action_and_parameter_description_beat_constructor_noise(intent_service, query):
    result = await intent_service.find_help_filtered(query, [], limit=3)
    assert result['results'][0]['full_path'] == 'Массив.Удалить'


async def test_intent_ranking_respects_explicit_owner(intent_service):
    result = await intent_service.find_help_filtered(
        'как удалить элемент массива', ['object_procedure'], object_name='Структура', limit=3)
    assert result['results']
    assert {doc['object'] for doc in result['results']} == {'Структура'}


@pytest.mark.parametrize('query', ['Массив.Удалить', 'Array.Delete'])
async def test_qualified_names_keep_their_owner(intent_service, query):
    result = await intent_service.find_help_filtered(query, [], limit=3)
    assert result['results'][0]['full_path'] == 'Массив.Удалить'
    assert {doc['object'] for doc in result['results']} == {'Массив'}


@pytest.mark.parametrize(('query', 'expected'), [
    ('как преобразовать строку в число', 'Число'),
    ('преобразовать строку в число', 'Число'),
    ('как преобразовать число в строку', 'Строка'),
    ('преобразовать число в строку', 'Строка'),
])
async def test_conversion_prefers_function_with_requested_return_type(intent_service, query, expected):
    result = await intent_service.find_help_filtered(query, [], limit=3)
    assert result['results'][0]['name_ru'] == expected


async def test_conversion_bonus_does_not_override_property_filter(intent_service):
    result = await intent_service.find_help_filtered(
        'как преобразовать строку в число', ['object_property'], limit=3)
    assert [doc['name_ru'] for doc in result['results']] == ['ПравилоПреобразования']
