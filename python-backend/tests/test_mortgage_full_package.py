"""Полное решение — шестой акт, выбранный по виду ипотеки."""

from copy import deepcopy
from decimal import Decimal
from itertools import product
import re

import pytest
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from test_civil_mortgage_generation import mortgage_data


FULL_FILES = {
    "civil": "Решение ипотека длинный текст.docx",
    "ddu": "Решение ДДУ длинный текст.docx",
    "military": "Решение военнаяипотека длинный текст.docx",
}
ACTS = ["mortgage_summons", "mortgage_acceptance_short", "mortgage_acceptance_long",
        "mortgage_notice", "mortgage_decision", "mortgage_full_decision"]


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


def packet_data(kind, rep=False, solid=False, outcome="full", first="50", second="20"):
    data = mortgage_data(rep, solid, outcome, first)
    number = lambda value: Decimal(str(value or "0").replace(" ", "").replace(",", "."))
    total = Decimal("1200") + number(first) + number(second)
    patch = {
        "selectedMortgageKind":kind, "mortgageKind":kind, "forfeitInterest1362":second,
        "totalDebt":str(total), "totalWithDuty1360":str(total+10), "birthPlace":"г. Тестовый",
        "milCzzContractNumber":"ЦЖЗ-77", "milCzzContractDate":"01.02.2020",
        "milPrincipalCzz":"800000", "milInterestRate":"7", "milPenaltyRate":"0.1",
        "milInterestPeriodFrom":"01.03.2025", "milInterestPeriodTo":"01.10.2026",
        "milLoanInterest":"50000", "milPenaltySum":"30000", "milTotalClaim":"880000",
        "cjzClaimant1381":"ФГКУ Росвоенипотека", "stateDutyLocalBudget1363":"10000",
    }
    data.update(patch)
    data["fields"].update(patch)
    data["mortgageProperties"] = [
        dict(description=f"Квартира объекта {i}", address=f"г. Тестовый, ул. Тестовая, д. {i}, кв. {i}",
             cadastralNumber=f"61:44:0000000:{100+i}", egrnRecord=f"ЗАПИСЬ-ОБЪЕКТА-{i}",
             egrnRecordDate=f"2022-02-{10+i:02d}", area=str(40+i*10), value=str(1000000*i),
             startingPrice=str(800000*i), appraisalReport=f"ОТЧЁТ-{i}",
             dduContract=f"ДДУ-{i}", dduDate=f"2020-03-{10+i:02d}")
        for i in (1,2)
    ]
    return data


def render(generator, monkeypatch, tmp_path, data):
    saved = {}
    monkeypatch.setattr(generator, "generated_dir", tmp_path)
    monkeypatch.setattr(generator, "_save_document_meta", lambda *args, **kwargs: None)
    monkeypatch.setattr(DocxDocument, "save", lambda doc, path: saved.__setitem__(str(path), doc))
    result = generator.generate("mortgage", deepcopy(data))
    assert result["success"], result
    docs = {act:saved[entry["file_path"]] for act,entry in result["documents"].items()}
    return result, docs


@pytest.mark.parametrize("kind", FULL_FILES)
@pytest.mark.parametrize("rep,solid", list(product((False,True),repeat=2)))
def test_real_packet_has_six_correctly_ordered_acts(generator, monkeypatch, tmp_path, kind, rep, solid):
    data = packet_data(kind, rep, solid)
    templates = generator._get_mortgage_templates(data)
    assert templates["mortgage_full_decision"]["path"].name == FULL_FILES[kind]
    assert list(templates) == ACTS
    assert [t["order"] for t in templates.values()] == list(range(1,7))
    result,docs = render(generator, monkeypatch, tmp_path, data)
    assert result["count"] == 6 and list(result["documents"]) == ACTS
    assert [entry["order"] for entry in result["documents"].values()] == list(range(1,7))
    assert not result.get("warnings")
    full = docs["mortgage_full_decision"]
    text = "\n".join(p.text for p in full.paragraphs)
    assert "ЗАПИСЬ-ОБЪЕКТА-1" in text and "ЗАПИСЬ-ОБЪЕКТА-2" in text
    assert text.index("Квартира объекта 1") < text.index("Квартира объекта 2")
    assert not list(full.element.iter(qn("w:bookmarkStart")))
    assert not list(full.element.iter(qn("w:bookmarkEnd")))
    assert not re.search(r"\[\d+(?:\.\d+)?\]",text)
    assert "руб. руб." not in text and "руб.." not in text
    if len(data["debtors"]) > 1:
        for case in ("datv","ablt"):
            names=", ".join(generator._decline_person_name(d["name"],case) for d in data["debtors"])
            assert names in text


