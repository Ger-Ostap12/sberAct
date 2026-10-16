"""Акты инициирования ФЛ берутся из дерева «Банкротство/Инициирование»."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import bankruptcy_tree  # noqa: E402
from document_generator import DocumentGenerator  # noqa: E402

ПЕРВОНАЧАЛЬНЫЕ = [a for a in bankruptcy_tree.INITIAL_ACT_ROLES
                  if a != "acceptance_no_motion_no_duty_collateral"]
ПРОМЕЖУТОЧНЫЕ = [a for a in bankruptcy_tree.INTERMEDIATE_ACT_ROLES
                 if a != "intermediate_simplified_to_main"]
ФИНАЛЬНЫЕ = list(bankruptcy_tree.INITIATION_FINAL_ROLES)


@pytest.fixture
def gen():
    return DocumentGenerator()


def данные(акты, **поля):
    основа = {
        "caseNumber": "А53-1234/2026",
        "debtorName": "Иванов Иван Иванович",
        "applicantName": "Иванов Иван Иванович",
        "creditorName": "ПАО Сбербанк",
        "judge": "Ерёмин Ф.Ф.",
        "date": "17.07.2026",
        "obligations": [],
        "selectedApplicationKind": "other",
        "selectedEntityType": "individual",
        "selectedCollateralOption": "no_collateral",
        "selectedActsIds": ",".join(акты),
        "selectedActsData": json.dumps([{"id": a, "selected": True} for a in акты]),
    }
    основа.update(поля)
    return основа


def подобрать(gen, data):
    return gen._map_selected_acts_to_templates(
        data["selectedActsIds"], data["selectedEntityType"],
        data["selectedCollateralOption"], data)


def пути(шаблоны):
    return [с["path"] for с in шаблоны.values()]


class TestВеткаИнициирования:
    @pytest.mark.parametrize("акты", [ПЕРВОНАЧАЛЬНЫЕ, ПРОМЕЖУТОЧНЫЕ, ФИНАЛЬНЫЕ])
    def test_все_акты_находятся(self, gen, акты):
        data = данные(акты)
        шаблоны, нерешённые = подобрать(gen, data)
        assert нерешённые == [], (нерешённые, data.get("_unresolvedReasons"))
        assert len(шаблоны) == len(акты), шаблоны
        for путь in пути(шаблоны):
            assert "Инициирование" in путь.parts, путь
            assert "Включение в РТК" not in путь.parts, путь
            assert путь.is_file(), путь

    def test_залоговая_папка_при_залоге(self, gen):
        шаблоны, _ = подобрать(gen, данные(ПЕРВОНАЧАЛЬНЫЕ,
                                           selectedCollateralOption="collateral"))
        assert len(шаблоны) == len(ПЕРВОНАЧАЛЬНЫЕ)
        for путь in пути(шаблоны):
            assert "Залог" in путь.parts, путь

    def test_умерший_без_подпапки_залога(self, gen):
        """У умершего в инициировании подпапок залога нет, в отличие от РТК."""
        шаблоны, нерешённые = подобрать(gen, данные(ПРОМЕЖУТОЧНЫЕ,
                                                    selectedDebtorStatus="deceased"))
        assert нерешённые == []
        assert len(шаблоны) == len(ПРОМЕЖУТОЧНЫЕ)
        for путь in пути(шаблоны):
            assert "Умерший" in путь.parts, путь
            assert "залог" not in [ч.lower() for ч in путь.parts], путь

    def test_самобанкрот_своя_папка(self, gen):
        шаблоны, нерешённые = подобрать(gen, данные(ПЕРВОНАЧАЛЬНЫЕ,
                                                    selectedApplicationKind="self"))
        assert нерешённые == []
        for путь in пути(шаблоны):
            assert "Самобанкрот" in путь.parts, путь

    def test_у_самобанкрота_оба_возврата(self, gen):
        """Файлы «возврат инициирование ГП» и «возврат инициирование» — разные акты."""
        акты = ["intermediate_return_no_duty", "intermediate_return_general"]
        шаблоны, нерешённые = подобрать(gen, данные(акты, selectedApplicationKind="self"))
        assert нерешённые == []
        имена = {с["path"].name for с in шаблоны.values()}
        assert len(имена) == 2, имена
        без_гп = шаблоны["return_no_duty"]["path"].name.lower()
        общий = шаблоны["return_general"]["path"].name.lower()
        assert "гп" in без_гп and "гп" not in общий, (без_гп, общий)


class TestФинальныеАкты:
    def test_процедуру_задаёт_акт_а_не_дело(self, gen):
        """Юрист может выбрать оба решения сразу — каждое из своей папки."""
        шаблоны, нерешённые = подобрать(gen, данные(ФИНАЛЬНЫЕ))
        assert нерешённые == []
        assert "Реализация" in шаблоны["final_realization"]["path"].parts
        assert "Реструктуризация" in шаблоны["final_restructuring"]["path"].parts

    def test_у_умершего_только_реализация(self, gen):
        data = данные(["final_realization"], selectedDebtorStatus="deceased")
        шаблоны, нерешённые = подобрать(gen, data)
        assert нерешённые == []
        путь = шаблоны["final_realization"]["path"]
        assert "Умерший" in путь.parts and "Реализация" in путь.parts, путь

    def test_самобанкроту_полный_текст(self, gen):
        шаблоны, нерешённые = подобрать(gen, данные(ФИНАЛЬНЫЕ,
                                                    selectedApplicationKind="self"))
        assert нерешённые == []
        for путь in пути(шаблоны):
            assert "Самобанкрот" in путь.parts, путь
            assert "полный текст" in путь.name.lower(), путь


class TestЧужиеВеткиНеТронуты:
    @pytest.mark.parametrize("поля", [
        pytest.param({"selectedEntityType": "legal"}, id="юрлицо"),
        pytest.param({"creditorName": "ФНС России"}, id="фнс"),
    ])
    def test_чужое_лицо_идёт_по_старым_путям(self, gen, поля):
        """Из инициирования подключена только папка ФЛ кредиторов и самобанкрота."""
        data = данные(ПЕРВОНАЧАЛЬНЫЕ, **поля)
        шаблоны, нерешённые = подобрать(gen, data)
        # Пустой набор прошёл бы проверку путей молча: сверяем и количество.
        assert нерешённые == [], (нерешённые, data.get("_unresolvedReasons"))
        assert шаблоны, "старые пути должны отдать шаблоны"
        for путь in пути(шаблоны):
            assert "Инициирование" not in путь.parts, путь

    def test_включение_в_ртк_не_берётся_из_инициирования(self, gen):
        data = данные(["final_rtk_inclusion"])
        шаблоны, нерешённые = подобрать(gen, data)
        assert нерешённые == [], (нерешённые, data.get("_unresolvedReasons"))
        assert len(шаблоны) == 1, шаблоны
        for путь in пути(шаблоны):
            assert "Инициирование" not in путь.parts, путь
