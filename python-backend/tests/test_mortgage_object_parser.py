"""Варианты вёрстки и границы реквизитов недвижимости без привязки к файлам."""

from itertools import product

import pytest

from document_analyzer import DocumentAnalyzer
from mortgage_object_parser import collateral_chunks, property_area
from llm.windows import extract_collateral_block
from llm.prompts import build_df_mortgage_collateral_prompt


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


def objects(address_label="адрес:", separator="\n", heading="а именно:"):
    return (
        "Кредит выдавался на приобретение недвижимости, " + heading + separator +
        "Жилой дом-площадь: 84 кв.м., " + address_label + " г. Примерск, ул. Тестовая, д. 24, кадастровый номер: 20:06:1234567:111," + separator +
        "земельный участок, " + address_label + " г. Примерск, ул. Тестовая, д. 24, кадастровый номер: 20:06:1234567:222" + separator +
        "Для обеспечения исполнения обязательств заемщик предоставил залог.\n"
        "Согласно договору заемщик обязан погашать кредит.\n"
        "ПРОШУ:\nОбратить взыскание на имущество, а именно:\n"
        "- Жилой дом-площадь: 84 кв.м., адрес: г. Примерск, ул. Тестовая, д. 24, кадастровый номер: 20:06:1234567:111\n"
        "- земельный участок, адрес: г. Примерск, ул. Тестовая, д. 24, кадастровый номер: 20:06:1234567:222\n"
        "Определить способ реализации имущества.\n"
    )


@pytest.mark.parametrize("label,separator", list(product(("адрес:", "по адресу:"), ("\n", "\n\n", "; "))))
def test_properties_are_bounded_deduplicated_and_split_into_fields(analyzer, label, separator):
    text = objects(label, separator)
    props = analyzer._build_mortgage_properties(text, [])
    assert len(props) == 2
    house, land = props
    assert house["description"] == "Жилой дом"
    assert house["area"] == "84"
    assert house["address"] == "г. Примерск, ул. Тестовая, д. 24"
    assert house["cadastralNumber"] == "20:06:1234567:111"
    assert land["description"] == "Земельный участок"
    assert land["cadastralNumber"] == "20:06:1234567:222"
    assert not house["value"] and not land["egrnRecord"]
    block = extract_collateral_block(text)
    assert "Согласно договору" not in block and "ПРОШУ" not in block
    assert block.count("20:06:1234567:111") == 1
    assert max(map(len, collateral_chunks(text))) < 350


@pytest.mark.parametrize("value,expected", [("общей площадью 183 кв.м.", "183"), ("площадь: 84 кв. м", "84"),
    ("площадью 1495+/-27 кв.м.", "1495+/-27"), ("площади 100 ± 2 м²", "100±2")])
def test_area_keeps_precision_and_uncertainty(value, expected):
    assert property_area(value) == expected


@pytest.mark.parametrize("number", ["20/026/2025-14", "23-68-09/699/4620-144", "23:26:5876727:9651-59/678/6420-2"])
@pytest.mark.parametrize("sign", ["", "№ "])
def test_egrn_number_does_not_require_sign_or_date(analyzer, number, sign):
    assert analyzer._mp_egrn("Запись в ЕГРН: " + sign + number + ". Ипотека.") == (number, "")


def test_record_number_without_sign_and_with_date(analyzer):
    assert analyzer._mp_egrn("Запись в ЕГРН: 20/026/2025-14 от 02.03.2025. Ипотека.") == ("20/026/2025-14", "02.03.2025")


def test_egrn_data_does_not_cross_objects(analyzer):
    text = ("предметы залога, а именно:\n"
        "жилой дом, кадастровый номер: 20:06:1234567:111. Запись в ЕГРН: 20/026/2025-14. Ипотека.\n"
        "земельный участок, кадастровый номер: 20:06:1234567:222. Запись в ЕГРН: 20/026/2025-15. Ипотека.\n"
        "В силу статьи закона.\n")
    house, land = analyzer._build_mortgage_properties(text, [])
    assert house["egrnRecord"] == "20/026/2025-14"
    assert land["egrnRecord"] == "20/026/2025-15"


