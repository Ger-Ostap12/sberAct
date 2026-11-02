"""Обычная резолютивка выводит каждый предмет ипотеки со своими реквизитами."""

from copy import deepcopy
from itertools import product

import pytest
from docx import Document
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from test_mortgage_full_package import packet_data, render as render_packet


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


def request(rep=False, solid=False, outcome="full", count=2):
    data = packet_data("civil", rep=rep, solid=solid, outcome=outcome)
    data["sourceDocumentType"] = "mortgage_claim"
    data["_current_doc_type"] = "mortgage_decision"
    data["mortgageProperties"] = [
        dict(description=f"Объект {i}", address=f"г. Тестовый, ул. Объектовая, д. {i}",
             cadastralNumber=f"61:44:1234567:{100+i}", area=str(40+i),
             egrnRecord=f"ЕГРН-ОБЪЕКТА-{i}", egrnRecordDate=f"2022-03-{10+i:02d}",
             value=str(1000000*i), startingPrice=str(800000*i),
             appraisalReport=f"ОТЧЁТ-{i}", npcStrategy=f"{70+i}%",
             saleMethod=f"продажа объекта {i} с публичных торгов")
        for i in range(1,count+1)
    ]
    for key in ("mortgageCollateralDescription1221", "mortgagePropertyAddress1227",
                "mortgageCadastralNumber1226", "mortgageEgrnRecord1229",
                "mortgageEgrnRecordDate1230", "mortgagePropertyArea1233",
                "mortgageCollateralValue1224", "mortgageStartingPrice1225"):
        data[key] = "УСТАРЕВШЕЕ-ЗНАЧЕНИЕ"
        data["fields"][key] = "УСТАРЕВШЕЕ-ЗНАЧЕНИЕ"
    return data


def decision(generator, data):
    template = generator._get_mortgage_templates(data)["mortgage_decision"]["path"]
    doc = Document(template)
    generator.set_times_new_roman_11(doc)
    original = deepcopy(data["mortgageProperties"])
    generator.replace_document_data(doc, deepcopy(data))
    assert data["mortgageProperties"] == original
    return doc, "\n".join(p.text for p in doc.paragraphs)


@pytest.mark.parametrize("rep,solid,count", list(product((False,True),(False,True),(1,2,5))))
@pytest.mark.parametrize("outcome", ["full","partial"])
def test_all_template_variants_use_local_requisites(generator, rep, solid, count, outcome):
    data=request(rep,solid,outcome,count)
    doc,text=decision(generator,data)
    assert "УСТАРЕВШЕЕ-ЗНАЧЕНИЕ" not in text
    for item in data["mortgageProperties"]:
        for key in ("description","address","cadastralNumber","area","egrnRecord","appraisalReport","npcStrategy","saleMethod"):
            assert item[key] in text,(key,item,text)
        assert f"от {item['egrnRecordDate'][-2:]}.03.2022" in text
    assert text.count("Объект недвижимости:")==count
    for paragraph in doc.paragraphs:
        if paragraph.text.startswith(("Объект недвижимости:", "Адрес:", "Кадастровый номер:", "Запись в ЕГРН:")):
            assert all(run.font.size.pt == 11 for run in paragraph.runs)
    assert "руб.." not in text and "руб. руб." not in text
    assert not list(doc.element.iter(qn("w:bookmarkStart")))
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))
    for index,item in enumerate(data["mortgageProperties"]):
        start=text.index("Объект недвижимости: "+item["description"])
        end=text.index("Объект недвижимости:",start+1) if index+1<count else len(text)
        block=text[start:end]
        for other in data["mortgageProperties"]:
            if other is not item:
                assert other["address"] not in block
                assert other["cadastralNumber"] not in block
                assert other["egrnRecord"] not in block


def test_reverse_order_is_preserved(generator):
    data=request(count=3)
    data["mortgageProperties"].reverse()
    _,text=decision(generator,data)
    assert text.index("Объект 3")<text.index("Объект 2")<text.index("Объект 1")


def test_missing_second_requisites_do_not_inherit_first(generator):
    data=request()
    second=data["mortgageProperties"][1]
    for key in list(second):
        if key!="description":
            second[key]=""
    _,text=decision(generator,data)
    block=text.split("Объект недвижимости: Объект 2.")[1]
    assert "Адрес: ******" in block and "Кадастровый номер: ******" in block
    assert "№ ****** от ******" in block
    assert "Рыночная стоимость: ******" in block and "Начальная продажная стоимость: ******" in block
    for key in ("address","cadastralNumber","egrnRecord","appraisalReport"):
        assert data["mortgageProperties"][0][key] not in block
    assert "продажа с публичных торгов" in block


def test_duplicate_descriptions_are_not_merged(generator):
    data=request()
    data["mortgageProperties"][1]["description"]=data["mortgageProperties"][0]["description"]
    _,text=decision(generator,data)
    assert text.count("Объект недвижимости: Объект 1.")==2
    assert "61:44:1234567:101" in text and "61:44:1234567:102" in text


@pytest.mark.parametrize("area,expected", [("54,3 кв. м","54,3"),("1495+/-27","1495+/-27"),(0,"0"),("","84")])
def test_area_units_and_legacy_description_fallback(generator, area, expected):
    data=request(count=1)
    data["mortgageProperties"][0].update(area=area,description="Дом площадью 84 кв. м")
    _,text=decision(generator,data)
    assert f"Общая площадь (кв. м.): {expected}." in text


def test_prices_and_report_are_per_property_with_russian_numbers(generator):
    data=request()
    data["mortgageProperties"][0].update(value="1 000 000,25 руб.",startingPrice="800000,20")
    data["mortgageProperties"][1].update(value="2000000.50",startingPrice="1600000.40")
    _,text=decision(generator,data)
    first,second=text.split("Объект недвижимости: Объект 1.")[1].split("Объект недвижимости: Объект 2.")
    assert "1 000 000,25 руб." in first and "800 000,20 руб." in first
    assert "2 000 000,50 руб." in second and "1 600 000,40 руб." in second
    assert "ОТЧЁТ-1" in first and "ОТЧЁТ-2" in second


@pytest.mark.parametrize("outcome,foreclosure", [("deny",True),("partial",False)])
def test_denied_foreclosure_ignores_bad_property_list(generator,outcome,foreclosure):
    data=request(outcome=outcome)
    data["mortgageProperties"]=[None]
    data["mortgageAwardForeclosure"]=str(foreclosure).lower()
    _,text=decision(generator,data)
    assert "Объект недвижимости:" not in text
    assert "Обратить взыскание" not in text


def test_blank_cards_are_skipped_without_number_limit(generator):
    data=request(count=6)
    data["mortgageProperties"].insert(1,{})
    _,text=decision(generator,data)
    assert text.count("Объект недвижимости:")==6 and "Объект 6" in text


def test_malformed_property_does_not_remove_other_acts(generator,monkeypatch,tmp_path):
    data=request()
    data["mortgageProperties"]=[None]
    result,docs=render_packet(generator,monkeypatch,tmp_path,data)
    assert result["count"]==4
    assert "mortgage_decision" not in docs and "mortgage_full_decision" not in docs
    assert len(result["warnings"])==2
