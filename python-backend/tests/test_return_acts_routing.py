# -*- coding: utf-8 -*-
"""Два акта возврата: общий и без госпошлины, шаблон по виду заявления.

У самобанкрота возврата без госпошлины не бывает — акт не генерируется даже
если он пришёл в выбранных.
"""
import json

import pytest

from document_generator import DocumentGenerator


@pytest.fixture
def gen():
    return DocumentGenerator()


BASE = {
    "caseNumber": "А53-1234/2026",
    "debtorName": "Иванов Иван Иванович",
    "applicantName": "Иванов Иван Иванович",
    "creditorName": "ПАО Сбербанк",
    "entityType": "individual",
    "date": "17.07.2026",
    "judge": "Петров П.П.",
    "obligations": [],
}


def _сгенерировать(gen, акты, вид):
    data = dict(BASE)
    data.update(
        selectedActsIds=",".join(акты),
        selectedActsData=json.dumps([{"id": a, "selected": True} for a in акты]),
        selectedEntityType="individual",
        selectedCollateralOption="no_collateral",
        selectedApplicationKind=вид,
    )
    return gen.generate("rtk_single_obligation", data)


class TestВыборШаблона:
    @pytest.mark.parametrize("вид,ожидаем", [
        ("rtk", "возврат ртк.docx"),
        ("other", "возврат инициирование.docx"),
        ("self", "возврат инициирование.docx"),
    ])
    def test_общий_возврат(self, gen, вид, ожидаем, monkeypatch):
        пути = []
        исходный = gen._resolve_template_path

        def перехват(path, *a, **kw):
            пути.append(str(path))
            return исходный(path, *a, **kw)

        monkeypatch.setattr(gen, "_resolve_template_path", перехват)
        результат = _сгенерировать(gen, ["intermediate_return_general"], вид)
        assert результат["success"]
        assert any(ожидаем in p for p in пути), пути

    @pytest.mark.parametrize("вид,ожидаем", [
        ("rtk", "возврат ртк ГП.docx"),
        ("other", "возврат инициирование ГП.docx"),
    ])
    def test_возврат_без_пошлины(self, gen, вид, ожидаем, monkeypatch):
        пути = []
        исходный = gen._resolve_template_path

        def перехват(path, *a, **kw):
            пути.append(str(path))
            return исходный(path, *a, **kw)

        monkeypatch.setattr(gen, "_resolve_template_path", перехват)
        результат = _сгенерировать(gen, ["intermediate_return_no_duty"], вид)
        assert результат["success"]
        assert any(ожидаем in p for p in пути), пути


class TestСамобанкрот:
    def test_возврат_без_пошлины_не_генерируется(self, gen):
        результат = _сгенерировать(gen, ["intermediate_return_no_duty"], "self")
        # Единственный выбранный акт самобанкроту не положен — документов нет.
        assert результат.get("count", 0) == 0 or "return_no_duty" not in результат.get("documents", {})

    def test_общий_возврат_самобанкроту_положен(self, gen):
        результат = _сгенерировать(gen, ["intermediate_return_general"], "self")
        assert результат["success"]
        assert "return_general" in результат["documents"]


class TestДваАктаВместе:
    def test_оба_возврата_дают_два_документа(self, gen):
        результат = _сгенерировать(
            gen, ["intermediate_return_general", "intermediate_return_no_duty"], "rtk")
        assert результат["success"]
        assert set(результат["documents"]) == {"return_general", "return_no_duty"}

    def test_у_самобанкрота_остаётся_только_общий(self, gen):
        результат = _сгенерировать(
            gen, ["intermediate_return_general", "intermediate_return_no_duty"], "self")
        assert результат["success"]
        assert set(результат["documents"]) == {"return_general"}
