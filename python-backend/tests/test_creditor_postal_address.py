# -*- coding: utf-8 -*-
"""Почтовый адрес кредитора [995]: вводится вручную, доезжает до акта."""
import json
import re

import pytest
from docx import Document

from document_generator import DocumentGenerator

ПОЧТОВЫЙ = "109052, г. Москва, ул. Смирновская, д. 10, стр. 22"


@pytest.fixture
def gen():
    return DocumentGenerator()


БАЗА = {
    "caseNumber": "А53-1234/2026",
    "debtorName": "Иванов Иван Иванович",
    "applicantName": "Иванов Иван Иванович",
    "creditorName": "ПАО Сбербанк",
    "creditorAddress": "117312, г. Москва, ул. Вавилова, д. 19",
    "entityType": "individual",
    "date": "17.07.2026",
    "judge": "Ерёмин Ф.Ф.",
    "obligations": [],
    "selectedEntityType": "individual",
    "selectedCollateralOption": "collateral",
    "selectedApplicationKind": "rtk",
}

# Маркер стоит в двух шаблонах принятия по залоговому включению в РТК.
АКТЫ = ["acceptance_definition"]


def _текст(gen, **поля):
    data = dict(БАЗА)
    data.update(поля)
    data["selectedActsIds"] = ",".join(АКТЫ)
    data["selectedActsData"] = json.dumps(
        [{"id": a, "selected": True, "rtkVariant": "realization"} for a in АКТЫ])
    результат = gen.generate("rtk_single_obligation", data)
    assert результат["success"], результат
    куски = []
    for инфо in результат["documents"].values():
        d = Document(инфо["file_path"])
        куски.append("\n".join(p.text for p in d.paragraphs))
    return re.sub(r"\s+", " ", "\n".join(куски))


def test_почтовый_адрес_попадает_в_акт(gen):
    текст = _текст(gen, creditorPostalAddress=ПОЧТОВЫЙ)
    assert ПОЧТОВЫЙ in текст
    assert "[995]" not in текст


def test_юридический_и_почтовый_не_путаются(gen):
    текст = _текст(gen, creditorPostalAddress=ПОЧТОВЫЙ)
    assert "почтовый адрес: " + ПОЧТОВЫЙ in текст
    assert "юридический адрес: 117312, г. Москва, ул. Вавилова, д. 19" in текст


def test_пустой_адрес_не_оставляет_маркер(gen):
    текст = _текст(gen)
    assert "[995]" not in текст


def test_поле_не_извлекается_из_заявления(gen):
    # Источник только один — ручной ввод; разбор его не заполняет.
    import document_analyzer
    анализатор = document_analyzer.DocumentAnalyzer()
    поля = анализатор.analyze_from_text(
        "Кредитор: ПАО Сбербанк, почтовый адрес: 109052, г. Москва", "x.docx")
    assert not (поля.get("fields") or {}).get("creditorPostalAddress")
