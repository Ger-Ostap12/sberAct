"""Частичное удовлетворение обычной ипотеки: выбор требований и суммы."""

from copy import deepcopy
from itertools import product

import pytest
from docx import Document
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from mortgage_awards import AWARD_BOOKMARKS, partial_awards, prepare_partial_awards
from test_civil_mortgage_generation import mortgage_data, scope

CHOICES = [choice for choice in product((False, True), repeat=3) if any(choice)]


def request(termination=True, debt=True, foreclosure=True, duty="10", **changes):
    data = scope(
        claimResolution="partial",
        mortgageAwardTermination=str(termination).lower(),
        mortgageAwardDebt=str(debt).lower(),
        mortgageAwardForeclosure=str(foreclosure).lower(),
        mortgageAwardPrincipal="700", mortgageAwardInterest="80",
        mortgageAwardPenalty="20", mortgageAwardDuty=duty,
        principalDebt="1000", interest="200", forfeit="50", stateDuty16="10",
    )
    data.update(changes)
    return data


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


def source_doc(generator, representatives=False, solidary=False):
    data = mortgage_data(representatives, solidary)
    template = generator._get_mortgage_templates(data)["mortgage_decision"]["path"]
    return Document(generator._resolve_template_path(template))


@pytest.mark.parametrize("termination,debt,foreclosure", CHOICES)
@pytest.mark.parametrize("representatives,solidary", list(product((False, True), repeat=2)))
@pytest.mark.parametrize("duty", ["0", "10"])
def test_all_partial_combinations(generator, termination, debt, foreclosure, representatives, solidary, duty):
    doc = source_doc(generator, representatives, solidary)
    data = prepare_partial_awards(request(termination, debt, foreclosure, duty))
    generator._apply_civil_mortgage_awards(doc, data)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert ("Расторгнуть кредитный договор" in text) == termination
    assert ("Обратить взыскание" in text) == foreclosure
    assert ("Определить способ реализации" in text) == foreclosure
    recovery = next((p.text for p in doc.paragraphs if p.text.startswith("Взыскать")), "")
    assert bool(recovery) == (debt or duty != "0")
    if recovery:
        assert ("задолженность" in recovery) == debt
        assert ("расходы по оплате государственной пошлины" in recovery) == (duty != "0")
        assert ("всего" in recovery) == debt
    assert "[888]" in text and "[889]" in text
    assert "Решение может быть обжаловано" in text and "Судья" in text
    assert not list(doc.element.iter(qn("w:bookmarkStart")))
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))


def test_awarded_amounts_are_separate_and_all_aliases_agree():
    original = request()
    original.update(totalDebt="9999", totalWithDuty1360="7777", interest14="900", forfeit15="400")
    snapshot = deepcopy(original)
    result = prepare_partial_awards(original)
    assert original == snapshot
    for key in ("principalDebt", "loanDebt", "principalDebt13"):
        assert result[key] == "700.00"
    assert result["interest"] == result["interest14"] == "80.00"
    assert result["forfeit"] == result["forfeit15"] == result["penalties"] == "20.00"
    assert result["stateDuty"] == result["stateDuty16"] == "10.00"
    assert result["totalDebt"] == "800.00"
    assert result["totalWithDuty1360"] == "810.00"


@pytest.mark.parametrize("resolution", ["full", "deny", ""])
def test_other_outcomes_ignore_stale_partial_settings(resolution):
    data = request(False, False, False, mortgageAwardPrincipal="ошибка")
    data["claimResolution"] = resolution
    assert prepare_partial_awards(data) is data


def test_previous_clients_keep_previous_values():
    data = scope(claimResolution="partial", totalDebt="900", forfeit="50")
    assert partial_awards(data) is None
    assert prepare_partial_awards(data) is data


def test_new_flags_can_use_original_amounts_and_nested_fields():
    data = scope(claimResolution="partial", principalDebt="100", interest="20", forfeit="0", stateDuty16="5")
    data["fields"] = {"mortgageAwardTermination": "false"}
    result = prepare_partial_awards(data)
    assert result["totalDebt"] == "120.00"
    assert result["totalWithDuty1360"] == "125.00"


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "1.001", "1,2,3", "abc", "1e3"])
def test_invalid_money_is_rejected(value):
    with pytest.raises(ValueError, match="сумм"):
        partial_awards(request(mortgageAwardPrincipal=value))


