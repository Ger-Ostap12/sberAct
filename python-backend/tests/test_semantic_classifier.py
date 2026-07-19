# -*- coding: utf-8 -*-
"""Тесты shadow-слоя семантической классификации (`semantic_classifier.py`).

Модуль ДИАГНОСТИЧЕСКИЙ (план `new_asnaliz`, фаза 1) — эти тесты проверяют его
изолированно и НЕ трогают golden. Если пакет `sentence-transformers` или
локальная модель недоступны в окружении — тесты пропускаются (skip), а не
падают: отсутствие опциональной зависимости не должно ломать прогон.
"""
import pytest
from semantic_classifier import classify_semantic, _ensure_model
from semantic_reference_phrases import SEMANTIC_DOCUMENT_TYPES

pytestmark = pytest.mark.skipif(
    not _ensure_model(),
    reason="sentence-transformers / локальная модель недоступны — shadow-слой опционален",
)


def test_rtk_inclusion_sentence_matches_rtk_application():
    text = (
        "ЗАЯВЛЕНИЕ о включении требования кредитора в реестр требований кредиторов\n"
        "Прошу включить в реестр требований кредиторов должника требование "
        "ПАО Сбербанк в размере 1 500 000 рублей в третью очередь удовлетворения."
    )
    label, score, sentence = classify_semantic(text, SEMANTIC_DOCUMENT_TYPES)
    assert label == "rtk_application"
    assert score >= 0.55
    assert sentence


def test_ip_realization_sentence_matches_ip_enforcement_realization():
    text = (
        "Прошу признать индивидуального предпринимателя Иванова Ивана Ивановича "
        "несостоятельным банкротом и ввести процедуру реализации имущества гражданина."
    )
    label, _score, _sentence = classify_semantic(text, SEMANTIC_DOCUMENT_TYPES)
    assert label == "ip_enforcement_realization"


def test_empty_text_returns_none():
    assert classify_semantic("", SEMANTIC_DOCUMENT_TYPES) == (None, 0.0, "")


def test_below_threshold_returns_none():
    text = "Съешь ещё этих мягких французских булок, да выпей же чаю."
    label, _score, _sentence = classify_semantic(text, SEMANTIC_DOCUMENT_TYPES, threshold=0.9)
    assert label is None
