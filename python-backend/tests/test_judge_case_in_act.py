# -*- coding: utf-8 -*-
"""Падежи судьи и ведущего протокол доезжают до готового акта."""
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
    "debtorName": "Иванов Иван Иванович",
    "applicantName": "Иванов Иван Иванович",
    "creditorName": "ПАО Сбербанк",
    "entityType": "individual",
    "date": "17.07.2026",
    "obligations": [],
    "selectedEntityType": "individual",
    "selectedCollateralOption": "no_collateral",
    "selectedApplicationKind": "rtk",
}


def _текст(gen, акты, **поля):
    data = dict(БАЗА)
    data.update(поля)
    data["selectedActsIds"] = ",".join(акты)
    data["selectedActsData"] = json.dumps([{"id": a, "selected": True} for a in акты])
    результат = gen.generate("rtk_single_obligation", data)
    assert результат["success"], результат
    куски = []
    for инфо in результат["documents"].values():
        d = Document(инфо["file_path"])
        куски.append("\n".join(p.text for p in d.paragraphs))
    return re.sub(r"\s+", " ", "\n".join(куски))


class TestСудья:
    def test_в_составе_судьи_родительный(self, gen):
        текст = _текст(gen, ["acceptance_definition"],
                       judge="Ерёмин Ф.Ф.", judgeFullName="Ерёмин Филипп Фёдорович")
        assert "в составе судьи Ерёмина Ф.Ф." in текст
        assert "в составе судьи Ерёмин Ф.Ф." not in текст

    def test_подпись_остаётся_именительной(self, gen):
        текст = _текст(gen, ["acceptance_definition"],
                       judge="Ерёмин Ф.Ф.", judgeFullName="Ерёмин Филипп Фёдорович")
        assert "Судья Ерёмин Ф.Ф." in текст

    def test_женская_фамилия_по_справочнику(self, gen):
        текст = _текст(gen, ["acceptance_definition"],
                       judge="Власова Н.Ю.", judgeFullName="Власова Наталья Юрьевна")
        assert "в составе судьи Власовой Н.Ю." in текст

    def test_без_полного_фио_род_берётся_по_фамилии(self, gen):
        текст = _текст(gen, ["acceptance_definition"], judge="Иванов И.И.")
        assert "в составе судьи Иванова И.И." in текст

    def test_несклоняемая_фамилия_не_портится(self, gen):
        текст = _текст(gen, ["acceptance_definition"], judge="Жигало Н.А.")
        assert "в составе судьи Жигало Н.А." in текст


class TestВедущийПротокол:
    def test_помощником_творительный(self, gen):
        текст = _текст(gen, ["intermediate_postponement"],
                       judge="Ерёмин Ф.Ф.", judgeFullName="Ерёмин Филипп Фёдорович",
                       authorName="Помощникова Ф.А.", authorRole="помощник")
        assert "Помощниковой Ф.А." in текст
        assert "помощником судебного заседания Помощникова Ф.А." not in текст

    def test_секретарем_творительный(self, gen):
        текст = _текст(gen, ["intermediate_postponement"],
                       judge="Ерёмин Ф.Ф.", authorName="Секретарева С.В.", authorRole="секретарь")
        assert "Секретаревой С.В." in текст

    def test_мужская_фамилия_ведущего(self, gen):
        текст = _текст(gen, ["intermediate_postponement"],
                       judge="Ерёмин Ф.Ф.", authorName="Иванов И.И.", authorRole="секретарь")
        assert "Ивановым И.И." in текст


class TestПустыеЗначения:
    def test_без_судьи_маркер_не_оставляет_мусора(self, gen):
        текст = _текст(gen, ["acceptance_definition"])
        assert "[415]" not in текст

    def test_без_ведущего_протокол_маркер_не_остаётся(self, gen):
        текст = _текст(gen, ["intermediate_postponement"], judge="Ерёмин Ф.Ф.")
        assert "[29]" not in текст
