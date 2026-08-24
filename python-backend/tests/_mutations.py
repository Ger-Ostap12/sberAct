# -*- coding: utf-8 -*-
"""Косметические мутации текста заявления — общий код теста и measure-скрипта.

Каждая мутация меняет ФОРМУ документа, но не его СМЫСЛ: так же выглядит то же
самое заявление, набранное в другом банке, другим конвертером или другой вёрсткой.
Правильный разбор обязан вернуть на мутированном тексте те же значения, что и на
исходном. Любое расхождение — зависимость результата от типографики, то есть риск
на заявлении нового кредитора, которого нет в корпусе.

Мутации намеренно НЕ трогают цифры, имена и порядок слов — только пробелы,
кавычки, регистр меток и ё/е.
"""
from __future__ import annotations

import re
from typing import Callable, List, Tuple

# Метки шапки, вокруг которых крутится label-anchored разбор. Список намеренно
# короткий: мутируем только то, что реально встречается как метка блока.
_LABELS = ("Должник", "Кредитор", "Заявитель", "Ответчик", "Адрес", "ИНН", "ОГРН")


def m_yo(text: str) -> str:
    """ё → е. Половина банков пишет «Петров», половина «Пётров» — это одно имя."""
    return text.replace("ё", "е").replace("Ё", "Е")


def m_quotes(text: str) -> str:
    """«ёлочки» → "прямые". Зависит от конвертера, а не от содержания."""
    return text.replace("«", '"').replace("»", '"')


def m_nbsp(text: str) -> str:
    """Пробел в разрядах суммы → неразрывный (типовой docx банка)."""
    return re.sub(r"(\d) (\d{3})", "\\1 \\2", text)


def m_label_case(text: str) -> str:
    """«Должник:» → «ДОЛЖНИК:». Регистр метки — оформление, не смысл."""
    for label in _LABELS:
        text = re.sub(r"\b" + label + r"(?=\s*:)", label.upper(), text)
    return text


def m_wrap(text: str) -> str:
    """Перенос строки после метки — так рвёт двухколоночную шапку PDF→docx."""
    return re.sub(r"(" + "|".join(_LABELS) + r")\s*:\s+", "\\1:\n", text)


def m_double_spaces(text: str) -> str:
    """Двойные пробелы между словами (кривая вёрстка исходника)."""
    return re.sub(r"(?<=\w) (?=\w)", "  ", text, count=400)


# (имя, функция). Имя попадает в id теста и в отчёт measure-скрипта.
MUTATIONS: List[Tuple[str, Callable[[str], str]]] = [
    ("yo", m_yo),
    ("quotes", m_quotes),
    ("nbsp", m_nbsp),
    ("label_case", m_label_case),
    ("wrap", m_wrap),
    ("double_spaces", m_double_spaces),
]

# Человекочитаемые названия для отчёта (терминал, не id теста).
# ⚠️ Только символы из cp1251: консоль Windows по умолчанию в этой кодировке, и
# «→» (U+2192) роняет вывод с UnicodeEncodeError. Отсюда «->» вместо стрелки.
MUTATION_TITLES = {
    "yo": "ё -> е",
    "quotes": "кавычки «» -> \"\"",
    "nbsp": "неразрывный пробел в суммах",
    "label_case": "МЕТКИ КАПСОМ",
    "wrap": "перенос строки после метки",
    "double_spaces": "двойные пробелы",
}


def significant_result(result: dict) -> dict:
    """Плоский срез результата analyze() для сравнения «до/после мутации».

    Берём поля + характеристики, видимые пользователю на форме. `rawText` не
    сравниваем: он МЕНЯЕТСЯ по построению (мы же и мутировали текст), а нас
    интересует устойчивость ИЗВЛЕЧЁННЫХ данных, а не входа.
    """
    flat = {}
    for key, value in (result.get("fields") or {}).items():
        if value not in (None, "", [], {}):
            flat[key] = str(value)
    flat["#documentType"] = str(result.get("documentType"))
    flat["#entityType"] = str(result.get("entityType"))
    flat["#obligations"] = str(len(result.get("obligations") or []))
    flat["#collaterals"] = str(len(result.get("collaterals") or []))
    flat["#debtors"] = str(len(result.get("debtors") or []))
    return flat


