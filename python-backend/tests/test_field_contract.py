# -*- coding: utf-8 -*-
"""Контракт поля: тип значения, владение текстом, инвариант каскада.

Реальные случаи из корпуса (файл указан в тесте) + негативные: контракт обязан
молчать там, где значение законное. Ложняк здесь дороже пропуска: вычищенное
поле юрист заметит, а лишний флаг обесценит подсветку.
"""
import logging
import os
import sys

import pytest

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

import field_contract as FC  # noqa: E402


# --- тип значения -----------------------------------------------------------
def test_money_field_rejects_text():
    """«Арбитражный суд Ростовской области» в loanDebt — Заявление РФЛ1.docx."""
    assert FC.check_value("loanDebt", "Арбитражный суд Ростовской области")


def test_money_field_rejects_text_with_newline():
    """Медведев М.Ю.docx: к суду прилип перенос и слово «Адрес»."""
    assert FC.check_value("loanDebt", "Арбитражный суд Ростовской области\nАдрес")


@pytest.mark.parametrize("value", ["25 000,00", "1 490 913,00", "163210,00", "0,00", "100000"])
def test_money_field_accepts_real_amounts(value):
    assert FC.check_value("totalDebt", value) is None


def test_money_field_accepts_nbsp_separators():
    """Разряды неразрывным пробелом — типовой docx банка, это валидная сумма."""
    assert FC.check_value("totalDebt", "1\xa0490\xa0913,00") is None


def test_zero_is_valid_money():
    """Законный ноль: неустойка может быть не начислена. Чистить нельзя."""
    assert FC.check_value("forfeit", "0,00") is None


# --- реквизиты (только помечаем, не чистим) ---------------------------------
def test_inn_checksum_failure_is_reported():
    """A53-9758…docx: ИНН должника побит OCR (стоит трижды, сумма не сходится)."""
    assert FC.check_value("inn", "612102429513")


def test_valid_inn_is_silent():
    assert FC.check_value("inn", "612102152288") is None


def test_ogrn_checksum_now_enforced():
    """is_valid_ogrn был написан, но не вызывался нигде — контракт его подключает."""
    assert FC.check_value("ogrn", "123454321234")


def test_multivalue_inn_kept_when_one_part_valid():
    """Многодолжниковые заявления: «ИНН1, ИНН2» — не мусор, а список."""
    assert FC.check_value("inn", "612102152288, 001023012301") is None


def test_requisites_are_flagged_but_not_cleared():
    """Решение Андрея: битый СВОЙ реквизит полезнее пустого поля."""
    fields = {"inn": "612102429513"}
    issues = FC.apply_contract(fields)
    assert fields["inn"] == "612102429513", "реквизит не должен вычищаться"
    assert [i for i in issues if i.field == "inn" and not i.cleared]


# --- адрес: позитивная грамматика -------------------------------------------
def test_address_without_any_address_marker_is_garbage():
    """«ПАО Сбер» в адресе должника — взыскание банкрот заявление.docx.

    Отсекается не потому, что «ПАО» в чёрном списке, а потому, что адресом не
    является: ни индекса, ни города, ни улицы, ни дома.
    """
    assert FC.check_value("applicantAddress", "ПАО Сбер")


@pytest.mark.parametrize("value", [
    "347561, Ростовская область, Песчанокопский р-н, с. Развильное, ул. Соляника, д. 20",
    "344068, г. Ростов-на-Дону, пр-кт Ленина, д. 5, кв. 61",
    "115114, Москва, Дербеневская наб., д. 11",
    "248030, Калужская обл., г. Калуга, ул. Труда, д. 29А",
    "a/я 15, 344000, г. Ростов-на-Дону",
])
def test_real_addresses_pass(value):
    assert FC.check_value("applicantAddress", value) is None


def test_address_with_postbox_tail_passes():
    """Хвост «а/я N» не режется (правило §K) — адрес остаётся валидным."""
    assert FC.check_value("managerAddress", "344000, г. Ростов-на-Дону, а/я 123") is None


# --- имя организации --------------------------------------------------------
def test_org_trailing_postal_index_is_cut():
    """Умерший ким клим.docx: к имени кредитора прилип индекс из адреса."""
    assert FC.clean_org_tail("ПАО Сбербанк России в лице Юго-Западного банка 344068") == \
        "ПАО Сбербанк России в лице Юго-Западного банка"


def test_fns_creditor_name_is_not_touched():
    """Анти-регрессия: «в лице Межрайонной ИФНС» — корректное имя, а не проза.

    34 документа ФНС в корпусе. Раньше мой же сканер аудита считал это мусором —
    контракт не должен повторять ту ошибку.
    """
    name = "ФНС России в лице Межрайонной ИФНС России № 26 по Ростовской области"
    assert FC.clean_org_tail(name) == name
    assert FC.check_value("creditorName", name) is None


