"""ДДУ: исход иска, отдельные требования и две независимые неустойки."""

from copy import deepcopy
from decimal import Decimal
from itertools import product

import pytest
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from mortgage_awards import partial_awards, prepare_partial_awards
from test_civil_mortgage_generation import mortgage_data

CASES = list(product((False, True), repeat=2))
CHOICES = [choice for choice in product((False, True), repeat=3) if any(choice)]


def ddu_data(rep=False, solid=False, outcome="partial", penalty="50", second="20"):
    data = mortgage_data(rep, solid, outcome, penalty)
    patch = {"selectedMortgageKind": "ddu", "mortgageKind": "ddu", "forfeitInterest1362": second,
             "totalDebt": str(Decimal("1200") + Decimal(penalty or "0") + Decimal(second or "0")),
             "_current_doc_type": "mortgage_decision"}
    data.update(patch)
    data["fields"].update(patch)
    data["mortgageProperties"][0].update(dduContract="DDU-77", dduDate="01.02.2020")
    return data


def selection(data, termination=True, debt=True, foreclosure=True, duty="10"):
    patch = {
        "mortgageAwardTermination": str(termination).lower(),
        "mortgageAwardDebt": str(debt).lower(),
        "mortgageAwardForeclosure": str(foreclosure).lower(),
        "mortgageAwardPrincipal": "700", "mortgageAwardInterest": "80",
        "mortgageAwardPenalty": "20", "mortgageAwardInterestPenalty": "5",
        "mortgageAwardDuty": duty,
    }
    data.update(patch)
    data["fields"].update(patch)
    return data


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


def template(generator, data):
    info = generator._get_mortgage_templates(data)["mortgage_decision"]
    return Document(generator._resolve_template_path(info["path"]))


def render(generator, monkeypatch, data):
    saved = {}
    monkeypatch.setattr(DocxDocument, "save", lambda doc, path: saved.__setitem__(str(path), doc))
    monkeypatch.setattr(generator, "_save_document_meta", lambda *args, **kwargs: None)
    result = generator.generate("mortgage", deepcopy(data))
    assert result["success"], result
    assert result["count"] == 5
    return {act: saved[entry["file_path"]] for act, entry in result["documents"].items()}


@pytest.mark.parametrize("rep,solid", CASES)
@pytest.mark.parametrize("outcome", ["full", "partial", "deny"])
def test_real_ddu_packets_in_memory(generator, monkeypatch, rep, solid, outcome):
    data = selection(ddu_data(rep, solid, outcome), termination=False, foreclosure=False)
    if outcome != "partial":
        data.update(mortgageAwardTermination="false", mortgageAwardDebt="false",
                    mortgageAwardForeclosure="false", mortgageAwardInterestPenalty="ошибка")
    docs = render(generator, monkeypatch, data)
    doc = docs["mortgage_decision"]
    text = "\n".join(p.text for p in doc.paragraphs)
    assert data["caseUid1304"] in text
    assert ("Расторгнуть кредитный договор" in text) == (outcome == "full")
    assert ("Обратить взыскание" in text) == (outcome == "full")
    assert ("Установить начальную продажную стоимость" in text) == (outcome == "full")
    assert ("Взыскать" in text) == (outcome != "deny")
    assert ("остальной части" in text) == (outcome == "partial")
    assert "Решение может быть обжаловано" in text and "Судья" in text
    assert not list(doc.element.iter(qn("w:bookmarkStart")))
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))
    if outcome == "partial":
        assert "700" in text and "80" in text and "5 руб." in text and "взыскать: 815." in text
    if outcome == "deny":
        assert "В удовлетворении исковых требований" in text and "— отказать." in text
        assert "отказать в удовлетворении" not in text
    if outcome == "full":
        assert "DDU-77" in text and "01.02.2020" in text
        assert "50 руб." in text and "20 руб." in text and "взыскать: 1 280." in text
    if solid and not rep:
        assert "Иванову Ивану Ивановичу, Петровой Анне Петровне" in text
        if outcome == "full":
            assert "Ивановым Иваном Ивановичем, Петровой Анной Петровной" in text


