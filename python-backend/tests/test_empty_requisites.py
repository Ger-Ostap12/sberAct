"""Отсутствующие реквизиты удаляются вместе с подписью, без потери соседних данных."""

from copy import deepcopy

import pytest
from docx import Document

from document_generator import DocumentGenerator
from empty_requisites import clean_requisite_text, remove_empty_requisites


@pytest.mark.parametrize(
    "text,missing,expected",
    [
        ("ООО (ОГРН [990], ИНН [991]) обратилось.", {"[990]", "[991]"}, "ООО обратилось."),
        ("ООО (ОГРН [990], ИНН [991])", {"[990]"}, "ООО (ИНН [991])"),
        ("ООО (ИНН [991], ОГРН [990])", {"[990]"}, "ООО (ИНН [991])"),
        ("ООО (ОГРН [990], ИНН [991], адрес [988])", {"[990]", "[991]"}, "ООО (адрес [988])"),
        ("Должник ([3] года рождения, ИНН [4])", {"[3]", "[4]"}, "Должник"),
        ("Должник (дата рождения: [3],ИНН[4], ОГРНИП [4.1])", {"[3]", "[4]", "[4.1]"}, "Должник"),
        ("Должник (ОГРН [3], ИНН [4])", {"[3]"}, "Должник (ИНН [4])"),
        ("Должник, ИНН [4], адрес [6].", {"[4]"}, "Должник, адрес [6]."),
        ("Управляющий (ИНН [41]).", {"[41]"}, "Управляющий."),
        ("Должник, ИНН [4]; кредитор, ИНН [991].", {"[4]"}, "Должник; кредитор, ИНН [991]."),
        (
            "Необходимы ИНН и паспорт. Договор [110] от [100]. ******",
            set(),
            "Необходимы ИНН и паспорт. Договор [110] от [100]. ******",
        ),
    ],
)
def test_bound_component_removal(text, missing, expected):
    assert clean_requisite_text(text, missing) == expected


@pytest.mark.parametrize(
    "text,missing,expected",
    [
        ("ФИО (серия и номер документа, удостоверяющего личность [1407.1] [1408.1])", {"[1407.1]", "[1408.1]"}, "ФИО"),
        ("ФИО (паспорт гражданина РФ серия [1407.1] номер [1408.1])", {"[1407.1]", "[1408.1]"}, "ФИО"),
        (
            "ФИО (серия и номер документа, удостоверяющего личность [1407.1] [1408.1])",
            {"[1408.1]"},
            "ФИО (серия документа, удостоверяющего личность [1407.1])",
        ),
        (
            "ФИО (серия и номер документа, удостоверяющего личность [1407.1] [1408.1])",
            {"[1407.1]"},
            "ФИО (номер документа, удостоверяющего личность [1408.1])",
        ),
        (
            "ФИО (паспорт гражданина РФ серия [1407.1] номер [1408.1], выдан ******, ******, код подразделения ******, адрес [6])",
            {"[1407.1]", "[1408.1]"},
            "ФИО (адрес [6])",
        ),
    ],
)
def test_passport_components(text, missing, expected):
    assert clean_requisite_text(text, missing) == expected


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


def test_roles_use_independent_values(generator):
    doc = Document()
    p = doc.add_paragraph("Должник (ИНН [4]); кредитор (ИНН [991]).")
    remove_empty_requisites(doc, {"creditorInn": "1234567890"}, generator._base_field_mapping(), generator)
    assert p.text == "Должник; кредитор (ИНН [991])."


