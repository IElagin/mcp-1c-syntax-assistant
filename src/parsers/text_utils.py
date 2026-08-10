"""Нормализация текста справки 1С.

Справка — HTML, свёрстанный под просмотр человеком, поэтому тип значения
оформлен то ссылкой, то обычным текстом, пробелы бывают неразрывными, а после
точки пробела иногда нет вовсе. Всё это чинится здесь, в одном месте, чтобы
парсер занимался структурой, а не орфографией.
"""

import re
from typing import Tuple

from bs4 import BeautifulSoup

_PERIOD_WITHOUT_SPACE = re.compile(r'([а-яёa-z0-9])\.([А-ЯЁA-Z])')
_BLANK_LINE_RUN = re.compile(r'\n{3,}')


def normalize_whitespace(text: str) -> str:
    """Неразрывные пробелы — обычными, кратные пробелы — одинарными.

    Неразрывный пробел в примере кода — синтаксическая ошибка 1С: скопированный
    агентом фрагмент не скомпилируется.
    """
    return " ".join((text or "").replace('\xa0', ' ').split())


def restore_space_after_period(text: str) -> str:
    """Ставит пробел там, где вёрстка его потеряла."""
    return _PERIOD_WITHOUT_SPACE.sub(r'\1. \2', text or "")


def clean_description(text: str) -> str:
    """Полная чистка текста описания."""
    return restore_space_after_period(normalize_whitespace(text))


def clean_multiline_description(text: str) -> str:
    """Та же чистка, но перевод строки остаётся переводом строки.

    Форма конструкции — часть ответа: «Для <Имя> = <Выражение> Цикл» и тело
    цикла стоят на разных строках, и склеенные в одну строку они перестают
    быть образцом кода.
    """
    lines = [clean_description(line) for line in (text or "").split("\n")]
    return _BLANK_LINE_RUN.sub("\n\n", "\n".join(lines)).strip()


def text_from_html(html: str) -> str:
    """Текст фрагмента справки; <br> становится переводом строки."""
    soup = BeautifulSoup(html or "", 'html.parser')
    for br in soup.find_all('br'):
        br.replace_with('\n')
    return soup.get_text().replace('\xa0', ' ')


def split_type_and_note(html: str, type_label: str = "Тип:") -> Tuple[str, str]:
    """Разделяет 'Тип: <a>Массив</a>. <br>Пояснение' на ('Массив', 'Пояснение').

    Тип и пояснение раньше лежали в одном поле, и половина «типов» была абзацем
    из трёх предложений — по такому значению нельзя понять, что вернёт вызов.

    Перечисление типов через запятую («Тип: Строка, Число.») сохраняется целиком:
    выбирать один из них сервер не вправе.

    Метка приходит аргументом: в английской книге тот же раздел начинается с
    «Type:», и захардкоженное «Тип:» молча отдало бы весь текст как описание,
    оставив тип пустым.
    """
    text = text_from_html(html).strip()
    if not text.startswith(type_label):
        return "", clean_description(text)

    rest = text[len(type_label):].strip()
    boundaries = [p for p in (rest.find('.'), rest.find('\n')) if p != -1]
    if not boundaries:
        return normalize_whitespace(rest), ""

    boundary = min(boundaries)
    value_type = normalize_whitespace(rest[:boundary])
    note = clean_description(rest[boundary + 1:])
    return value_type, note
