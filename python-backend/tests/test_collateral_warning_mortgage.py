# -*- coding: utf-8 -*-
"""Ложное «залог не найден» на ипотеке (23.09.2026).

Предупреждение о залоге сравнивало ожидание по типу документа с `collaterals`,
а у ипотеки предметы живут ОТДЕЛЬНЫМ массивом `mortgageProperties`. На корпус-6
(военная ипотека, жилой дом + земельный участок) залог разобран полностью, а
юрист видел «Тип документа предполагает наличие залога, но по извлечённым
данным залог не найден».

Замер по 101 документу: это было ЕДИНСТВЕННОЕ предупреждение о залоге вообще,
и оно было ложным. После правки — ни одного.

⚠️ Порядок вычислений: `mortgage_properties` собирается ПОЗЖЕ в `analyze_from_text`,
поэтому блок предупреждения перенесён ниже сборки. Проверка, которая смотрит на
незаполненную ещё переменную, молча даёт прежний ложный результат.
"""
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from classify_mixin import (  # noqa: E402
    _collateral_expected_from_document_type,
    collateral_found,
)

ДОМ = {"id": "mp-0", "objectName": "Жилой дом", "cadastralNumber": "20:09:0000000:1111"}
УЧАСТОК = {"id": "mp-1", "objectName": "Земельный участок",
           "cadastralNumber": "20:09:0000000:2222"}
АВТО = {"id": "collateral-0", "collateralType": "auto", "vin": "XW8ZZZ16ZEN900156"}


def test_предметы_ипотеки_считаются_залогом():
    """Корень дефекта: корпус-6 — два предмета в mortgageProperties, collaterals пуст."""
    assert collateral_found([], [ДОМ, УЧАСТОК])


def test_обычный_залог_считается_как_прежде():
    assert collateral_found([АВТО], [])


def test_оба_массива_пусты_залога_нет():
    assert not collateral_found([], [])


@pytest.mark.parametrize("залоги, предметы", [(None, None), ([], None), (None, [])])
def test_отсутствующие_массивы_не_ломают_проверку(залоги, предметы):
    assert not collateral_found(залоги, предметы)


def test_ипотека_предполагает_залог():
    """Без этого ожидания предупреждение не зажглось бы вовсе — стережём связку."""
    assert _collateral_expected_from_document_type("mortgage_claim") is True


def test_предупреждение_на_ипотеке_без_предметов_остаётся():
    """Правило не должно ГЛУШИТЬ предупреждение: пустая ипотека обязана краснеть."""
    ожидание = _collateral_expected_from_document_type("mortgage_claim")
    assert ожидание is not None and ожидание != collateral_found([], [])


def test_предупреждения_на_разобранной_ипотеке_нет():
    ожидание = _collateral_expected_from_document_type("mortgage_claim")
    assert ожидание == collateral_found([], [ДОМ, УЧАСТОК])


def test_тип_без_ожидания_не_сравнивается():
    """rtk/initiation не гарантируют ни наличия, ни отсутствия залога."""
    assert _collateral_expected_from_document_type("rtk_application") is None
