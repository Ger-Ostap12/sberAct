# -*- coding: utf-8 -*-
"""Тесты блока ЗАЛОГ: извлечение предметов залога (недвижимость / авто / иное).

Пиновка поведения извлекателей, чтобы будущие правки не сломали:
- недвижимость: вид объекта, кадастр, адрес (в т.ч. «Расположенное … здание»);
- авто: вид ТС + марка/модель + год (метки «Марка ТС:», OCR «Мо дель», freeform);
- иное (движимое): наименование + стоимость; болванки без стоимости отсеиваются;
- разбор блоков «в залог передано … имущество: <предметы>».
"""
import pytest

from document_analyzer import DocumentAnalyzer


@pytest.fixture(scope="module")
def da():
    return DocumentAnalyzer()


# --- Вид ТС -----------------------------------------------------------------
@pytest.mark.parametrize("desc,expected", [
    ("автомобиль: VIN: X, Грузовой ИЖ 27175 2009.", "Грузовой"),
    ("движимое имущество: полуприцеп, Модель: 98472 0000010; Год: 2020.", "Полуприцеп"),
    ("движимое имущество: грузовой тягач, Марка: МЕРСЕ; Год: 2011.", "Грузовой тягач"),
    ("движимое имущество: прицеп, Krone; Марка ТС: KRONE.", "Прицеп"),
    ("седельный тягач Volvo FH 2015.", "Седельный тягач"),
    ("квартира площадью 40 кв.м", None),  # не ТС
])
def test_vehicle_type(da, desc, expected):
    assert da._extract_vehicle_type(desc) == expected


# --- Год выпуска ------------------------------------------------------------
@pytest.mark.parametrize("desc,expected", [
    ("Год: 2020.", "2020"),
    ("Год выпуска ТС: 1992;", "1992"),
    ("год выпуска: 2011", "2011"),
    ("2011 г.в.", "2011"),
    ("Грузовой ИЖ 27175 2009.", "2009"),  # хвостовой год без метки
    ("Модель: 98472 0000010", None),      # 5-значный номер — не год
])
def test_car_year(da, desc, expected):
    assert da._extract_car_year(desc) == expected


# --- Марка/модель (метки и OCR) ---------------------------------------------
@pytest.mark.parametrize("desc,expected", [
    ("Марка: МЕРСЕ ДЕС БЕНЦ; Модель: АКТРОС 1846; Год: 2011.", "МЕРСЕ ДЕС БЕНЦ АКТРОС 1846"),
    ("Марка ТС: KRONE.", "KRONE"),
    ("Марка: MERCEDES BENZ; Мо дель: ACTROS 1844 LS; Год: 2008.", "MERCEDES BENZ ACTROS 1844 LS"),
    ("Модель: 98472 0000010; Год: 2020.", "98472 0000010"),
])
def test_brand_model(da, desc, expected):
    assert da._extract_collateral_brand_model(desc) == expected


# --- Freeform марка/модель после вида ТС ------------------------------------
def test_freeform_make_model(da):
    desc = "автомобиль: VIN: XWK27175090025634, Грузовой ИЖ 27175 2009."
    assert da._extract_freeform_make_model(desc, "Грузовой", "2009") == "ИЖ 27175"


# --- Полное наименование авто (интеграция _make_collateral_obj) -------------
@pytest.mark.parametrize("desc,expected_name", [
    ("автомобиль: VIN: XWK27175090025634, Грузовой ИЖ 27175 2009.",
     "Грузовой ИЖ 27175, 2009 г.в."),
    ("движимое имущество: VIN: X89984710L2GS7002, полуприцеп, Модель: 98472 0000010; Год: 2020.",
     "Полуприцеп 98472 0000010, 2020 г.в."),
    ("движимое имущество: VIN: WD89340321L561057, грузовой тягач, Марка: МЕРСЕ ДЕС БЕНЦ; Модель: АКТРОС 1846; Год: 2011.",
     "Грузовой тягач МЕРСЕ ДЕС БЕНЦ АКТРОС 1846, 2011 г.в."),
    ("движимое имущество: VIN: SDP24ELMW103735, прицеп, Krone; Год выпуска ТС: 1992; Марка ТС: KRONE.",
     "Прицеп KRONE, 1992 г.в."),
    ("автомобиль: VIN: WDB9340321L364458, Грузовой Марка: MERCEDES BENZ; Мо дель: ACTROS 1844 LS; Год: 2008.",
     "Грузовой MERCEDES BENZ ACTROS 1844 LS, 2008 г.в."),
])
def test_auto_object_name(da, desc, expected_name):
    obj = da._make_collateral_obj(0, desc)
    assert obj["collateralType"] == "auto"
    assert obj["objectName"] == expected_name