@pytest.mark.parametrize("rep,solid", CASES)
@pytest.mark.parametrize("termination,debt,foreclosure", CHOICES)
@pytest.mark.parametrize("duty", ["0", "10"])
def test_each_ddu_requirement_can_be_removed(generator, rep, solid, termination, debt, foreclosure, duty):
    data = selection(ddu_data(rep, solid), termination, debt, foreclosure, duty)
    doc = template(generator, data)
    generator._apply_mortgage_awards(doc, prepare_partial_awards(data, "ddu"))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert ("Расторгнуть кредитный договор" in text) == termination
    assert ("Обратить взыскание" in text) == foreclosure
    assert ("Установить начальную продажную стоимость" in text) == foreclosure
    recovery = next((p.text for p in doc.paragraphs if p.text.startswith("Взыскать")), "")
    assert bool(recovery) == (debt or duty != "0")
    if recovery:
        assert ("задолженность" in recovery) == debt
        assert ("судебные расходы" in recovery) == (duty != "0")
        assert ("а всего взыскать:" in recovery) == debt
    assert "[888]" in text and "[889]" in text
    assert "Судья" in text and "Решение может быть обжаловано" in text


@pytest.mark.parametrize("first,second", list(product(("", "0", "25"), repeat=2)))
def test_ddu_penalties_are_removed_independently(generator, monkeypatch, first, second):
    docs = render(generator, monkeypatch, ddu_data(outcome="full", penalty=first, second=second))
    text = "\n".join(p.text for p in docs["mortgage_decision"].paragraphs)
    assert ("неустойка за просроченный основной долг" in text) == (first == "25")
    assert ("неустойка за просроченные проценты" in text) == (second == "25")
    assert "просроченные проценты - 200" in text and "просроченный основной долг - 1 000" in text


def test_ddu_penalty_cleanup_preserves_styles_and_split_markers(generator):
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("[13] — основной долг, [14] — проценты").bold = True
    for fragment in (", неустойка за просроченный основной долг - [1", "5]",
                     ", неустойка за просроченные проценты - [136", "2]"):
        p.add_run(fragment).italic = True
    p.add_run(", судебные расходы [16], а всего взыскать: [1360].").underline = True
    generator._apply_penalty_removal(doc, ddu_data(outcome="full", penalty="0", second="0"))
    assert p.text == "[13] — основной долг, [14] — проценты, судебные расходы [16], а всего взыскать: [1360]."
    assert next(r for r in p.runs if "основной долг" in r.text).bold
    assert next(r for r in p.runs if "судебные расходы" in r.text).underline


def test_ddu_awarded_total_includes_second_penalty_without_changing_original():
    data = selection(ddu_data())
    before = deepcopy(data)
    result = prepare_partial_awards(data, "ddu")
    assert result["forfeitInterest1362"] == "5.00"
    assert result["totalDebt"] == "805.00"
    assert result["totalWithDuty1360"] == "815.00"
    assert data == before
    civil = prepare_partial_awards(data, "civil")
    assert civil["totalDebt"] == "800.00" and civil["forfeitInterest1362"] == "20"


@pytest.mark.parametrize("value", ["-1", "abc", "1.001", "1,2,3", "NaN"])
def test_invalid_awarded_second_penalty_rejected(value):
    data = selection(ddu_data())
    data["mortgageAwardInterestPenalty"] = value
    with pytest.raises(ValueError, match="сумм"):
        partial_awards(data, "ddu")


def test_hidden_invalid_second_penalty_does_not_prevent_costs_only(generator, monkeypatch):
    data = selection(ddu_data(), False, False, True, "12,50")
    data["mortgageAwardInterestPenalty"] = "-1"
    docs = render(generator, monkeypatch, data)
    text = "\n".join(p.text for p in docs["mortgage_decision"].paragraphs)
    assert "задолженность по кредитному договору" not in text
    assert "судебные расходы по оплате государственной пошлины в размере 12,50 руб." in text
    assert "а всего взыскать:" not in text and "руб.." not in text
    assert "Обратить взыскание" in text and "Установить начальную" in text


