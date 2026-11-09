"""Публикации и подача заявления: источники, числа, даты и реальные шаблоны."""
import re
from copy import deepcopy
from zipfile import ZipFile

import pytest
from docx import Document
from lxml import etree

from document_analyzer import DocumentAnalyzer
from document_generator import DocumentGenerator
from publication_fields import apply_filing_dates, apply_publication_fields


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


@pytest.fixture(scope="module")
def gen():
    return DocumentGenerator()


HEADER = "Арбитражный суд Ростовской области\nЗаявитель: ПАО Сбербанк\nДолжник: Иванов Иван Иванович\nЗаявление о включении в реестр требований кредиторов\n"


@pytest.mark.parametrize("text", [
    "На сайте ЕФРСБ опубликовано сообщение № 998877665 от 12.08.2026.",
    "ЕФРСБ № 998877665 от 12.08.2026.",
    "Сообщением на ЕФРСБ № 998877665 от 12.08.2026 опубликованы сведения.",
    "ЕФРСБ сообщение 12.08.2026 (сообщение № 998877665).",
    "ЕФРСБ имеется сообщение № 998877665 от 12.08.2026.",
    "Сообщение № 998877665 от 12.08.2026 опубликовано на сайте ЕФРСБ.",
    "ЕФРСБ - сообщение № 998877665 от 12,08,2026.",
    "Единый федеральный реестр сведений о банкротстве № 998877665 от 12.08.2026.",
])
def test_efrsb_number_and_date_from_real_wordings(analyzer, text):
    fields = analyzer.analyze_from_text(HEADER + text)["fields"]
    assert fields.get("messageNumber") == "998877665"
    assert fields.get("efirsbPublicationDate") == "12.08.2026"


@pytest.mark.parametrize("text", [
    'В газете «Коммерсантъ» № 321 от 14.08.2026 опубликованы сведения.',
    'В газете "Коммерсант" № 321 от 14,08,2026 опубликованы сведения.',
    'Сведения опубликованы 14.08.2026 в газете «Коммерсантъ» № 321.',
    'Коммерсантъ № 321 (12345) от 14.08.2026.',
])
def test_kommersant_number_and_date(analyzer, text):
    fields = analyzer.analyze_from_text(HEADER + text)["fields"]
    assert fields.get("kommersantNumber") == "321"
    assert fields.get("kommersantDate") == "14.08.2026"


@pytest.mark.parametrize("text", [
    'ЕФРСБ № 998877665 от 12.08.2026; Коммерсантъ № 321 от 14.08.2026.',
    'Коммерсантъ № 321 от 14.08.2026. ЕФРСБ № 998877665 от 12.08.2026.',
])
def test_sources_never_exchange_numbers_or_dates(analyzer, text):
    fields = analyzer.analyze_from_text(HEADER + text)["fields"]
    assert {k: fields[k] for k in ("messageNumber", "efirsbPublicationDate", "kommersantNumber", "kommersantDate")} == {
        "messageNumber": "998877665", "efirsbPublicationDate": "12.08.2026",
        "kommersantNumber": "321", "kommersantDate": "14.08.2026",
    }


@pytest.mark.parametrize("source", ["ЕФРСБ", "Коммерсантъ"])
@pytest.mark.parametrize("ending", [
    '. Договор заключен 12.08.2026 № 123.',
    ' согласно Закону от 26.10.2002 № 127-ФЗ.',
    '. Заявление направлено в суд 15.08.2026 посредством сервиса «Мой Арбитр».',
])
def test_publications_do_not_take_contract_law_or_filing_date(source, ending):
    fields = {}
    apply_publication_fields(fields, source + ending)
    assert not fields


@pytest.mark.parametrize("text,expected", [
    ('12.08.2026 (согласно штампу канцелярии); 14.08.2026 посредством сервиса электронной подачи документов «Мой Арбитр»',
     {"applicationReceiptDate23": "12.08.2026", "courtSubmissionDate24": "14.08.2026"}),
    ('Заявление поступило в суд 12.08.2026. Заявление направлено в суд 14.08.2026 через сервис «Мой Арбитр».',
     {"applicationReceiptDate23": "12.08.2026", "courtSubmissionDate24": "14.08.2026"}),
    ('Дата поступления заявления в суд: 12.08.2026. Дата направления в суд: 14.08.2026.',
     {"applicationReceiptDate23": "12.08.2026", "courtSubmissionDate24": "14.08.2026"}),
    ('Через сервис «Мой Арбитр» заявление подано 14.08.2026.', {"courtSubmissionDate24": "14.08.2026"}),
    ('[23] 12.08.2026 [24] 14.08.2026', {"applicationReceiptDate23": "12.08.2026", "courtSubmissionDate24": "14.08.2026"}),
])
def test_filing_dates_keep_separate_meanings(analyzer, text, expected):
    fields = analyzer.analyze_from_text(HEADER + text)["fields"]
    assert {key: fields.get(key) for key in expected} == expected


