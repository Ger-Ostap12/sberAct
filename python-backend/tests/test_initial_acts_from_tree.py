"""Первоначальные акты включения в РТК берутся из дерева «Банкротство»."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import bankruptcy_tree  # noqa: E402
from document_generator import DocumentGenerator  # noqa: E402

АКТЫ = list(bankruptcy_tree.INITIAL_ACT_ROLES)


@pytest.fixture
def gen():
    return DocumentGenerator()


def данные(**поля):
    основа = {
        "caseNumber": "А53-1234/2026",
        "debtorName": "Иванов Иван Иванович",
        "applicantName": "Иванов Иван Иванович",
        "creditorName": "ПАО Сбербанк",
        "judge": "Ерёмин Ф.Ф.",
        "date": "17.07.2026",
        "obligations": [],
        "selectedApplicationKind": "rtk",
        "selectedEntityType": "individual",
        "selectedCollateralOption": "collateral",
        "selectedActsIds": ",".join(АКТЫ),
        "selectedActsData": json.dumps([{"id": a, "selected": True} for a in АКТЫ]),
    }
    основа.update(поля)
    return основа


def подобрать(gen, data):
    return gen._map_selected_acts_to_templates(
        data["selectedActsIds"], data["selectedEntityType"],
        data["selectedCollateralOption"], data)


class TestПутиИзДерева:
    @pytest.mark.parametrize("поля,ожидаемая_процедура", [
        ({}, "реализация"),
        ({"final_rtk_inclusion_variant": "restructuring"}, "реструктуризация"),
        ({"selectedEntityType": "legal"}, "наблюдение"),
        ({"selectedEntityType": "kfh"}, "наблюдение"),
    ])
    def test_пять_актов_из_дерева(self, gen, поля, ожидаемая_процедура):
        data = данные(**поля)
        шаблоны, нерешённые = подобрать(gen, data)
        assert нерешённые == [], (нерешённые, data.get("_unresolvedReasons"))
        assert len(шаблоны) == 5, шаблоны
        for сведения in шаблоны.values():
            путь = сведения["path"]
            assert "Банкротство" in путь.parts, путь
            assert "Включение в РТК" in путь.parts, путь
            assert путь.is_file(), путь

    def test_залоговая_папка_при_залоге(self, gen):
        шаблоны, _ = подобрать(gen, данные(selectedCollateralOption="collateral"))
        for сведения in шаблоны.values():
            assert "Залог" in сведения["path"].parts

    def test_беззалоговая_папка_без_залога(self, gen):
        шаблоны, _ = подобрать(gen, данные(selectedCollateralOption="no_collateral"))
        for сведения in шаблоны.values():
            assert "Незалог" in сведения["path"].parts

    def test_статус_юрлица_в_пути(self, gen):
        шаблоны, _ = подобрать(gen, данные(selectedEntityType="legal",
                                           selectedDebtorStatus="liquidation"))
        for сведения in шаблоны.values():
            assert "Ликвидируемый" in сведения["path"].parts

    def test_умерший_в_пути(self, gen):
        шаблоны, _ = подобрать(gen, данные(selectedDebtorStatus="deceased"))
        for сведения in шаблоны.values():
            assert "Умерший" in сведения["path"].parts

    def test_фнс_своя_папка(self, gen):
        шаблоны, _ = подобрать(gen, данные(creditorName="ФНС России",
                                           selectedCollateralOption="no_collateral"))
        assert шаблоны, "у ФНС должны находиться принятие, после Б/Д и Б/Д иное"
        for сведения in шаблоны.values():
            assert "ФНС" in сведения["path"].parts


class TestПроцедураПоДелу:
    """Проверяем и количество: all() по пустому набору истинно и ничего не доказывает."""

    def _имена(self, gen, data, сколько=5):
        шаблоны, нерешённые = подобрать(gen, data)
        assert len(шаблоны) == сколько, (шаблоны, нерешённые, data.get("_unresolvedReasons"))
        return [с["path"].name.lower() for с in шаблоны.values()]

    def test_ликвидируемому_конкурсное(self, gen):
        имена = self._имена(gen, данные(selectedEntityType="legal",
                                        selectedDebtorStatus="liquidation"))
        assert all("конкурс" in имя or "кокнурс" in имя for имя in имена), имена

    def test_отсутствующему_конкурсное(self, gen):
        имена = self._имена(gen, данные(selectedEntityType="kfh",
                                        selectedDebtorStatus="absent"))
        assert all("конкурс" in имя or "кокнурс" in имя for имя in имена), имена

    def test_умершему_реализация(self, gen):
        имена = self._имена(gen, данные(selectedDebtorStatus="deceased"))
        assert all("реализац" in имя for имя in имена), имена

    def test_вариант_вкл_главнее_типа_лица(self, gen):
        имена = self._имена(gen, данные(selectedEntityType="legal",
                                        final_rtk_inclusion_variant="competition"))
        assert all("конкурс" in имя or "кокнурс" in имя for имя in имена), имена

    def test_залог_авто_идёт_в_залоговую_папку(self, gen):
        шаблоны, нерешённые = подобрать(gen, данные(selectedCollateralOption="collateral_auto"))
        assert нерешённые == [], (нерешённые, данные().get("_unresolvedReasons"))
        assert len(шаблоны) == 5
        for сведения in шаблоны.values():
            assert "Залог" in сведения["path"].parts, сведения["path"]


class TestШаблонНеГотов:
    def test_залоговый_акт_в_беззалоговом_деле(self, gen):
        data = данные(selectedCollateralOption="no_collateral")
        _, нерешённые = подобрать(gen, data)
        assert нерешённые == ["acceptance_no_motion_no_duty_collateral"]
        assert "нет акта роли" in data["_unresolvedReasons"]["acceptance_no_motion_no_duty_collateral"]

    def test_нет_гп_у_фнс(self, gen):
        data = данные(creditorName="ФНС России", selectedCollateralOption="no_collateral")
        _, нерешённые = подобрать(gen, data)
        assert "acceptance_no_motion_no_duty" in нерешённые
        assert data["_unresolvedReasons"]["acceptance_no_motion_no_duty"]

    def test_причина_уходит_в_предупреждения(self, gen):
        data = данные(selectedCollateralOption="no_collateral")
        результат = gen.generate("rtk_single_obligation", data)
        assert результат["success"], результат
        предупреждения = результат.get("warnings") or []
        assert any("шаблон не готов" in w for w in предупреждения), предупреждения


class TestИнициированиеНеТронуто:
    def test_другой_вид_заявления_идёт_прежним_путём(self, gen):
        # Инициирование подключаем следующим этапом: оси дерева не считаем.
        data = данные(selectedApplicationKind="other")
        оси = gen._bankruptcy_tree_axes(data, "individual", "no_collateral", АКТЫ)
        assert оси is None
        шаблоны, _ = подобрать(gen, data)
        assert шаблоны, "старые ветки маппинга должны отработать как раньше"
        assert all("Включение в РТК" not in с["path"].parts for с in шаблоны.values())

    def test_самобанкрот_не_идёт_в_дерево(self, gen):
        data = данные(selectedApplicationKind="self")
        assert gen._bankruptcy_tree_axes(data, "individual", "no_collateral", АКТЫ) is None


class TestСквозная:
    def test_акт_принятия_генерируется_из_дерева(self, gen):
        одна_галка = ["acceptance_definition"]
        data = данные(
            selectedActsIds=",".join(одна_галка),
            selectedActsData=json.dumps([{"id": a, "selected": True} for a in одна_галка]),
        )
        результат = gen.generate("rtk_single_obligation", data)
        assert результат["success"], результат
        assert результат["count"] == 1, результат
        сведения = next(iter(результат["documents"].values()))
        assert сведения["name"] == "Определение о принятии"
