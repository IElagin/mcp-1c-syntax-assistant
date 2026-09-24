"""Version conditions survive parsing, indexing and both card renderers."""

import pytest
from pathlib import Path
from bs4 import BeautifulSoup

from src.handlers.element_card import render_element_card, render_object_card
from src.handlers.ui_strings import EN_STRINGS, RU_STRINGS
from src.parsers.dialects import EN_DIALECT, RU_DIALECT
from src.parsers.html_parser import HTMLParser
from src.parsers.indexer import ElasticsearchIndexer
from tests.conftest import FIXTURES_RU

FIXTURES_EN = Path(__file__).parent / 'fixtures/hbk-en'


@pytest.mark.parametrize('fixtures,dialect,strings,available,changed,deprecated', [
    (FIXTURES_RU, RU_DIALECT, RU_STRINGS,
     'Доступен, начиная с версии 8.3.6 (в режиме совместимости с версией 8.3.6 и последующими).',
     'Описание изменено в версии 8.3.20.',
     'Не рекомендуется использовать, начиная с версии 8.3.10.'),
    (FIXTURES_EN, EN_DIALECT, EN_STRINGS,
     'Available since version 8.3.6 (in version 8.3.6 compatibility mode and later).',
     'Description changed in version 8.3.20.',
     'It is not recommended to use since version 8.3.10.'),
])
@pytest.mark.parametrize('has_available', [True, False])
def test_version_conditions_survive_to_card(fixtures, dialect, strings, available,
                                           changed, deprecated, has_available):
    soup = BeautifulSoup((fixtures / 'array_add.html').read_bytes(), 'html.parser')
    for node in soup.select('p.V8SH_versionInfo'):
        node.decompose()
    expected = ([available] if has_available else []) + [changed, deprecated]
    for notice in expected + expected:
        node = soup.new_tag('p', attrs={'class': 'V8SH_versionInfo'})
        node.string = notice
        soup.body.append(node)
    doc = HTMLParser(dialect=dialect).parse_html_content(
        str(soup).encode('utf-8'), 'objects/catalog234/Array/methods/Add772.html')
    assert doc.version_notes == expected
    assert doc.version_from == ('8.3.6' if has_available else None)
    stored = ElasticsearchIndexer(None)._prepare_document(doc)
    for card in (render_element_card(stored, strings=strings),
                 render_object_card(stored, {}, strings=strings)):
        for notice in expected:
            assert card.count(notice) == 1
        assert strings.available_since.format(version='8.3.10') not in card
        assert strings.available_since.format(version='8.3.20') not in card


def test_legacy_index_version_still_renders():
    card = render_element_card({'type': 'global_function', 'name': 'Example',
                                'version_from': '8.0'})
    assert 'Доступно с: 8.0' in card