def test_mention_of_my_arbitr_does_not_steal_publication_date():
    fields = {}
    apply_filing_dates(fields, 'Заявление подано через «Мой Арбитр». ЕФРСБ № 998877665 от 12.08.2026.')
    assert not fields


@pytest.mark.parametrize("source", ["efrsb", "kommersant", "both"])
@pytest.mark.parametrize("template", [
    'Сведения опубликованы на сайте ЕФРСБ сообщение [11] (сообщение № [9]).',
    'Сведения опубликованы в газете «Коммерсантъ» [67] от [68].',
    'Сведения опубликованы [на сайте ЕФРСБ №[9] от [11]] в газете «Коммерсантъ» №[67] от [68].',
])
def test_publication_rendering_and_fallback_preserve_whole_dates(gen, source, template):
    doc = Document()
    paragraph = doc.add_paragraph()
    for char in template:
        paragraph.add_run(char)
    data = {"entityType": "individual", "obligations": []}
    if source in ("efrsb", "both"):
        data.update(messageNumber="998877665", efirsbPublicationDate="12.08.2026")
    if source in ("kommersant", "both"):
        data.update(kommersantNumber="321", kommersantDate="14.08.2026")
    gen.replace_document_data(doc, data)
    text = paragraph.text
    if source == "efrsb" or (source == "both" and "[67]" not in template):
        assert "998877665" in text and "12.08.2026" in text
        assert "ЕФРСБ" in text
    else:
        assert "321" in text and "14.08.2026" in text
        assert "Коммерсантъ" in text
    assert not re.search(r"\[(?:9|11|67|68)\]", text)


def test_receipt_and_submission_markers_are_not_interchanged(gen):
    doc = Document()
    paragraph = doc.add_paragraph('[23] (согласно штампу канцелярии); [24] посредством сервиса электронной подачи документов «Мой Арбитр».')
    gen.replace_document_data(doc, {"applicationReceiptDate23": "2026-08-12", "courtSubmissionDate24": "2026-08-14"})
    assert paragraph.text.startswith('12.08.2026 (согласно штампу канцелярии); 14.08.2026 посредством')


@pytest.mark.parametrize("field,text", [
    ("courtSubmissionDate24", "Дата направления в суд не указана. Договор от 12.08.2026."),
    ("applicationReceiptDate23", "Дата поступления заявления в суд не указана. Публикация от 12.08.2026."),
    ("courtSubmissionDate24", "[24] 33.13.2026"),
])
def test_filing_dates_clear_legacy_guesses(field, text):
    fields = {field: "12.08.2026"}
    apply_filing_dates(fields, text)
    assert field not in fields


def test_all_four_dates_in_one_statement_are_not_interchanged(analyzer):
    text = HEADER + (
        'ЕФРСБ № 998877665 от 12.08.2026. Коммерсантъ № 321 от 14.08.2026. '
        '15.08.2026 (согласно штампу канцелярии); '
        '16.08.2026 посредством сервиса электронной подачи документов «Мой Арбитр».'
    )
    fields = analyzer.analyze_from_text(text)["fields"]
    assert fields["efirsbPublicationDate"] == "12.08.2026"
    assert fields["kommersantDate"] == "14.08.2026"
    assert fields["applicationReceiptDate23"] == "15.08.2026"
    assert fields["courtSubmissionDate24"] == "16.08.2026"


@pytest.mark.parametrize("text", [
    '14.08.2026 в 17:20:10 посредством сервиса электронной подачи документов «Мой Арбитр».',
    'Посредством сервиса электронной подачи документов «Мой Арбитр» 14.08.2026 подано заявление.',
])
def test_my_arbitr_accepts_timestamp_and_long_service_name(analyzer, text):
    fields = analyzer.analyze_from_text(HEADER + text)["fields"]
    assert fields.get("courtSubmissionDate24") == "14.08.2026"


