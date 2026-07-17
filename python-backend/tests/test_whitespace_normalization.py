# -*- coding: utf-8 -*-
"""Канонизация горизонтальных пробелов до сопоставления (фаза 2a).

Разбор не должен зависеть от типографики: то же заявление, набранное в другом
банке или прогнанное другим конвертером, отличается пробелами, а не смыслом.
Замер до правки (`tests/measure_format_robustness.py`): двойные пробелы меняли
результат у 42 документов из 79 (у 28 из них — `documentType`, то есть ветку
извлечения), неразрывный пробел в суммах — у 5. После правки обе оси — ноль.
"""
import logging
import os
import sys
import types

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from document_analyzer import DocumentAnalyzer  # noqa: E402

# Метод не трогает self — зовём несвязанным, чтобы не поднимать spaCy-модель.
_stub = types.SimpleNamespace(
    _HSPACE_ONE_RE=DocumentAnalyzer._HSPACE_ONE_RE,
    _HSPACE_RUN_RE=DocumentAnalyzer._HSPACE_RUN_RE,
)


def norm(text: str) -> str:
    return DocumentAnalyzer._normalize_whitespace_for_matching(_stub, text)


def test_double_spaces_collapse():
    assert norm("Должник:  Иванов  Иван") == "Должник: Иванов Иван"


def test_nbsp_in_amount_becomes_regular_space():
    """«1 490 913,00» с неразрывными пробелами — типовой docx банка."""
    assert norm("1\xa0490\xa0913,00") == "1 490 913,00"


def test_tabs_collapse_to_single_space():
    """Реальный случай (умерший сос.docx): «расположенный \\t\\tпо адресу»."""
    assert norm("расположенный \t\tпо адресу") == "расположенный по адресу"


def test_thin_and_figure_spaces_normalized():
    assert norm("1 490 913") == "1 490 913"


def test_zero_width_nobreak_space_normalized():
    """U+FEFF внутри текста — след конвертера, для смысла это пробел."""
    assert norm("ООО﻿«Вектор»") == "ООО «Вектор»"


def test_newlines_are_never_touched():
    """КЛЮЧЕВОЕ: на структуре строк держатся label-anchored слои и таблицы.

    «Должник:» + следующая строка — основной приём разбора шапки; схлопни мы
    переводы строк, поехал бы весь label-anchored разбор.
    """
    text = "Должник:\nИванов Иван\n\nКредитор:\nПАО Сбербанк"
    assert norm(text) == text


def test_newline_with_trailing_spaces_keeps_newline():
    assert norm("Должник:  \n  Иванов") == "Должник: \n Иванов"


def test_single_spaces_untouched():
    text = "Арбитражный суд Ростовской области"
    assert norm(text) == text


def test_idempotent():
    """Повторная нормализация ничего не меняет — иначе слои бы «дрейфовали»."""
    once = norm("а\xa0\xa0б  в\t\tг")
    assert norm(once) == once