@pytest.mark.parametrize("value", ["1 234,50", "1234.50", "1\u00a0234,50 руб.", "1234,50 ₽"])
def test_local_money_formats(value):
    result = prepare_partial_awards(request(mortgageAwardPrincipal=value))
    assert result["principalDebt"] == "1234.50"
    assert result["totalDebt"] == "1334.50"


def test_empty_awarded_penalty_is_zero_and_decimal_totals_are_exact():
    result = prepare_partial_awards(request(mortgageAwardPrincipal="0,10",
        mortgageAwardInterest="0,20", mortgageAwardPenalty="", mortgageAwardDuty="0"))
    assert result["totalDebt"] == result["totalWithDuty1360"] == "0.30"
    assert result["forfeit"] == "0.00"


def test_hidden_debt_amounts_are_ignored_for_costs_only():
    result = prepare_partial_awards(request(False, False, True, "15", mortgageAwardPrincipal="-50"))
    assert result["totalDebt"] == "0.00"
    assert result["totalWithDuty1360"] == "15.00"


@pytest.mark.parametrize("changes,message", [
    ({"mortgageAwardTermination": "false", "mortgageAwardDebt": "false",
      "mortgageAwardForeclosure": "false"}, "Все требования"),
    ({"mortgageAwardDebt": "yes"}, "Некорректный выбор"),
    ({"mortgageAwardPrincipal": "", "mortgageAwardInterest": "0", "mortgageAwardPenalty": "0"},
     "положительную сумму"),
])
def test_invalid_partial_requests_leave_document_untouched(generator, changes, message):
    doc = source_doc(generator)
    before = doc.element.xml
    with pytest.raises(ValueError, match=message):
        generator.replace_document_data(doc, request(**changes))
    assert doc.element.xml == before


@pytest.mark.parametrize("name", AWARD_BOOKMARKS)
def test_missing_individual_bookmark_fails_before_mutation(generator, name):
    doc = source_doc(generator)
    start = next(node for node in doc.element.iter(qn("w:bookmarkStart"))
                 if node.get(qn("w:name")) == name)
    start.getparent().remove(start)
    before = doc.element.xml
    with pytest.raises(ValueError, match=name):
        generator._apply_civil_mortgage_awards(doc, request(False, True, False))
    assert doc.element.xml == before


def test_bad_recovery_clause_fails_before_removing_other_requirements(generator):
    doc = source_doc(generator)
    paragraph = next(p for p in doc.paragraphs if p.text.startswith("Взыскать"))
    generator._regex_sub_in_paragraphs([paragraph], __import__("re").compile("а также"), "плюс")
    before = doc.element.xml
    with pytest.raises(ValueError, match="MortgageDebt"):
        generator._apply_civil_mortgage_awards(doc, request(False, True, False, "0"))
    assert doc.element.xml == before


@pytest.mark.parametrize("kind,doc_type", [
    ("ddu", "mortgage_decision"), ("military", "mortgage_decision"),
    ("civil", "mortgage_notice"), ("civil", "mortgage_summons"),
    ("civil", "mortgage_acceptance_short"), ("civil", "mortgage_acceptance_long"),
])
def test_new_settings_do_not_touch_other_documents(generator, kind, doc_type):
    doc = Document()
    doc.add_paragraph("Текст [13], [14], [15], [16], [1360].")
    data = request(False, False, False, mortgageAwardPrincipal="-1")
    data.update(selectedMortgageKind=kind, _current_doc_type=doc_type)
    before = doc.element.xml
    generator._apply_civil_mortgage_awards(doc, data)
    assert doc.element.xml == before


def test_awarded_total_uses_russian_money_format(generator):
    doc = source_doc(generator)
    data = mortgage_data()
    data.update(request(False, True, False, "0", mortgageAwardPrincipal="0,10",
                        mortgageAwardInterest="0,20", mortgageAwardPenalty=""))
    generator.replace_document_data(doc, data)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "всего 0,30." in text
    assert "всего 0.30" not in text