def diff_fields(base: dict, mutated: dict) -> List[str]:
    """Имена полей, значение которых мутация изменила (в т.ч. появление/пропажу)."""
    return sorted(k for k in set(base) | set(mutated) if base.get(k) != mutated.get(k))


# --- Мутации САМОЙ МЕТКИ (ось §S.2.D «нечёткое сопоставление меток») ----------
#
# Отличие от косметических выше: меняется не типографика, а НАПИСАНИЕ метки — на
# другое, которое `label_synonyms` уже объявляет равнозначным, либо на бытовое
# сокращение. Если разбор действительно label-anchored и опирается на реестр,
# такая замена обязана пройти незаметно.
#
# Держатся ОТДЕЛЬНЫМ списком и НЕ входят в MUTATIONS: в `test_format_robustness`
# участвуют только косметические мутации, там зелёная базовая линия. Эти —
# измерительные, их цель дать честную цену §S.2.D, а не покрасить тест.
# Считай их исполняемым определением готовности: §S.2.D сделана тогда, когда
# `measure_label_robustness` показывает по ним ноль.

# Пары «как в корпусе» -> «как у другого банка». Оба варианта уже перечислены в
# label_synonyms как один и тот же блок.
_HEADER_SWAP = (
    ("Должник", "Заёмщик"),
    ("Кредитор", "Взыскатель"),
    ("Заявитель", "Кредитор"),
)

# Сокращения, которыми банки пишут те же подписи полей.
_LABEL_ABBREV = (
    ("Государственная пошлина", "Госпошлина"),
    ("Место нахождения", "Местонахождение"),
    ("Адрес регистрации", "Адрес рег."),
    ("Дата рождения", "Дата рожд."),
)

# Уточнение в скобках — ровно то, что реестр держит как отдельные строки.
_LABEL_PAREN = (
    ("Должник", "Должник (ответчик)"),
    ("Заявитель", "Заявитель (кредитор)"),
)


def m_label_synonym(text: str) -> str:
    """«Должник:» -> «Заёмщик:». Синоним из реестра — блок тот же."""
    for src, dst in _HEADER_SWAP:
        # Если метка-приёмник в документе уже есть, подмена породила бы ДВА
        # одинаковых блока — это меняет смысл, а не форму. Пропускаем.
        if re.search(rf"\b{dst}\s*:", text):
            continue
        text = re.sub(rf"\b{src}(?=\s*:)", dst, text)
    return text


def m_label_abbrev(text: str) -> str:
    """«Место нахождения:» -> «Местонахождение:». То же поле, другое написание."""
    for src, dst in _LABEL_ABBREV:
        text = re.sub(rf"\b{re.escape(src)}(?=\s*:)", dst, text, flags=re.IGNORECASE)
    return text


def m_label_paren(text: str) -> str:
    """«Должник:» -> «Должник (ответчик):». Уточнение в скобках."""
    for src, dst in _LABEL_PAREN:
        text = re.sub(rf"(?<!\()\b{src}(?=\s*:)", dst, text)
    return text


def m_label_dash(text: str) -> str:
    """«Должник:» -> «Должник —». Разделитель метки и значения — тире, не двоеточие."""
    return re.sub(r"\b(" + "|".join(_LABELS) + r")\s*:", r"\1 —", text)


LABEL_MUTATIONS: List[Tuple[str, Callable[[str], str]]] = [
    ("label_synonym", m_label_synonym),
    ("label_abbrev", m_label_abbrev),
    ("label_paren", m_label_paren),
    ("label_dash", m_label_dash),
]

LABEL_MUTATION_TITLES = {
    "label_synonym": "метка -> синоним из реестра",
    "label_abbrev": "метка -> сокращение",
    "label_paren": "метка + уточнение в скобках",
    "label_dash": "разделитель метки: тире вместо двоеточия",
}
