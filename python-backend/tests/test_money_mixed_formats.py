"""Денежные форматы, границы финансовых записей и календарные даты."""

from decimal import Decimal
from pathlib import Path

import pytest

from document_analyzer import DocumentAnalyzer
from money_utils import canonical_money_text, decimal_amount


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("7,602.65 ₽ руб.", "7602.65"),
        ("1,234,567.89 руб.", "1234567.89"),
        ("1.234.567,89 руб.", "1234567.89"),
        ("7 602,65", "7602.65"),
        ("7\u00a0602,65", "7602.65"),
        ("7\u202f602.65", "7602.65"),
        ("7602.65", "7602.65"),
        ("7602,65", "7602.65"),
        ("2000", "2000"),
        ("0.00 ₽ руб.", "0"),
        ("7,602.6", "7602.6"),
    ],
)
def test_complete_money_value(analyzer, raw, expected):
    assert decimal_amount(raw) == Decimal(expected)
    assert decimal_amount(analyzer.normalize_amount_value(raw)) == Decimal(expected)


@pytest.mark.parametrize(
    "raw",
    [
        "29.08.1986",
        "31,12,2026",
        "А53-3432/2026",
        "221 487,12 446 340,73",
        "12,34,567.89",
        "7,602.654",
        "31.02.2026",
        "ст. 213.24",
        "",
    ],
)
def test_dates_and_malformed_numbers_are_not_money(raw):
    assert decimal_amount(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("7,602.65 ₽ руб.", "7 602,65 руб."),
        ("1.234.567,89 руб.", "1 234 567,89 руб."),
        ("7602.65 ₽ рублей", "7602.65 руб."),
        ("дата 29.08.1986; договор № 7,602.65", "дата 29.08.1986; договор № 7,602.65"),
    ],
)
def test_working_text_normalization_is_bounded_and_idempotent(raw, expected):
    assert canonical_money_text(raw) == expected
    assert canonical_money_text(expected) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("7,602.65 ₽ руб.", "7,602.65"),
        ("7 602,65 5 289,51", "7 602,65"),
        ("29.08.1986", ""),
        ("31,12,2026", ""),
    ],
)
def test_money_token_does_not_take_date_or_neighbour(analyzer, raw, expected):
    assert analyzer.money_token_from_capture(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("29.02.2024", "29.02.2024"),
        ("2024-02-29", "29.02.2024"),
        ("29 февраля 2024", "29.02.2024"),
        ("29.02.2023", None),
        ("31.04.2026", None),
        ("2026-02-31", None),
        ("31 апреля 2026", None),
        ("12,12,2026.00", None),
        ("7,602.65 ₽ руб.", None),
    ],
)
def test_calendar_date_validation(analyzer, raw, expected):
    assert analyzer._normalize_obl_date(raw) == expected


PRAYER = (
    "ПРОСИТ: Включить в реестр требования на сумму составляет 12,892.16 ₽ руб., "
    "из которой: сумма основного долга 7,602.65 ₽ руб., "
    "сумма долга по процентам 5,289.51 ₽ руб., сумма долга по пени 0.00 ₽ руб., "
    "расходы по оплате госпошлины 2000,00 руб, ИТОГО 14892,16 руб."
)


@pytest.mark.parametrize("separator", [", ", ";\n"])
def test_category_precedes_its_amount_in_same_paragraph(analyzer, separator):
    text = canonical_money_text(PRAYER.replace(", сумма", separator + "сумма"))
    fields = {"loanDebt": "8,99"}
    assert analyzer._apply_prayer_finances(fields, text)
    assert fields["principalDebt"] == "7 602,65"
    assert fields["interest"] == "5 289,51"
    assert fields["forfeit"] == "0,00"
    assert fields["loanStateDuty17"] == "2 000,00"
    assert fields["totalDebt"] == "14 892,16"


def test_explicit_prayer_outranks_body_calculation(analyzer):
    body = "Задолженность составляет 12892,16 руб., из которой: основной долг 7602,65 руб., проценты 5289,51 руб.\n"
    fields = {}
    assert analyzer._apply_prayer_finances(fields, canonical_money_text(body + PRAYER))
    assert fields["totalDebt"] == "14 892,16"
    assert fields["loanStateDuty17"] == "2 000,00"


def test_real_requirement_finances_and_dates(analyzer):
    source = Path("C:/Users/padal/Desktop/trebovanie 2956947_2.docx")
    if not source.exists():
        pytest.skip("Исходное требование доступно локально")
    result = analyzer.analyze(str(source))
    fields = result["fields"]
    assert fields["principalDebt"] == "7 602,65"
    assert fields["interest"] == fields["interest14"] == "5 289,51"
    assert fields["forfeit"] == fields["forfeit15"] == "0,00"
    assert fields["loanStateDuty17"] == "2 000,00"
    assert fields["totalDebt"] == "14 892,16"
    assert not fields.get("stateDuty16")
    assert fields["birthDate"] == "29.08.1986"
    assert fields["contractDate"] == "04.11.2021"
    assert fields["courtDecisionDate"] == "05.08.2026"
    assert "7,602.65" in result["rawText"]


@pytest.mark.parametrize(
    "pattern,total",
    [
        ("АГЕЕВ*.docx", "5 825 199,47"),
        ("ДДУ.docx", "5 199 989,94"),
    ],
)
def test_civil_mortgage_keeps_debt_separate_from_duty(analyzer, pattern, total):
    folder = Path("Заявления/НОвая конвертация/Ипотека")
    files = list(folder.glob(pattern))
    if not files:
        pytest.skip("Корпус ипотечных заявлений недоступен")
    fields = analyzer.analyze(str(files[0]))["fields"]
    assert fields["totalDebt"] == total
    assert not fields.get("loanStateDuty17")


@pytest.mark.parametrize(
    "raw",
    [
        "2026-02-28.00",
        "29.02.20240",
        "29 февраля 20240",
    ],
)
def test_date_does_not_accept_numeric_suffix(analyzer, raw):
    assert analyzer._normalize_obl_date(raw) is None