def test_ddu_can_award_only_interest_penalty(generator, monkeypatch):
    data = selection(ddu_data(), False, True, False, "0")
    data.update(mortgageAwardPrincipal="0", mortgageAwardInterest="0",
                mortgageAwardPenalty="0", mortgageAwardInterestPenalty="0,30")
    docs = render(generator, monkeypatch, data)
    text = "\n".join(p.text for p in docs["mortgage_decision"].paragraphs)
    assert "неустойка за просроченные проценты - 0,30 руб." in text
    assert "неустойка за просроченный основной долг" not in text
    assert "взыскать: 0,30." in text


@pytest.mark.parametrize("count", [2, 3, 5])
def test_all_ddu_debtors_reach_claim_and_termination(generator, count):
    data = ddu_data(solid=True)
    names = ["Иванов Иван Иванович", "Петрова Анна Петровна", "Кузнецов Алексей Николаевич",
             "Сидорова Ольга Сергеевна", "Смирнов Семён Семёнович"][:count]
    data["debtors"] = [{"name": name} for name in names]
    generator._apply_debtor_name_field_mapping(data, generator._base_field_mapping(), True)
    assert data["mortgageDebtorNameDative"] == ", ".join(generator._decline_person_name(n, "datv") for n in names)
    assert data["applicantNameInstrumental"] == ", ".join(generator._decline_person_name(n, "ablt") for n in names)


@pytest.mark.parametrize("missing", ["MortgageAwards", "MortgageDebt", "MortgageSale"])
def test_missing_ddu_bookmark_is_rejected_before_mutation(generator, missing):
    data = selection(ddu_data(), False, True, False)
    doc = template(generator, data)
    start = next(n for n in doc.element.iter(qn("w:bookmarkStart")) if n.get(qn("w:name")) == missing)
    start.getparent().remove(start)
    before = doc.element.xml
    with pytest.raises(ValueError, match=missing):
        generator._apply_mortgage_awards(doc, data)
    assert doc.element.xml == before


@pytest.mark.parametrize("kind,act,source", [
    ("civil", "mortgage_notice", "mortgage_claim"),
    ("ddu", "mortgage_summons", "mortgage_claim"),
    ("military", "mortgage_decision", "mortgage_claim"),
    ("ddu", "mortgage_decision", "rtk_application"),
])
def test_common_military_and_bankruptcy_do_not_apply_ddu_selection(generator, kind, act, source):
    data = selection(ddu_data(), False, False, False)
    data.update(selectedMortgageKind=kind, _current_doc_type=act, sourceDocumentType=source)
    doc = Document()
    doc.add_paragraph("Нет ипотечных закладок.")
    before = doc.element.xml
    generator._apply_mortgage_awards(doc, data)
    assert doc.element.xml == before


@pytest.mark.parametrize("kind", ["civil", "ddu"])
def test_word_can_reorder_coincident_bookmark_boundaries(generator, kind):
    data = ddu_data(outcome="full")
    data.update(selectedMortgageKind=kind, mortgageKind=kind)
    doc = template(generator, data)
    starts = {n.get(qn("w:name")): n for n in doc.element.iter(qn("w:bookmarkStart"))}
    parent = starts["MortgageAwards"]
    child = starts["MortgageTermination"]
    child.getparent().remove(child)
    parent.addprevious(child)
    ends = {n.get(qn("w:id")): n for n in doc.element.iter(qn("w:bookmarkEnd"))}
    parent_end = ends[parent.get(qn("w:id"))]
    child_end = ends[starts["MortgageSale"].get(qn("w:id"))]
    child_end.getparent().remove(child_end)
    parent_end.addnext(child_end)
    generator._apply_mortgage_awards(doc, data)
    assert any(p.text.startswith("Расторгнуть") for p in doc.paragraphs)
    assert not list(doc.element.iter(qn("w:bookmarkStart")))
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))


def test_inner_bookmark_cannot_escape_to_another_paragraph(generator):
    data = selection(ddu_data())
    doc = template(generator, data)
    child = next(n for n in doc.element.iter(qn("w:bookmarkStart"))
                 if n.get(qn("w:name")) == "MortgageTermination")
    child.getparent().remove(child)
    doc.paragraphs[0]._p.insert(0, child)
    before = doc.element.xml
    with pytest.raises(ValueError, match="свой абзац"):
        generator._apply_mortgage_awards(doc, data)
    assert doc.element.xml == before
