# -*- coding: utf-8 -*-
"""Тесты разбивки полей финансов на слагаемые (`financeBreakdown`) — для тултипа
«откуда число».

`_apply_prayer_finances` кладёт разбивку во временный ключ `fields["financeBreakdown"]`
(analyze() поднимает его в top-level). ОДНО слагаемое — тоже разбивка («взято из
документа как есть»): тултип нужен на всех не-ФНС заявлениях (требование Андрея).
Нулевые слагаемые не выводим.
"""
import pytest
from document_analyzer import DocumentAnalyzer


@pytest.fixture(scope="module")
def da():
    return DocumentAnalyzer()


def test_breakdown_two_obligations(da):
    # Два верхнеуровневых блока «включить … в размере SUB …, из которых: …».
    text = (
        "просим суд "
        "включить в реестр требований в размере 547 583 112,57 рублей, из которых: "
        "465 015 355,26 рублей задолженность за просроченный кредит, "
        "82 567 757,31 рублей просроченная задолженность по процентам. "
        "включить в реестр требований в размере 1 102 505 689,29 рублей, из которых: "
        "999 998 250,73 рублей задолженность за просроченный кредит, "
        "102 507 438,56 рублей просроченная задолженность по процентам."
    )
    fields = {}
    da._apply_prayer_finances(fields, text)
    br = fields.get("financeBreakdown")
    assert br is not None
    # Осн.долг = сумма двух блоков; в разбивке — оба слагаемых по порядку.
    assert br["principalDebt"] == ["465 015 355,26", "999 998 250,73"]
    assert br["interest"] == ["82 567 757,31", "102 507 438,56"]
    # Итог поля = сумме слагаемых.
    assert fields["principalDebt"] == "1 465 013 605,99"


def test_breakdown_single_obligation(da):
    # Одно обязательство → одно слагаемое на категорию: разбивка есть (источник
    # числа виден и когда сумма взята из документа как есть — кейс Форте Хоум).
    text = (
        "просим суд включить в реестр требований в размере 100 000,00 рублей, из которых: "
        "90 000,00 рублей задолженность за просроченный кредит, "
        "10 000,00 рублей просроченная задолженность по процентам."
    )
    fields = {}
    da._apply_prayer_finances(fields, text)
    br = fields.get("financeBreakdown")
    assert br is not None
    assert br["principalDebt"] == ["90 000,00"]
    assert br["interest"] == ["10 000,00"]


def test_analyze_forte_home_single_addends(da):
    # Интеграционно (кейс Андрея, Форте Хоум): просительная с одним блоком сумм →
    # analyze() отдаёт top-level financeBreakdown с единичными слагаемыми,
    # тултип «откуда число» есть и без суммирования.
    import glob
    import os
    corpus = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Заявления"))
    hits = [f for f in glob.glob(os.path.join(corpus, "**", "*Форте Хоум*.docx"), recursive=True)
            if "~$" not in f]
    if not hits:
        pytest.skip("файл Форте Хоум не найден в корпусе (перемещён)")
    r = da.analyze(hits[0])
    br = r.get("financeBreakdown")
    assert br is not None
    assert br["principalDebt"] == ["4 463 145 841,47"]
    assert br["interest"] == ["518 326 017,27"]
    assert br["forfeit"] == ["51 072 996,85"]
    # Временный ключ не должен оставаться в fields (и утекать в golden/editedFields).
    assert "financeBreakdown" not in r["fields"]