@pytest.mark.parametrize("name", ["квартиру", "жилой дом", "нежилое помещение"])
def test_ddu_description_names_physical_property(analyzer, name):
    text = ("Обратить взыскание на имущественные права требования по ДОГОВОРУ № ДДУ-123 "
            "УЧАСТИЯ В ДОЛЕВОМ СТРОИТЕЛЬСТВЕ от 01.02.2022 на " + name +
            ", расположенное по адресу: г. Примерск, ул. Тестовая, д. 1, кадастровый номер земельного участка № 20:06:1234567:111.\n"
            "Установить начальную цену.")
    props = analyzer._build_mortgage_properties(text, [], "ddu")
    assert props[0]["description"] == {"квартиру": "Квартира", "жилой дом": "Жилой дом", "нежилое помещение": "Нежилое помещение"}[name]
    assert props[0]["dduContract"] == "ДДУ-123"
    assert props[0]["dduDate"] == "01.02.2022"


def test_unknown_ddu_property_type_is_not_invented(analyzer):
    props = analyzer._build_mortgage_properties("имущественные права требования по договору без описания", [], "ddu")
    assert props[0]["description"] == ""


@pytest.mark.parametrize("name", ["ПЕТРОВА МАРИЯ НИКОЛАЕВНА", "ИВАНОВ ИВАН ИВАНОВИЧ"])
@pytest.mark.parametrize("separator", ["", ":", "："])
def test_representative_glued_to_bank_and_snils(analyzer, name, separator):
    text = ("Представитель истца:ПАО Банк в лице филиала - Южный Банк ПАО Банк " +
            name + "СНИЛС" + separator + " 123-456-789 00Почтовый адрес: г. Примерск\nОтветчик:\nСидоров Сергей Сергеевич")
    assert analyzer._extract_representative_name(text) == name.title()


def test_missing_plaintiff_representative_cannot_be_filled_from_defendant_or_attachment(analyzer):
    text = ("Представитель истца:ПАО Банк\nОтветчик\nСидоров Сергей Сергеевич\n"
            "Представитель ответчика: Петров Пётр Петрович\n"
            "Приложение\nПредставитель ПАО Банк\nПо доверенности Кузнецов К.К.")
    assert analyzer._extract_representative_name(text) is None


def test_ddu_hint_contract_matches_physical_description():
    prompt = build_df_mortgage_collateral_prompt(with_ddu=True)
    assert "вид физического объекта" in prompt["system"]


def test_house_type_does_not_come_from_underlying_land_or_street(analyzer):
    assert analyzer._mp_type("Жилой дом на земельном участке, по адресу: ул. Квартирная, д. 1") == "дом"
    assert analyzer._mp_type("Квартира, по адресу: ул. Дома, д. 5") == "квартира"


def test_unknown_ddu_type_does_not_come_from_borrower_address_or_land_cadastre(analyzer):
    text = ("Ответчик: Иванов Иван Иванович, адрес: г. Примерск, квартира 5.\n"
            "Имущественные права требования по договору, кадастровый номер земельного участка № 20:06:1234567:111.\n"
            "Установить начальную цену.")
    assert analyzer._build_mortgage_properties(text, [], "ddu")[0]["description"] == ""


def test_unknown_prose_is_not_an_address_continuation():
    text = ("а именно:\nКвартира, адрес: г. Примерск, ул. Тестовая, д. 1,\n"
            "Обязательства заемщика заключаются в ежемесячном погашении кредита.\n")
    assert "Обязательства" not in collateral_chunks(text)[0]


def test_wrapped_address_is_preserved():
    text = ("а именно:\nКвартира, адрес: г. Примерск,\n"
            "ул. Тестовая, д. 1,\nкадастровый номер: 20:06:1234567:111.\nСогласно договору")
    assert "ул. Тестовая" in collateral_chunks(text)[0]
