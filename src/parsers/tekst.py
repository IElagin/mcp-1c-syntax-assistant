"""Нормализация текста справки 1С.

Справка — HTML, свёрстанный под просмотр человеком, поэтому тип значения
оформлен то ссылкой, то обычным текстом, пробелы бывают неразрывными, а после
точки пробела иногда нет вовсе. Всё это чинится здесь, в одном месте, чтобы
парсер занимался структурой, а не орфографией.
"""

import re

from bs4 import BeautifulSoup

# Пробел после точки пропадает при вёрстке через <br>: «не по ссылке.Не работает».
# Обрыв слова на такой границе меняет смысл фразы, а обрезка по границе фразы
# перестаёт находить границу вовсе.
_TOCHKA_BEZ_PROBELA = re.compile(r'([а-яёa-z0-9])\.([А-ЯЁA-Z])')


def normalizovat_probely(tekst: str) -> str:
    """Неразрывные пробелы — обычными, кратные пробелы — одинарными.

    Неразрывный пробел в примере кода — синтаксическая ошибка 1С: скопированный
    агентом фрагмент не скомпилируется.
    """
    return " ".join((tekst or "").replace('\xa0', ' ').split())


def vosstanovit_probel_posle_tochki(tekst: str) -> str:
    """Ставит пробел там, где вёрстка его потеряла."""
    return _TOCHKA_BEZ_PROBELA.sub(r'\1. \2', tekst or "")


def pochistit_opisanie(tekst: str) -> str:
    """Полная чистка текста описания."""
    return vosstanovit_probel_posle_tochki(normalizovat_probely(tekst))


def tekst_iz_html(html: str) -> str:
    """Текст фрагмента справки; <br> становится переводом строки."""
    sup = BeautifulSoup(html or "", 'html.parser')
    for br in sup.find_all('br'):
        br.replace_with('\n')
    return sup.get_text().replace('\xa0', ' ')


def izvlech_tip_i_poyasnenie(html: str) -> tuple:
    """Разделяет 'Тип: <a>Массив</a>. <br>Пояснение' на ('Массив', 'Пояснение').

    Тип и пояснение раньше лежали в одном поле, и половина «типов» была абзацем
    из трёх предложений — по такому значению нельзя понять, что вернёт вызов.

    Перечисление типов через запятую («Тип: Строка, Число.») сохраняется целиком:
    выбирать один из них сервер не вправе.
    """
    tekst = tekst_iz_html(html).strip()
    if not tekst.startswith('Тип:'):
        return "", pochistit_opisanie(tekst)

    ostatok = tekst[len('Тип:'):].strip()
    granitsy = [p for p in (ostatok.find('.'), ostatok.find('\n')) if p != -1]
    if not granitsy:
        return normalizovat_probely(ostatok), ""

    granitsa = min(granitsy)
    tip = normalizovat_probely(ostatok[:granitsa])
    poyasnenie = pochistit_opisanie(ostatok[granitsa + 1:])
    return tip, poyasnenie