def test_sberbank_branch_name_is_not_touched():
    """«ПАО Сбербанк в лице филиала - Юго-Западный Банк» — так и пишут в заявлении."""
    name = "ПАО Сбербанк в лице филиала - Юго-Западный Банк ПАО Сбербанк"
    assert FC.clean_org_tail(name) == name


# --- владение текстом -------------------------------------------------------
def test_cross_field_court_name_in_money_field():
    """Корень бага: один и тот же текст в courtName и в loanDebt."""
    fields = {"courtName": "Арбитражный суд Ростовской области",
              "loanDebt": "Арбитражный суд Ростовской области"}
    issues = FC.check_cross_field(fields)
    assert [i for i in issues if i.field == "loanDebt"]
    assert not [i for i in issues if i.field == "courtName"], "владелец не жертва"


def test_cross_field_creditor_name_in_debtor_address():
    """applicantAddress = «ПАО Сбер» — префикс creditorName."""
    fields = {"creditorName": "ПАО Сбербанк", "applicantAddress": "ПАО Сбер"}
    assert [i for i in FC.check_cross_field(fields) if i.field == "applicantAddress"]


def test_cross_field_ignores_identical_legit_addresses():
    """Адрес кредитора и должника могут совпасть (оба — тот же город/дом).

    Оба поля одного типа — конфликта нет: несовместимы только РАЗНЫЕ типы.
    """
    addr = "344068, г. Ростов-на-Дону, ул. Ленина, д. 5"
    assert not FC.check_cross_field({"creditorAddress": addr, "applicantAddress": addr})


def test_apply_contract_clears_victim_and_keeps_owner():
    fields = {"courtName": "Арбитражный суд Ростовской области",
              "loanDebt": "Арбитражный суд Ростовской области",
              "totalDebt": "25 000,00"}
    FC.apply_contract(fields)
    assert "loanDebt" not in fields
    assert fields["courtName"] == "Арбитражный суд Ростовской области"
    assert fields["totalDebt"] == "25 000,00"


# --- записи, строящиеся мимо fields ----------------------------------------
def test_entries_addresses_are_checked():
    """Ловушка §J.3: debtors[] строится отдельным путём, мимо fields."""
    debtors = [{"name": "Иванов Иван Иванович", "address": "ПАО Сбер"}]
    issues = FC.check_entries(debtors, "debtors")
    assert issues and debtors[0]["address"] == ""


def test_entries_keep_valid_address():
    debtors = [{"name": "Иванов Иван Иванович",
                "address": "347561, Ростовская область, с. Развильное, ул. Соляника, д. 20"}]
    assert not FC.check_entries(debtors, "debtors")
    assert debtors[0]["address"]


# --- инвариант каскада ------------------------------------------------------
def test_find_issues_does_not_mutate():
    """Чекпоинт обязан быть наблюдателем: правит только apply_contract."""
    fields = {"courtName": "Арбитражный суд Ростовской области",
              "loanDebt": "Арбитражный суд Ростовской области"}
    before = dict(fields)
    assert FC.find_issues(fields)
    assert fields == before


def test_find_issues_silent_on_clean_fields():
    fields = {"courtName": "Арбитражный суд Ростовской области", "loanDebt": "25 000,00",
              "creditorName": "ПАО Сбербанк", "inn": "612102152288"}
    assert not FC.find_issues(fields)


def test_unknown_field_is_never_touched():
    """Поля вне реестра не проверяем: молчать безопаснее, чем чистить непонятое."""
    assert FC.check_value("someFutureField", "что угодно") is None


def test_checkpoint_raises_only_in_strict_mode():
    """В проде чекпоинт лишь пишет в лог: ронять разбор из-за одного поля нельзя.

    В строгом режиме (SBERACT_STRICT_CONTRACT=1) — падает, показывая ШАГ каскада,
    на котором словарь испортился. Зовём метод несвязанным, чтобы не поднимать
    spaCy-модель ради проверки трёх строк.
    """
    import types

    from document_analyzer import DocumentAnalyzer

    dirty = {"courtName": "Арбитражный суд Ростовской области",
             "loanDebt": "Арбитражный суд Ростовской области"}

    DocumentAnalyzer._contract_checkpoint(
        types.SimpleNamespace(_STRICT_CONTRACT=False), dirty, "шаг")  # молчит

    with pytest.raises(AssertionError, match="финансовый каскад"):
        DocumentAnalyzer._contract_checkpoint(
            types.SimpleNamespace(_STRICT_CONTRACT=True), dirty, "финансовый каскад")


def test_checkpoint_silent_on_clean_fields_even_in_strict_mode():
    import types

    from document_analyzer import DocumentAnalyzer

    clean = {"courtName": "Арбитражный суд Ростовской области", "loanDebt": "25 000,00"}
    DocumentAnalyzer._contract_checkpoint(
        types.SimpleNamespace(_STRICT_CONTRACT=True), clean, "шаг")
