"""Две госпошлины в акте принятия удаляются независимо, без подмены сумм."""
import re

import pytest
from docx import Document

from document_generator import DocumentGenerator


@pytest.fixture(scope="module")
def gen():
    return DocumentGenerator()


TEXT = ("Начало. [15] руб. – неустойка; [17] – государственная пошлина, "
        "о взыскании с должника государственной пошлины в размере [16] руб.")


def fill(gen, loan, bankruptcy, split=False):
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Заголовок. ").bold = True
    for part in (list(TEXT) if split else [TEXT]):
        paragraph.add_run(part)
    gen.replace_document_data(doc, {
        "entityType": "individual", "obligations": [], "forfeit15": "50",
        "loanStateDuty17": loan, "stateDuty16": bankruptcy,
    })
    text = re.sub(r"\s+", " ", paragraph.text).strip()
    return doc, text


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("loan,bankruptcy,ending", [
    ("100", "200", "100 – государственная пошлина, о взыскании с должника государственной пошлины в размере 200 руб."),
    ("100", "", "100 – государственная пошлина."),
    ("", "200", "взыскание с должника государственной пошлины в размере 200 руб."),
    ("", "", None),
])
def test_independent_clauses(gen, split, loan, bankruptcy, ending):
    doc, text = fill(gen, loan, bankruptcy, split)
    prefix = "Заголовок. Начало. 50 руб. – неустойка"
    assert text == prefix + ("; " + ending if ending else ".")
    assert "[16]" not in text and "[17]" not in text


@pytest.mark.parametrize("zero", [None, "", 0, "0", "0,00", "0.00", "0 руб.", "не указано"])
@pytest.mark.parametrize("empty_field", ["loan", "bankruptcy"])
def test_zero_is_absent_and_never_copied_from_other_duty(gen, zero, empty_field):
    loan, bankruptcy = (zero, "200") if empty_field == "loan" else ("100", zero)
    _, text = fill(gen, loan, bankruptcy)
    if empty_field == "loan":
        assert "200 руб." in text
        assert "– государственная пошлина" not in text
        assert "; взыскание с должника" in text
    else:
        assert "100 – государственная пошлина." in text
        assert "взыскан" not in text


def test_both_zero_remove_both_clauses(gen):
    _, text = fill(gen, "0,00", "0,00")
    assert text.endswith("50 руб. – неустойка.")
    assert "пошлин" not in text


@pytest.mark.parametrize("empty", [{"16"}, {"17"}, {"16", "17"}])
def test_clause_removal_preserves_surviving_run_formatting(gen, empty):
    doc = Document()
    paragraph = doc.add_paragraph()
    prefix = paragraph.add_run("Начало; ")
    prefix.bold = True
    loan = paragraph.add_run("[17] – государственная пошлина")
    loan.italic = True
    paragraph.add_run(", о взыскании с должника государственной пошлины в размере ")
    bank = paragraph.add_run("[16] руб.")
    bank.underline = True
    gen._remove_combined_duty_clauses([paragraph], empty)
    assert prefix.bold
    assert prefix.text.startswith("Начало")
    if "17" not in empty:
        assert "[17]" in loan.text and loan.italic
    if "16" not in empty:
        assert "[16]" in bank.text and bank.underline


@pytest.mark.parametrize("loan,bankruptcy", [("100", "200"), ("100", ""), ("", "200"), ("", "")])
def test_actual_rtk_acceptance_template(gen, loan, bankruptcy):
    from pathlib import Path
    import bankruptcy_tree
    root = Path(__file__).resolve().parents[2] / "Templates"
    template = bankruptcy_tree.resolve(
        root, entity="individual", role="acceptance", procedure="realization").path
    assert template is not None
    doc = Document(template)
    assert any("[16]" in p.text and "[17]" in p.text for p in doc.paragraphs)
    gen.replace_document_data(doc, {
        "entityType": "individual", "obligations": [], "forfeit15": "50",
        "principalDebt": "1000", "interest": "20", "creditorName": "ПАО Сбербанк",
        "loanStateDuty17": loan, "stateDuty16": bankruptcy,
        "date": "09.11.2026", "applicationDate": "09.11.2026",
    })
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "[16]" not in text and "[17]" not in text
    assert ("государственной пошлины в размере 200 руб." in text) == bool(bankruptcy)
    assert ("100 – государственная пошлина" in text) == bool(loan)
    if loan:
        assert text.index("штампу канцелярии") < text.index("100 – государственная пошлина")
    if bankruptcy:
        assert text.index("штампу канцелярии") < text.index("государственной пошлины в размере 200 руб.")
    if not loan and bankruptcy:
        assert "о взыскании с должника государственной пошлины" not in text
        assert "взыскание с должника государственной пошлины" in text


@pytest.mark.parametrize("location", ["body", "table", "header"])
def test_highlighting_preserves_order_of_text_breaks_and_tabs_within_one_run(gen, location):
    from docx.oxml.ns import qn
    doc = Document()
    if location == "table":
        paragraph = doc.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
    elif location == "header":
        paragraph = doc.sections[0].header.paragraphs[0]
    else:
        paragraph = doc.add_paragraph()
    sentinel = gen.EMPTY_MARK_SENTINEL
    run = paragraph.add_run("Начало " + sentinel + ", дата " + sentinel + ".")
    run.bold = True
    run.add_break()
    run.add_text("105 544 – государственная пошлина")
    run.add_tab()
    run.add_text("Хвост " + sentinel)
    before = paragraph.text
    count = gen._highlight_sentinel(doc, sentinel, gen.EMPTY_MARK_TEXT, gen.EMPTY_MARK_COLOR)
    assert count == 3
    assert paragraph.text == before.replace(sentinel, gen.EMPTY_MARK_TEXT)
    assert all(r.bold for r in paragraph.runs if r.text)
    highlighted = [r for r in paragraph.runs if r._r.find(qn("w:rPr") + "/" + qn("w:highlight")) is not None]
    assert [r.text for r in highlighted] == [gen.EMPTY_MARK_TEXT] * 3



def test_duties_stay_after_debt_list_with_mixed_contracts_and_empty_dates(gen):
    from pathlib import Path
    import bankruptcy_tree
    template = bankruptcy_tree.resolve(
        Path(__file__).resolve().parents[2] / "Templates", entity="individual",
        role="acceptance", procedure="realization").path
    doc = Document(template)
    gen.replace_document_data(doc, {
        "entityType": "individual", "creditorName": "ПАО Сбербанк",
        "principalDebt": "4333328,58", "interest14": "190140,59",
        "forfeit15": "12804,78", "totalDebt": "4536273,95",
        "loanStateDuty17": "105544", "stateDuty16": "123123",
        "obligations": [
            {"contractNumber": "1383367", "contractDate": "16.11.2022", "obligationType": "Кредитный договор"},
            {"contractNumber": "2105586", "contractDate": "02.08.2024", "obligationType": "Кредитный договор"},
            {"contractNumber": "99ТКПР24061300419782", "contractDate": "13.06.2024", "obligationType": "Кредитная карта"},
        ],
    })
    text = next(p.text for p in doc.paragraphs if "штампу канцелярии" in p.text)
    assert text.startswith("****** (согласно штампу канцелярии)")
    assert text.index("штампу канцелярии") < text.index("обратилось")
    assert text.index("обратилось") < text.index("неустойка")
    assert text.index("неустойка") < text.index("105 544 – государственная пошлина")
    assert text.index("105 544 – государственная пошлина") < text.index("123 123 руб.")
    for number in ("1383367", "2105586", "99ТКПР24061300419782"):
        assert text.count(number) == 1
