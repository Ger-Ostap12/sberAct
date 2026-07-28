# -*- coding: utf-8 -*-
"""Склонение названия суда в родительный падеж для акта ([002.1], ипотека).

Склоняем прилагательные и слово «суд» (до него включительно), хвост-топоним
оставляем как есть."""
import pytest


@pytest.fixture(scope="module")
def generator():
    from document_generator import DocumentGenerator
    return DocumentGenerator.__new__(DocumentGenerator)


CASES = [
    ("Ворошиловский районный суд г. Ростова-на-Дону",
     "Ворошиловского районного суда г. Ростова-на-Дону"),
    ("Ленинский районный суд города Ростова-на-Дону",
     "Ленинского районного суда города Ростова-на-Дону"),
    ("Октябрьский районный суд", "Октябрьского районного суда"),
]


@pytest.mark.parametrize("nominative,genitive", CASES)
def test_court_name_to_genitive(generator, nominative, genitive):
    assert generator._court_name_to_genitive(nominative) == genitive


def test_empty_and_none(generator):
    assert generator._court_name_to_genitive("") == ""
    assert generator._court_name_to_genitive("   ") == "   "


def test_first_letter_capitalization_preserved(generator):
    # Первое слово остаётся с заглавной, «районного/суда» — строчные.
    out = generator._court_name_to_genitive("Ворошиловский районный суд")
    assert out[0].isupper()
    assert out == "Ворошиловского районного суда"
