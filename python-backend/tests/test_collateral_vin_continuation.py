# -*- coding: utf-8 -*-
"""Строка «VIN …» — продолжение предмета залога, а не второй предмет (22.09.2026).

свежие-20: один автомобиль разорван переносом строки в просительной части —
«…обеспеченного залогом автомобиля марки VOLKSWAGEN модель Jetta 2013 г.в.» /
«VIN-номер XW8ZZZ16ZEN900156, - в размере 1014095.33, из которых:». Предметы
залога режутся ПО СТРОКАМ (`_split_collateral_items`), поэтому получалось две
карточки: первая без VIN, вторая — из одного VIN.

VIN сам по себе предметом не бывает: это атрибут автомобиля, названного выше.
Замер по 101 документу: строка, начинающаяся с «VIN», встречается один раз —
в свежие-20.
"""
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from document_analyzer import DocumentAnalyzer  # noqa: E402


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


СВЕЖИЕ_20 = (
    '1. Включить в третью очередь реестра требований кредиторов должника '
    'СЫТНИК МАКСИМ ВИК-ТОРОВИЧ денежное требование ПАО "Совкомбанк" в рамках '
    'кредитного договора: № 11937369169 от "26" января 2025 года , '
    'обеспеченного залогом автомобиля марки VOLKSWAGEN модель Jetta 2013 г.в.\n'
    'VIN-номер XW8ZZZ16ZEN900156, - в размере 1014095.33, из которых:\n'
    '772889.48 руб. - основной долг,\n')


def test_vin_приклеивается_к_предыдущему_предмету(analyzer):
    предметы = analyzer._split_collateral_items(СВЕЖИЕ_20)
    assert len(предметы) == 2, предметы
    assert предметы[0].endswith("VIN-номер XW8ZZZ16ZEN900156, - в размере 1014095.33, из которых:")
    assert "VOLKSWAGEN" in предметы[0]


def test_один_автомобиль_даёт_одну_карточку(analyzer):
    карточки = [analyzer._make_collateral_obj(i, d)
                for i, d in enumerate(analyzer._split_collateral_items(СВЕЖИЕ_20))]
    авто = [c for c in карточки if c.get("collateralType") == "auto"]
    assert len(авто) == 1
    assert авто[0]["vin"] == "XW8ZZZ16ZEN900156"


# --- чего правило ломать НЕ должно ---------------------------------------------

def test_первой_строкой_vin_не_приклеивается_никуда(analyzer):
    """Клеить не к чему — строка остаётся самостоятельным предметом."""
    предметы = analyzer._split_collateral_items(
        "VIN: XW8ZZZ16ZEN900156, автомобиль VOLKSWAGEN Jetta\n")
    assert предметы == ["VIN: XW8ZZZ16ZEN900156, автомобиль VOLKSWAGEN Jetta"]


def test_vin_внутри_строки_ничего_не_меняет(analyzer):
    """Обычная вёрстка — VIN в той же строке; предметов столько же, сколько строк."""
    предметы = analyzer._split_collateral_items(
        "Автомобиль LADA Granta 2019 г.в., VIN XTA219010K0512345\n"
        "Автомобиль KIA Rio 2020 г.в., VIN Z94C251BALR123456\n")
    assert len(предметы) == 2


def test_слово_на_vin_не_похожее_не_клеится(analyzer):
    """Якорь по границе слова: «VINоград» продолжением не считается."""
    предметы = analyzer._split_collateral_items(
        "Автомобиль LADA Granta 2019 г.в.\nVINоградник площадью 300 кв.м\n")
    assert len(предметы) == 2
