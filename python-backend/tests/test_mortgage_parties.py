# -*- coding: utf-8 -*-
"""Ипотека: разбор сторон — представитель истца, адрес одиночного ответчика,
несовершеннолетние со-ответчики «в лице законного представителя».

Синтетические тексты (без внешних .docx) — детерминированно и быстро.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import fio_detector as fd  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402


# --- #5: несовершеннолетние со-ответчики -----------------------------------

def test_represented_minor_name_full_string():
    line = "Федотьев Даниил Александрович в лице законного представителя ФЕДОТЬЕВА АЛЕКСАНДРА АРТАВАЗДОВИЧА"
    assert fd._represented_minor_name(line) == (
        "Федотьев Даниил Александрович в лице законного представителя "
        "Федотьева Александра Артаваздовича"
    )


def test_represented_minor_name_rejects_plain_fio():
    assert fd._represented_minor_name("Иванов Иван Иванович") is None
    assert fd._represented_minor_name("Цена иска: 100 руб.") is None


def test_extract_debtors_includes_minors():
    text = (
        "Ответчики:\n"
        "ФЕДОТЬЕВ АЛЕКСАНДР АРТАВАЗДОВИЧ\n"
        "ИНН: 261543614802,\n"
        "Дата рождения: 22.08.1989,\n"
        "Адрес регистрации: 353132, Краснодарский край, ст-ца Березанская, ул. Жлобы, д. 8\n"
        "Федотьев Даниил Александрович в лице законного представителя ФЕДОТЬЕВА АЛЕКСАНДРА АРТАВАЗДОВИЧА\n"
        "Дата рождения: 11.10.2021,\n"
        "СНИЛС 574-699-736 77\n"
        "Адрес регистрации: 353132, Краснодарский край, ст-ца Березанская, ул. Жлобы, д. 8\n"
        "Цена иска: 1177237,23 руб.\n"
    )
    debtors = fd.extract_debtors(text)
    names = [d["name"] for d in debtors]
    assert "Федотьев Александр Артаваздович" in names
    assert any("в лице законного представителя" in n for n in names)
    assert all(d.get("address") for d in debtors)


# --- #2: представитель истца -----------------------------------------------

def test_extract_representative_skips_branch_line():
    da = DocumentAnalyzer()
    text = (
        "Представитель истца:\n"
        "Северодвинское отделение №2221\n"
        "Чепелов Иван Александрович\n"
        "СНИЛС 131-761-878 92\n"
    )
    assert da._extract_representative_name(text) == "Чепелов Иван Александрович"


def test_extract_representative_none_when_absent():
    da = DocumentAnalyzer()
    assert da._extract_representative_name("Истец:\nПАО Сбербанк\n") is None


# --- #4: адрес одиночного ответчика восполняется из записи блока -------------

def test_single_debtor_address_backfilled():
    """Плоский applicantAddress пуст, но запись блока «Ответчик:» несёт адрес —
    он должен попасть в единственного ответчика (реальный путь resolve)."""
    da = DocumentAnalyzer()
    text = (
        "Ответчик:\n"
        "НУРИЕВА ЕЛЕНА ВАЛИДИНОВНА\n"
        "Дата рождения: 27.08.1978\n"
        "ИНН 231552257675\n"
        "Адрес регистрации: 353911, Краснодарский край, г. Новороссийск, пер. Геленджикский, д. 8Б\n"
        "Цена иска: 3 670 388,48 руб.\n"
    )
    fields = {"applicantName": "Нуриева Елена Валидиновна", "applicantAddress": ""}
    debtors_result, _ = da._resolve_debtors_and_third_parties(fields, text, {})
    assert len(debtors_result) == 1
    assert debtors_result[0]["address"].startswith("353911")
