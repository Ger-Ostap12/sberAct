# -*- coding: utf-8 -*-
"""Канонизация переноса между меткой и её значением (фаза 2a-2).

Один и тот же блок шапки банки печатают и в строку («Должник: Иванов»), и с
переносом («Должник:\\nИванов»); при PDF→docx перенос появляется ещё и сам, когда
шапка двухколоночная. Для смысла это одно и то же, для паттернов — нет: замер
(`measure_format_robustness.py`) показал 8 сломанных документов из 74.

⚠️ Направление канонизации выбрано ЗАМЕРОМ по всему корпусу, а не рассуждением:
  - «джойн» (значение поднимаем на строку метки) — эталон не меняется, мутация
    ломает 2 из 74 вместо 8;
  - «сплит» (всегда перенос) — та же устойчивость, но эталон менялся у 6 файлов.
Тесты фиксируют выбранное направление, чтобы его не развернули «по интуиции».
"""
import logging
import os
import sys
import types

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from document_analyzer import DocumentAnalyzer  # noqa: E402
from label_synonyms import all_labels  # noqa: E402

_stub = types.SimpleNamespace(
    _LABEL_ONLY_LINE_RE=DocumentAnalyzer._LABEL_ONLY_LINE_RE,
    _LABEL_STARTS_LINE_RE=DocumentAnalyzer._LABEL_STARTS_LINE_RE,
    _is_title_line=DocumentAnalyzer._is_title_line.__get__(
        types.SimpleNamespace(_TITLE_START_RE=DocumentAnalyzer._TITLE_START_RE,
                              _TITLE_CAPS_RE=DocumentAnalyzer._TITLE_CAPS_RE)),
)


def norm(text: str) -> str:
    return DocumentAnalyzer._normalize_label_wrap_for_matching(_stub, text)


def test_value_is_lifted_to_label_line():
    assert norm("Должник:\nИванов Иван Иванович") == "Должник: Иванов Иван Иванович"


def test_already_joined_is_untouched():
    text = "Должник: Иванов Иван Иванович"
    assert norm(text) == text


def test_labels_come_from_registry():
    """Метки — данные, а не строки в логике: новый банк = правка label_synonyms."""
    for label in ("Должник", "Ответчик", "Заёмщик", "Кредитор", "Взыскатель",
                  "Адрес регистрации", "Юридический адрес", "Дата рождения", "СНИЛС"):
        assert label in all_labels()
    assert norm("Взыскатель:\nПАО Сбербанк") == "Взыскатель: ПАО Сбербанк"


def test_longer_label_wins_over_shorter():
    """«Адрес регистрации» не должен разбираться как «Адрес» + хвост «регистрации»."""
    assert norm("Адрес регистрации:\n344068, г. Ростов") == "Адрес регистрации: 344068, г. Ростов"


def test_label_without_value_is_not_glued_to_title():
    """АНТИ-РЕГРЕССИЯ («Заявление о включении в реестр требований кредиторов 2 л.docx»).

    «СНИЛС:» — метка БЕЗ значения, следом заголовок документа. Без гарда
    канонизация давала «СНИЛС: ЗАЯВЛЕНИЕ», то есть выдумывала значение.
    """
    text = "\tСНИЛС:\nЗАЯВЛЕНИЕ"
    assert norm(text) == text


def test_label_is_not_glued_to_another_label():
    """Значением не может быть чужая метка."""
    text = "Должник:\nАдрес: 344068, г. Ростов"
    assert norm(text) == text


def test_label_in_prose_is_not_touched():
    """АНТИ-РЕГРЕССИЯ: канонизируем только строку-метку, прозу — никогда.

    Ослабление правила до «строка ЗАКАНЧИВАЕТСЯ меткой» ломало «Заявление о
    включении в реестр требований кредиторов 3л.docx»: склеивались куски шапки,
    applicantName становился «рбитражный суд Ростовско», кредитор терялся.
    В прозе двоеточие после слова-метки не значит «дальше значение».
    """
    text = "гражданина ЕПИФАНОВА Л.Н. (27.11.1961 года рождения, адрес регистрации:\n346311 РОССИЯ"
    assert norm(text) == text


def test_label_with_value_on_same_line_is_not_touched():
    """Метка в СЕРЕДИНЕ строки со значением после неё — уже канонична."""
    text = "прочий текст Должник: Иванов\nследующая строка"
    assert norm(text) == text


def test_word_ending_with_label_is_not_a_label():
    """«Взыскатель» — метка, «Довзыскатель» — нет: граница слова обязательна."""
    text = "Довзыскатель:\nИванов"
    assert norm(text) == text


def test_empty_line_after_label_is_kept():
    """Пустая строка — не «значение на следующей строке», не склеиваем."""
    text = "Должник:\n\nИванов Иван"
    assert norm(text) == text


def test_idempotent():
    once = norm("Кредитор:\nПАО Сбербанк\nАдрес:\n344068")
    assert norm(once) == once
