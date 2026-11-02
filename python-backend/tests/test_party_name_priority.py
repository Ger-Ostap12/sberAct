"""Регрессии выбора имени стороны и многострочного названия кредитора."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from document_analyzer import DocumentAnalyzer
from fio_detector import explicit_debtor_name, is_person_name
from party_name_parser import explicit_creditor_name


@pytest.mark.parametrize(
    "name",
    [
        "Ароян Ваче Рушани",
        "Хантемерьян Евгений Александрович",
        "Петрова Мария (Кулемзина) Сергеевна",
        "Иванов Иван Иванович",
    ],
)
def test_person_names_remain_valid(name):
    assert is_person_name(name)


@pytest.mark.parametrize(
    "text",
    [
        "ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ПРОФЕССИОНАЛЬНАЯ",
        "ПРОФЕССИОНАЛЬНАЯ КОЛЛЕКТОРСКАЯ ОРГАНИЗАЦИЯ",
        "ОБЩЕСТВО ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ",
    ],
)
def test_business_prose_is_not_person(text):
    assert not is_person_name(text)


@pytest.mark.parametrize("label", ["Должник", "Ответчик", "Должник (ответчик)", "Заемщик"])
@pytest.mark.parametrize("separator", [" ", "\n", "\r\n", "\n\n"])
def test_explicit_debtor_replaces_other_role(label, separator):
    text = (
        "Представитель кредитора: Петров Петр Петрович\n"
        f"{label}:{separator}Иванов Иван Иванович (ИНН 123456789012)\n"
        "Финансовый управляющий: Сидоров Сидор Сидорович"
    )
    fields = {
        "applicantName": "Петров Петр Петрович",
        "debtorName": "Петров Петр Петрович",
        "applicantNameGenitive": "Петрова Петра Петровича",
    }
    DocumentAnalyzer()._fix_debtor_name(text, fields)
    assert fields["applicantName"] == fields["debtorName"] == "Иванов Иван Иванович"
    assert fields["applicantNameGenitive"] == "Иванова Ивана Ивановича"


@pytest.mark.parametrize(
    "text",
    [
        "Должник:\nПредставитель: Петров Петр Петрович",
        "Должник:\nКредитор:\nИванов Иван Иванович",
        "По договору должник: Иванов Иван Иванович",
        "Должник: ООО «Пример»",
        "Должник: Иванов Иван Иванович\nПетров Петр Петрович",
        "Должник: Иванов Иван Иванович\nДолжник: Петров Петр Петрович",
    ],
)
def test_ambiguous_or_empty_headers_are_not_authoritative(text):
    assert explicit_debtor_name(text) is None


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\n\n", "\n \t"])
def test_creditor_legal_form_on_separate_line(separator):
    text = (
        "Кредитор:\nОбщество с ограниченной ответственностью"
        f"{separator}«Профессиональная коллекторская организация «Пример» "
        "(сокращенно наименование ООО ПКО «Пример») ИНН: 1234567890\n"
        "Адрес: г. Москва\nДолжник: Иванов Иван Иванович"
    )
    candidate = explicit_creditor_name(text)
    assert candidate.name == "ООО ПКО «Пример»"
    fields = {"creditorName": "Общество с ограниченной ответственностью"}
    DocumentAnalyzer()._fix_truncated_creditor_name(fields, text)
    assert fields["creditorName"] == candidate.name


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Истец: ПАО «Тест-\nБанк»\nИНН 1234567890", "ПАО «Тест-Банк»"),
        ("Кредитор: ООО\n«Пример»\nАдрес для корреспонденции: Москва", "ООО «Пример»"),
        ("Кредитор: ПАО «Первый»\nПредставитель: Иванов Иван Иванович", "ПАО «Первый»"),
        ("Кредитор:\nДолжник: ООО «Другой»", None),
        ("Кредитор: Общество с ограниченной ответственностью\nИНН 1234567890", None),
        ("Кредитор:\nПредставитель взыскателя по доверенности:\nООО «Другой»", None),
    ],
)
def test_creditor_boundaries(text, expected):
    candidate = explicit_creditor_name(text)
    assert (candidate.name if candidate else None) == expected


def test_unrelated_trusted_creditor_is_preserved():
    fields = {"creditorName": "ПАО «Первый»"}
    DocumentAnalyzer()._fix_truncated_creditor_name(fields, "Кредитор: ООО «Другой»")
    assert fields["creditorName"] == "ПАО «Первый»"


def test_real_requirement_parties():
    source = Path("C:/Users/padal/Desktop/trebovanie 2956947_2.docx")
    if not source.exists():
        pytest.skip("Исходное требование доступно только локально")
    result = DocumentAnalyzer().analyze(str(source))
    fields = result["fields"]
    assert fields["debtorName"] == fields["applicantName"] == "Хантемерьян Евгений Александрович"
    assert result["debtors"][0]["name"] == fields["debtorName"]
    assert fields["creditorName"] == "ООО ПКО «АйДи Коллект»"
    assert fields["applicantNameGenitive"] == "Хантемерьяна Евгения Александровича"


@pytest.mark.parametrize("name", ["Елены Васильевны", "Воробьева Светлана Михайловна На"])
def test_incomplete_or_extended_person_line_not_high_confidence(name):
    assert explicit_debtor_name(f"Должник: {name}\nИНН 123456789012") is None


def test_preserve_original_name_capitalization():
    fields = {"applicantName": "ИВАНОВ ИВАН ИВАНОВИЧ", "debtorName": "ИВАНОВ ИВАН ИВАНОВИЧ"}
    DocumentAnalyzer()._fix_debtor_name("Должник: ИВАНОВ ИВАН ИВАНОВИЧ", fields)
    assert fields["applicantName"] == "ИВАНОВ ИВАН ИВАНОВИЧ"


def test_full_legal_form_in_parentheses_is_preserved():
    candidate = explicit_creditor_name("Кредитор: ББР Банк (акционерное общество)\nИНН 1234567890")
    assert candidate.name == "ББР Банк (акционерное общество)"


def test_director_does_not_become_part_of_creditor_name():
    candidate = explicit_creditor_name(
        'Кредитор: ООО "Профессиональная\nколлекторская организация Пример"\nГенеральный директор: Иванов Иван Иванович'
    )
    assert candidate.name == 'ООО "Профессиональная коллекторская организация Пример"'


@pytest.mark.parametrize(
    "tail",
    [
        "\nпроспект Мира, д. 18, Москва",
        " (ИНН 1234567890)",
        "\n123456, г. Москва",
    ],
)
def test_address_and_requisites_do_not_extend_quoted_name(tail):
    candidate = explicit_creditor_name('Кредитор: ПАО "Пример"' + tail)
    assert candidate.name == 'ПАО "Пример"'


@pytest.mark.parametrize("line", ["Елены Васильевны", "Воробьева Светлана Михайловна На"])
def test_valid_debtor_field_outranks_weak_fallback_when_applicant_is_creditor(line):
    fields = {
        "applicantName": "ФНС России",
        "debtorName": "Бузнякова Елена Васильевна",
        "creditorName": "ФНС России",
    }
    DocumentAnalyzer()._fix_debtor_name(f"Должник: {line}", fields)
    assert fields["debtorName"] == fields["applicantName"] == "Бузнякова Елена Васильевна"


def test_multiple_inline_debtors_do_not_collapse_to_first():
    text = "Должник: Иванов Иван Иванович (ИНН 123456789012)\nПетров Петр Петрович (ИНН 123456789013)"
    assert explicit_debtor_name(text) is None