# --- Недвижимость: вид объекта (здание важнее «на земельном участке») --------
def test_real_estate_object_name_building_wins(da):
    desc = ("Расположенное на земельном участке здание, находящееся по адресу: "
            "Россия, Волгоград, ул. Бахтурова, 12ж, кадастровый номер "
            "34:34:080109:528, стоимостью 20 622 000,00 руб.")
    obj = da._make_collateral_obj(0, desc)
    assert obj["collateralType"] == "real_estate"
    assert obj["objectName"].startswith("Здание")
    assert obj["cadastralNumber"] == "34:34:080109:528"
    # адрес — после «по адресу», без хвоста «здание/находящееся» и без кадастра/стоимости
    assert obj["address"].startswith("Россия, Волгоград")
    assert "здание" not in obj["address"].lower()
    assert "кадастр" not in obj["address"].lower()


def test_real_estate_object_name_land(da):
    desc = ("Земельный участок площадью 1940 кв. м, с кадастровым номером "
            "34:34:080109:88, находящийся по адресу: обл. Волгоградская, "
            "г. Волгоград, ул. Бахтурова, 12ж, стоимостью 1 971 000,00 руб.")
    obj = da._make_collateral_obj(0, desc)
    assert obj["collateralType"] == "real_estate"
    assert obj["objectName"].startswith("Земельный участок")
    assert obj["cadastralNumber"] == "34:34:080109:88"
    assert obj["collateralValue"] == "1971000,00"


# --- Иное (движимое): стоимость обязательна ---------------------------------
def test_other_movable_kept_with_value(da):
    desc = ("Комплектная автоматизированная линия унифицированной механической "
            "обработки радиаторов отопления № 6, стоимостью 104 817 785,00 руб.")
    obj = da._make_collateral_obj(0, desc)
    assert obj["collateralType"] == "other"
    assert obj["collateralValue"] == "104817785,00"
    assert da._collateral_has_substance(obj) is True


def test_other_garbage_dropped_without_value(da):
    # Болванка переизвлечения без стоимости — не предмет залога.
    for junk in ("Согласно Обзора судебной практики Верховного Суда РФ 1 (2024)",
                 "по доверенности № 177 С/ФЦ от 17.05.2023",
                 "Правовое обоснование требований ПАО Сбербанк"):
        obj = da._make_collateral_obj(0, junk)
        assert da._collateral_has_substance(obj) is False, junk


# --- Разбор блока «в залог передано … имущество: <предметы>» -----------------
def test_pledge_block_items(da):
    text = (
        "в залог передано следующее имущество: \n"
        "Земельный участок площадью 1940 кв. м, с кадастровым номером "
        "34:34:080109:88, стоимостью 1 971 000,00 руб.\n"
        "Расположенное на земельном участке здание, кадастровый номер "
        "34:34:080109:528, стоимостью 20 622 000,00 руб.\n"
        "Общая стоимость переданного в залог имущества составляет 22 593 000,00 руб.\n"
    )
    items = da._extract_pledge_block_items(text)
    assert len(items) == 2
    assert "Земельный участок" in items[0]
    assert "здание" in items[1].lower()
    # итоговая строка «Общая стоимость … составляет …» — не предмет
    assert all("общая стоимост" not in it.lower() for it in items)


def test_pledge_block_summary_movable(da):
    text = ("в залог передано движимое имущество, находящееся по адресу: "
            "г. Волгоград, ул. Бахтурова, 12Л, перечисленное в Приложении № 1 "
            "к Договору залога общей стоимостью 880 000,00 руб.")
    items = da._extract_pledge_block_items(text)
    assert len(items) == 1
    obj = da._make_collateral_obj(0, items[0])
    assert obj["collateralValue"] == "880000,00"
    assert "общей" not in (obj.get("otherDescription") or "").lower()
