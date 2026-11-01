"""Проверки требований и реквизитов военной резолютивки."""

from copy import deepcopy
from itertools import product

import pytest
from docx import Document
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from military_mortgage import FLAGS, render_military_decision, selection
from test_mortgage_full_package import packet_data


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


def render(generator, data):
    path = generator._get_mortgage_templates(data)["mortgage_decision"]["path"]
    doc = Document(path)
    original = deepcopy(data)
    render_military_decision(doc, data, generator)
    assert data == original
    assert "руб.." not in "\n".join(p.text for p in doc.paragraphs)
    return doc, "\n".join(p.text for p in doc.paragraphs)


@pytest.mark.parametrize("outcome,solid,count", list(product(("full", "partial", "deny"), (False, True), (1, 2))))
def test_outcomes_and_personal_details(generator, outcome, solid, count):
    data = packet_data("military", solid=solid, outcome=outcome)
    data["debtors"] = data["debtors"][:count]
    doc, text = render(generator, data)
    assert "Иванову Ивану Ивановичу" in text
    assert "******" not in text.split("председательствующего судьи")[1].split("РЕШИЛ")[0]
    assert "TEST-CREDIT-77" in text or outcome == "deny"
    assert "Заявлению третьего лица" not in text
    assert not list(doc.element.iter(qn("w:bookmarkStart")))
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))
    if outcome == "deny":
        assert "отказать" in text
        assert not any(word in text for word in ("Расторгнуть", "Взыскать", "Обратить взыскание"))
    else:
        assert ("солидарно" in text) == (solid and count > 1)
        assert "ИНН 7707083893, ОГРН 1027700132195" in text
        assert "(включительно) в размере" in text
        assert "1 270,00 руб." in text
        assert "880 000,00 руб." in text
        assert "Квартира объекта 1" in text and "Квартира объекта 2" in text
        assert text.index("Квартира объекта 1") < text.index("Квартира объекта 2")
        for person in data["debtors"]:
            assert f"{person['birthDate']} года рождения, ИНН {person['inn']}" in text
        assert "7% годовых" in text and "0,1%" in text


@pytest.mark.parametrize("flag", list(FLAGS))
def test_each_requirement_can_be_removed_independently(generator, flag):
    data = packet_data("military", outcome="partial")
    data[FLAGS[flag]] = "false"
    _, text = render(generator, data)
    checks = {
        "bank_termination": "Расторгнуть кредитный договор",
        "czz_termination": "Расторгнуть договор целевого жилищного займа",
        "czz_future": "начиная с",
        "czz_debt": "880 000,00 руб.",
        "bank_debt": "1 270,00 руб.",
    }
    if flag in checks:
        assert checks[flag] not in text
    if flag.endswith("foreclosure"):
        property_text = text.split("Обратить взыскание")[1].split("на следующее")[0]
        excluded = "ПАО Сбербанк" if flag.startswith("bank") else "ФГКУ Росвоенипотека"
        assert excluded not in property_text
        assert "Квартира объекта 2" in text


@pytest.mark.parametrize("penalty", ["", "0"])
@pytest.mark.parametrize("count", [1, 2])
def test_missing_penalty_never_removes_bank_debt(generator, penalty, count):
    data = packet_data("military", first=penalty, second="")
    data["debtors"] = data["debtors"][:count]
    _, text = render(generator, data)
    assert "1 200,00 руб." in text and "1 000,00 руб. — просроченный основной долг" in text
    assert "неустойка за" not in text


def test_partial_awards_are_separate_for_each_creditor(generator):
    data = packet_data("military", outcome="partial")
    data.update(mortgageAwardPrincipal="700", mortgageAwardInterest="80",
                mortgageAwardPenalty="20", mortgageAwardInterestPenalty="5", mortgageAwardDuty="5",
                militaryAwardCzzPrincipal="500000", militaryAwardCzzInterest="10000",
                militaryAwardCzzPenalty="1000", militaryAwardBudgetDuty="500")
    _, text = render(generator, data)
    assert "805,00 руб." in text and "всего 810,00 руб." in text
    assert "511 000,00 руб." in text and "500,00 руб." in text
    assert "1 270,00 руб." not in text and "880 000,00 руб." not in text
    assert data["totalDebt"] == "1270"


