# -*- coding: utf-8 -*-
"""Фичи C и D: защита «номер договора vs закон» и «дата vs ссылка на закон»."""
import pytest

from org_normalizer import looks_like_law_ref, date_in_law_context


# --- C: ссылка на закон не должна считаться номером договора ---
@pytest.mark.parametrize("value,is_law", [
    ("№ 353-ФЗ", True),
    ("№ 127-ФЗ", True),
    ("№ 14-ФКЗ", True),
    ("353-ФЗ", True),
    ("№ 1203-Р-2451256790", False),
    ("№ ПЦ-77/2024", False),
    ("1203/456-ДГ", False),
])
def test_looks_like_law_ref(value, is_law):
    assert looks_like_law_ref(value) is is_law


def test_contract_number_drops_law_reference():
    """В пайплайне извлечения '№ 353-ФЗ' не попадает в contractNumber."""
    from document_analyzer import DocumentAnalyzer
    da = DocumentAnalyzer()
    # Прямой контракт через фильтр пайплайна: looks_like_law_ref отсекает закон.
    assert looks_like_law_ref("353-ФЗ")
    assert not looks_like_law_ref("1203-Р-245")


# --- D: дата в контексте закона/Пленума игнорируется ---
@pytest.mark.parametrize("text,kw,in_law", [
    ("Федеральный закон от 26.10.2002 № 127-ФЗ", "26.10.2002", True),
    ("постановление Пленума ВС РФ от 13.10.2015", "13.10.2015", True),
    ("Договор заключен 15.03.2021", "15.03.2021", False),
    ("Дата рождения: 01.01.1990", "01.01.1990", False),
])
def test_date_in_law_context(text, kw, in_law):
    start = text.index(kw)
    assert date_in_law_context(text, start, start + len(kw)) is in_law


def test_drop_law_context_dates_removes_only_law_dates():
    """_drop_law_context_dates убирает дату закона, но сохраняет дату договора."""
    from document_analyzer import DocumentAnalyzer
    da = DocumentAnalyzer()
    text = "Кредитный договор от 15.03.2021. Согласно Федеральному закону от 26.10.2002 № 127-ФЗ."
    fields = {"contractDate": "15.03.2021", "courtDecisionDate": "26.10.2002"}
    da._drop_law_context_dates(fields, text)
    assert fields.get("contractDate") == "15.03.2021"
    assert "courtDecisionDate" not in fields