def test_all_publication_templates_use_field_markers_not_literal_blanks(gen):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    publication = re.compile(r"ЕФРСБ|Един\w*\s+федеральн\w*\s+реестр\w*\s+сведени\w*\s+о\s+банкротств|Коммерсант", re.I)
    checked = 0
    for path in gen._templates_root().rglob("*.docx"):
        if path.name.startswith("~$"):
            continue
        with ZipFile(path) as archive:
            for part in archive.namelist():
                if not re.match(r"word/(?:document|header\d*|footer\d*|footnotes|endnotes)\.xml$", part):
                    continue
                xml = etree.fromstring(archive.read(part))
                for paragraph in xml.xpath("//w:p", namespaces=ns):
                    text = "".join(paragraph.xpath(".//w:t/text()", namespaces=ns))
                    if not publication.search(text) or not re.search("опубликован", text, re.I):
                        continue
                    checked += 1
                    assert not re.search(r"[*＊✱_]|\b(?:ДД|ММ|ГГГГ)\b", text), (path, text)
                    markers = set(re.findall(r"\[(9|11|67|68|5557|5558)\]", text))
                    if "Коммерсант" in text:
                        assert {"67", "68"} <= markers, (path, text)
                    if "ЕФРСБ" in text:
                        assert {"9", "11"} <= markers or {"5557", "5558"} <= markers, (path, text)
    assert checked > 0


@pytest.mark.parametrize("text,expected", [
    ('В арбитражный суд 12.08.2026 поступило (посредством сервиса подачи документов в электронном виде «Мой арбитр») заявление кредитора.', {"applicationReceiptDate23": "12.08.2026"}),
    ('Заявление направлено в суд посредством системы Мой арбитр 14.08.2026, поступило в суд 15.08.2026.', {"courtSubmissionDate24": "14.08.2026", "applicationReceiptDate23": "15.08.2026"}),
])
def test_filing_dates_in_full_act_word_order(text, expected):
    fields = {}
    apply_filing_dates(fields, text)
    assert fields == expected


def test_real_filing_paragraphs_use_submission_and_receipt_not_current_date(gen):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    checked = 0
    for path in gen._templates_root().rglob("*.docx"):
        if path.name.startswith("~$"):
            continue
        with ZipFile(path) as archive:
            xml = etree.fromstring(archive.read("word/document.xml"))
        for original in xml.xpath("//w:p", namespaces=ns):
            text = "".join(original.xpath(".//w:t/text()", namespaces=ns))
            if not re.search(r"Мой\s+Арбитр", text, re.I):
                continue
            assert not re.search(r'Мой\s+Арбитр[»"]?\s*\[777\]|\[(?:777|554)\]\s+поступило', text, re.I), (path, text)
            if not re.search(r'Мой\s+Арбитр[»"]?\s*\[24\]|\[23\]\s+поступило', text, re.I):
                continue
            doc = Document()
            doc._element.body.insert(0, deepcopy(original))
            gen.replace_document_data(doc, {
                "applicationReceiptDate23": "2026-08-15",
                "courtSubmissionDate24": "2026-08-14",
                "currentDate": "2026-01-01",
                "cpCaseDate": "2026-01-02",
            })
            rendered = doc.paragraphs[0].text
            assert "15.08.2026" in rendered, (path, rendered)
            if "[24]" in text:
                assert "14.08.2026" in rendered, (path, rendered)
            assert "01.01.2026" not in rendered and "02.01.2026" not in rendered, (path, rendered)
            checked += 1
    assert checked > 0


def test_kommersant_message_is_not_also_an_efrsb_message(analyzer):
    fields = analyzer.analyze_from_text(HEADER + 'В газете «Коммерсантъ» опубликовано сообщение № 321 от 14.08.2026.')["fields"]
    assert fields.get("kommersantNumber") == "321"
    assert fields.get("kommersantDate") == "14.08.2026"
    assert not fields.get("messageNumber")
    assert not fields.get("efirsbPublicationDate")


@pytest.mark.parametrize("actor,expected", [("ББР Банк", None), ("Экспобанк", "01.04.2026")])
def test_my_arbitr_date_belongs_to_current_creditor(actor, expected):
    fields = {"creditorName": 'АО «Экспобанк»'}
    apply_filing_dates(fields, f'01.04.2026 посредством сервиса электронной подачи документов «Мой Арбитр» АО «{actor}» обратилось в суд с заявлением.')
    assert fields.get("courtSubmissionDate24") == expected


def test_submission_to_bank_is_not_submission_to_court():
    fields = {}
    apply_filing_dates(fields, 'Заявление подано 12.08.2026 в банк. Заявление поступило 13.08.2026 в банк.')
    assert not fields