@pytest.mark.parametrize("kind", FULL_FILES)
@pytest.mark.parametrize("outcome", ["partial","deny"])
def test_full_keeps_claimed_sums_and_warns_about_manual_outcome(generator, monkeypatch, tmp_path, kind, outcome):
    data = packet_data(kind, outcome=outcome)
    patch = {"mortgageAwardTermination":"false","mortgageAwardDebt":"true",
             "mortgageAwardForeclosure":"false","mortgageAwardPrincipal":"700",
             "mortgageAwardInterest":"80","mortgageAwardPenalty":"20",
             "mortgageAwardInterestPenalty":"5","mortgageAwardDuty":"10"}
    data.update(patch)
    data["fields"].update(patch)
    result,docs = render(generator, monkeypatch, tmp_path, data)
    assert result["count"] == 6
    assert len(result["warnings"]) == 1 and "вручную" in result["warnings"][0]
    full = "\n".join(p.text for p in docs["mortgage_full_decision"].paragraphs)
    assert "1 270" in full and "805" not in full
    assert "удовлетворить" in full
    if kind in ("civil","ddu"):
        short = "\n".join(p.text for p in docs["mortgage_decision"].paragraphs)
        if outcome=="partial":
            assert ("805" if kind=="ddu" else "800") in short and "удовлетворить частично" in short
        else:
            assert "В удовлетворении исковых требований" in short and "Взыскать" not in short


@pytest.mark.parametrize("kind", FULL_FILES)
@pytest.mark.parametrize("first,second", [("0","20"),("50","0"),("0","0"),("","")])
def test_full_removes_each_empty_penalty_without_losing_debt(generator, monkeypatch, tmp_path, kind, first, second):
    result,docs = render(generator, monkeypatch, tmp_path, packet_data(kind, first=first, second=second))
    assert result["count"] == 6
    text = "\n".join(p.text for p in docs["mortgage_full_decision"].paragraphs)
    assert ("неустойка за просроченный основной долг" in text) == bool(Decimal(first or "0"))
    assert ("неустойка за просроченные проценты" in text) == bool(Decimal(second or "0"))
    assert "просроченный основной долг" in text and "просроченные проценты" in text
    assert "Взыскать" in text


@pytest.mark.parametrize("kind", FULL_FILES)
def test_full_formats_interest_penalty_and_currency(generator, monkeypatch, tmp_path, kind):
    result,docs = render(generator, monkeypatch, tmp_path, packet_data(kind, first="50,25", second="20,50"))
    assert result["count"] == 6
    text = "\n".join(p.text for p in docs["mortgage_full_decision"].paragraphs)
    assert "50,25 руб." in text and "20,50 руб." in text
    assert "руб. руб." not in text and "руб.." not in text


def test_missing_full_file_never_substitutes_another_docx(generator, monkeypatch, tmp_path):
    other = Document()
    other.add_paragraph("ПОСТОРОННИЙ АКТ")
    other.save(tmp_path/"другой.docx")
    templates=generator._get_mortgage_templates(packet_data("civil"))
    templates["mortgage_full_decision"]={**templates["mortgage_full_decision"],"path":tmp_path/"нет полного решения.docx"}
    monkeypatch.setattr(generator,"_get_mortgage_templates",lambda data:templates)
    result,docs=render(generator,monkeypatch,tmp_path,packet_data("civil"))
    assert result["count"]==5 and "mortgage_full_decision" not in docs
    assert len(result["warnings"])==1 and "файл шаблона не найден" in result["warnings"][0]


@pytest.mark.parametrize("items", [None, [], [{}]])
def test_invalid_property_list_does_not_break_first_five(generator, monkeypatch, tmp_path, items):
    data=packet_data("civil")
    data["mortgageProperties"]=items
    result,docs=render(generator,monkeypatch,tmp_path,data)
    assert result["count"]==5 and list(docs)==ACTS[:5]
    assert "не удалось сформировать" in result["warnings"][0]


def test_corrupt_full_file_does_not_break_first_five(generator, monkeypatch, tmp_path):
    path=tmp_path/"повреждённый.docx"
    path.write_bytes(b"not a docx")
    templates=generator._get_mortgage_templates(packet_data("civil"))
    templates["mortgage_full_decision"]={**templates["mortgage_full_decision"],"path":path}
    monkeypatch.setattr(generator,"_get_mortgage_templates",lambda data:templates)
    result,docs=render(generator,monkeypatch,tmp_path,packet_data("civil"))
    assert result["count"]==5 and list(docs)==ACTS[:5]
    assert "не удалось сформировать" in result["warnings"][0]