@pytest.mark.parametrize("where", ["body", "table", "header", "footer", "nested_table"])
def test_document_parts_and_split_runs(generator, where):
    doc = Document()
    if where == "body":
        p = doc.add_paragraph()
    elif where == "table":
        p = doc.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
    elif where == "nested_table":
        p = doc.add_table(rows=1, cols=1).cell(0, 0).add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
    else:
        p = getattr(doc.sections[0], where).paragraphs[0]
    p.add_run("Начало").bold = True
    p.add_run(" (ОГ")
    p.add_run("РН [99").italic = True
    p.add_run("0], ИНН [991])")
    p.add_run(" конец").underline = True
    remove_empty_requisites(doc, {}, generator._base_field_mapping(), generator)
    assert generator._paragraph_text(p) == "Начало конец"
    assert p.runs[0].bold
    assert p.runs[-1].underline


def test_filled_requisites_are_byte_identical(generator):
    doc = Document()
    p = doc.add_paragraph("ИНН [4], ОГРН [990], паспорт серия [1407.1] номер [1408.1]")
    before = doc.element.xml
    data = {
        "inn": "123456789012",
        "creditorOgrn": "1234567890123",
        "mortgageRespPassSer1407_1": "6001",
        "mortgageRespPassNum1408_1": "123456",
    }
    original = deepcopy(data)
    remove_empty_requisites(doc, data, generator._base_field_mapping(), generator)
    assert doc.element.xml == before
    assert data == original


@pytest.mark.parametrize("entity", ["individual", "legal", "ip"])
def test_full_generator_removes_identifiers(generator, entity):
    doc = Document()
    doc.add_paragraph("ознакомившись с заявлением [989] (ОГРН [990], ИНН [991]) к [2] (ИНН [4]).")
    data = {
        "entityType": entity,
        "sourceDocumentType": "rtk_application",
        "applicantName": "Иванов Иван Иванович",
        "creditorName": "ООО «Пример»",
        "judge": "Иванова И.И.",
        "date": "03.11.2026",
        "caseNumber": "А53-1/2026",
    }
    generator.replace_document_data(doc, data)
    text = doc.paragraphs[0].text
    assert "ИНН" not in text and "ОГРН" not in text and "******" not in text
    assert "ООО" in text and "Иванов" in text


def test_unrelated_required_markers_remain_manual(generator):
    doc = Document()
    doc.add_paragraph("Кредитор [989] (ИНН [991]); срок [18].")
    generator.replace_document_data(doc, {"creditorName": "ООО «Пример»", "sourceDocumentType": "rtk_application"})
    assert "ИНН" not in doc.paragraphs[0].text
    assert "******" in doc.paragraphs[0].text


def test_legacy_ogrnip_marker_does_not_use_birth_date(generator):
    doc = Document()
    p = doc.add_paragraph("Должник ([3] года рождения, ОГРНИП [3], ИНН [4])")
    remove_empty_requisites(
        doc, {"birthDate": "01.01.1980", "inn": "123456789012"}, generator._base_field_mapping(), generator
    )
    assert p.text == "Должник ([3] года рождения, ИНН [4])"


@pytest.mark.parametrize(
    "text",
    [
        "ФИО ([3] г. рождения)",
        "ФИО (д. р. [3])",
        "ФИО ([3] г.р.)",
        "ФИО (паспорт: серия: [1407.1], номер: [1408.1])",
        "ФИО (паспорт гражданина Российской Федерации серия [1407.1] № [1408.1])",
    ],
)
def test_common_abbreviations_and_passport_punctuation(text):
    assert clean_requisite_text(text, {"[3]", "[1407.1]", "[1408.1]"}) == "ФИО"


@pytest.mark.parametrize(
    "text,missing,expected",
    [
        ("Кредитор (идентификационный номер налогоплательщика [991])", {"[991]"}, "Кредитор"),
        ("Должник (основной государственный регистрационный номер [3])", {"[3]"}, "Должник"),
        ("ФИО (паспорт серия [1407.1] № [1408.1])", {"[1408.1]"}, "ФИО (паспорт серия [1407.1])"),
    ],
)
def test_full_identifier_labels_and_partial_passport_number(text, missing, expected):
    assert clean_requisite_text(text, missing) == expected
