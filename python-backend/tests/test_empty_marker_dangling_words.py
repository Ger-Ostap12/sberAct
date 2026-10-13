# -*- coding: utf-8 -*-
"""Пустой маркер не оставляет висячих «от» и «№».

Без даты решения печаталось «Решением … области от Песня Сергей Николаевич
признан», без реквизитов договора залога — «договор залога № от».
"""
import json
import re

import pytest
from docx import Document

from document_generator import DocumentGenerator


@pytest.fixture
def gen():
    return DocumentGenerator()


БАЗА = {
    "caseNumber": "А53-1234/2026",
    "debtorName": "Песня Сергей Николаевич",
    "applicantName": "Песня Сергей Николаевич",
    "creditorName": "ПАО Сбербанк",
    "entityType": "individual",
    "date": "17.07.2026",
    "judge": "Ерёмин Ф.Ф.",
    "managerName": "Шалегин Вячеслав Владимирович",
    "obligations": [],
    "selectedEntityType": "individual",
    "selectedApplicationKind": "rtk",
}


def _текст(gen, акты, залог="no_collateral", **поля):
    data = dict(БАЗА)
    data.update(поля)
    data["selectedCollateralOption"] = залог
    data["selectedActsIds"] = ",".join(акты)
    data["selectedActsData"] = json.dumps(
        [{"id": a, "selected": True, "rtkVariant": "realization"} for a in акты])
    результат = gen.generate("rtk_single_obligation", data)
    assert результат["success"], результат
    куски = []
    for инфо in результат["documents"].values():
        d = Document(инфо["file_path"])
        куски.append("\n".join(p.text for p in d.paragraphs))
    return re.sub(r"\s+", " ", "\n".join(куски))


class TestДатаРешения:
    def test_без_даты_предлог_не_повисает(self, gen):
        текст = _текст(gen, ["final_rtk_inclusion"])
        assert "от Песня Сергей Николаевич" not in текст
        assert "области от Песня" not in текст

    def test_с_датой_фраза_целая(self, gen):
        текст = _текст(gen, ["final_rtk_inclusion"], courtDecisionDate="23.04.2026")
        assert "от 23.04.2026" in текст


class TestДоговорЗалога:
    def test_без_реквизитов_не_остаётся_номер_и_от(self, gen):
        текст = _текст(gen, ["final_rtk_inclusion"], залог="collateral")
        assert "договор залога № от" not in текст
        assert "№ от " not in текст

    def test_с_реквизитами_они_на_месте(self, gen):
        текст = _текст(gen, ["final_rtk_inclusion"], залог="collateral",
                       ipCollateralContractNumber="77-З", ipCollateralContractDate="01.02.2024")
        assert "77-З" in текст
        assert "01.02.2024" in текст
