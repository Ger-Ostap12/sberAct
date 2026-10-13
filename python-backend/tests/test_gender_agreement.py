# -*- coding: utf-8 -*-
"""Согласование глагола с родом: «утверждена» у женщины, «утвержден» у мужчины.

Род зашит в шаблон, а лицо бывает любым: в акте Андрея печаталось
«Финансовым управляющим утвержден Рябинина Екатерина Алексеевна».
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
    "debtorName": "Анохина Маргарита Николаевна",
    "applicantName": "Анохина Маргарита Николаевна",
    "creditorName": "ПАО Сбербанк",
    "entityType": "individual",
    "date": "17.07.2026",
    "judge": "Ерёмин Ф.Ф.",
    "obligations": [],
    "selectedEntityType": "individual",
    "selectedCollateralOption": "no_collateral",
    "selectedApplicationKind": "rtk",
}


def _текст(gen, акты, **поля):
    data = dict(БАЗА)
    data.update(поля)
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


class TestУправляющий:
    def test_женщина_утверждена(self, gen):
        текст = _текст(gen, ["acceptance_definition"], managerName="Рябинина Екатерина Алексеевна")
        assert "утверждена Рябинина Екатерина Алексеевна" in текст
        assert "утвержден Рябинина" not in текст

    def test_мужчина_утвержден(self, gen):
        текст = _текст(gen, ["acceptance_definition"], managerName="Шалегин Вячеслав Владимирович")
        assert "утвержден Шалегин Вячеслав Владимирович" in текст
        assert "утверждена Шалегин" not in текст

    def test_род_по_фамилии_без_отчества(self, gen):
        текст = _текст(gen, ["acceptance_definition"], managerName="Рябинина Е.А.")
        assert "утверждена Рябинина Е.А." in текст

    def test_несклоняемая_фамилия_оставляет_форму_шаблона(self, gen):
        # Род неизвестен — форму шаблона не трогаем, иначе угадывание вместо факта.
        # В этом шаблоне написано «утверждена», и она остаётся.
        текст = _текст(gen, ["acceptance_definition"], managerName="Жигало А.")
        assert "утверждена Жигало А." in текст

    def test_инициал_не_принимается_за_женское_имя(self, gen):
        # «Жигало А.»: разбор имени по инициалу давал femn, и мужчина становился
        # женщиной. Теперь сокращённая запись рода не даёт вовсе.
        текст = _текст(gen, ["acceptance_definition"], managerName="Иванов И.И.")
        assert "утвержден Иванов И.И." in текст
        assert "утверждена Иванов" not in текст


class TestДолжник:
    def test_женщина_признана(self, gen):
        текст = _текст(gen, ["final_rtk_inclusion"], managerName="Шалегин Вячеслав Владимирович")
        assert "признана несостоятельным" in текст or "признана" in текст
        assert "Анохина Маргарита Николаевна признан " not in текст

    def test_мужчина_признан(self, gen):
        текст = _текст(gen, ["final_rtk_inclusion"],
                       debtorName="Базов Георгий Николаевич",
                       applicantName="Базов Георгий Николаевич",
                       managerName="Шалегин Вячеслав Владимирович")
        assert "признана" not in текст

    def test_организацию_не_трогаем(self, gen):
        # У юрлица в шаблоне «общество признано» — своя форма, в неё не лезем.
        текст = _текст(gen, ["final_rtk_inclusion"],
                       debtorName="ООО «СПОРТ»", applicantName="ООО «СПОРТ»",
                       entityType="legal", selectedEntityType="legal",
                       managerName="Шалегин Вячеслав Владимирович")
        assert "признана" not in текст