def test_creditors_properties_and_third_parties_are_not_confused(generator):
    data = packet_data("military")
    data["thirdParties"] = [{"name": "ФГКУ Росвоенипотека"}, {"name": "Управление Росреестра"}]
    data["mortgageProperties"].reverse()
    data["mortgageProperties"][0]["startingPrice"] = ""
    _, text = render(generator, data)
    czz_line = next(p for p in text.splitlines() if "денежные средства" in p)
    assert "в пользу ФГКУ Росвоенипотека" in czz_line and "ПАО Сбербанк" not in czz_line
    contract = next(p for p in text.splitlines() if "Расторгнуть договор целевого" in p)
    assert "ФГКУ Росвоенипотека" in contract and "ПАО Сбербанк" not in contract
    assert text.count("Иные третьи лица: Управление Росреестра.") == 1
    assert text.index("Квартира объекта 2") < text.index("Квартира объекта 1")
    assert "Начальная продажная стоимость: ******." in text
    assert "200000" not in text


def test_missing_requisites_remain_visible_without_truncated_sentences(generator):
    data = packet_data("military")
    for key in ("milCzzContractNumber", "milCzzContractDate", "stateDutyLocalBudget1363"):
        data.pop(key, None)
        data["fields"].pop(key, None)
    _, text = render(generator, data)
    assert "договор целевого жилищного займа № ****** от ******" in text
    assert "в доход местного бюджета" not in text
    assert "Взыскать с Иванова Ивана Ивановича, \n" not in text
    assert "1 270,00 руб." in text


@pytest.mark.parametrize("key", ["mortgageAwardPrincipal", "militaryAwardCzzPrincipal", "militaryAwardBudgetDuty"])
@pytest.mark.parametrize("value", ["-1", "NaN", "1.001"])
def test_invalid_partial_amounts_are_rejected(key, value):
    data = packet_data("military", outcome="partial")
    data[key] = value
    with pytest.raises(ValueError):
        selection(data)


def test_all_requirements_denied_requires_denial_mode():
    data = packet_data("military", outcome="partial")
    data.update({key: "false" for key in FLAGS.values()})
    with pytest.raises(ValueError, match="Все требования"):
        selection(data)


def test_missing_bookmark_does_not_trigger_arbitrary_paragraph_edit(generator):
    data = packet_data("military")
    doc = Document()
    doc.add_paragraph("Посторонний документ")
    with pytest.raises(ValueError, match="MilitaryMortgageHeader"):
        render_military_decision(doc, data, generator)
    assert doc.paragraphs[0].text == "Посторонний документ"


def test_partial_outcomes_do_not_imply_both_creditors_lost_something(generator):
    data = packet_data("military", outcome="partial")
    data["mortgageAwardPrincipal"] = "700"
    _, text = render(generator, data)
    assert "В удовлетворении остальной части требований ПАО Сбербанк отказать." in text
    assert "В удовлетворении остальной части требований ФГКУ Росвоенипотека" not in text


def test_only_czz_can_be_awarded(generator):
    data = packet_data("military", outcome="partial")
    data.update(mortgageAwardTermination="false", mortgageAwardDebt="false",
                mortgageAwardForeclosure="false", mortgageAwardDuty="0")
    _, text = render(generator, data)
    assert "В удовлетворении требований ПАО Сбербанк" in text
    assert "в пользу ПАО Сбербанк" not in text
    assert "в пользу ФГКУ Росвоенипотека" in text


def test_invalid_partial_military_awards_preserve_other_five(generator, monkeypatch, tmp_path):
    from test_mortgage_full_package import render as render_packet
    data = packet_data("military", outcome="partial")
    data["militaryAwardCzzPrincipal"] = "-1"
    result, docs = render_packet(generator, monkeypatch, tmp_path, data)
    assert result["count"] == 5 and "mortgage_decision" not in docs
    assert "mortgage_full_decision" in docs
    assert any("не удалось сформировать" in warning for warning in result["warnings"])


def test_missing_military_short_never_substitutes_another_act(generator, monkeypatch, tmp_path):
    from test_mortgage_full_package import render as render_packet
    data = packet_data("military")
    other = Document()
    other.add_paragraph("Посторонний акт")
    other.save(tmp_path / "чужой.docx")
    templates = generator._get_mortgage_templates(data)
    templates["mortgage_decision"] = {**templates["mortgage_decision"], "path": tmp_path / "нет военной резолютивки.docx"}
    monkeypatch.setattr(generator, "_get_mortgage_templates", lambda data: templates)
    result, docs = render_packet(generator, monkeypatch, tmp_path, data)
    assert result["count"] == 5 and "mortgage_decision" not in docs
    assert any("файл шаблона не найден" in warning for warning in result["warnings"])
