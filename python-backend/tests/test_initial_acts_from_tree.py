"""Акты включения в РТК берутся из дерева «Банкротство»: первоначальные и промежуточные."""

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


ПРОМЕЖУТОЧНЫЕ = list(bankruptcy_tree.INTERMEDIATE_ACT_ROLES)


class TestПромежуточные:
    def _подобрать(self, gen, **поля):
        data = данные(selectedActsIds=",".join(ПРОМЕЖУТОЧНЫЕ),
                      selectedActsData=json.dumps(
                          [{"id": a, "selected": True} for a in ПРОМЕЖУТОЧНЫЕ]),
                      **поля)
        шаблоны, нерешённые = подобрать(gen, data)
        return шаблоны, нерешённые, data

    def test_шесть_актов_из_дерева(self, gen):
        шаблоны, нерешённые, data = self._подобрать(gen)
        assert нерешённые == [], (нерешённые, data.get("_unresolvedReasons"))
        assert len(шаблоны) == len(ПРОМЕЖУТОЧНЫЕ)
        for сведения in шаблоны.values():
            assert "Промежуточные" in сведения["path"].parts, сведения["path"]
            assert сведения["path"].is_file()

    def test_два_отложения_разные_файлы(self, gen):
        шаблоны, _, _ = self._подобрать(gen)
        общее = шаблоны["postponement"]["path"].name
        третье = шаблоны["postponement_third_party"]["path"].name
        assert общее != третье
        assert "3 лицо" in третье and "3 лицо" not in общее

    def test_файл_на_две_процедуры_годится_обеим(self, gen):
        # «Отложение рестр+реал» подходит и реализации, и реструктуризации.
        реализация, _, _ = self._подобрать(gen)
        реструктуризация, _, _ = self._подобрать(gen, final_rtk_inclusion_variant="restructuring")
        assert реализация["postponement"]["path"] == реструктуризация["postponement"]["path"]
        assert "рестр+реал" in реализация["postponement"]["path"].name

    def test_залог_влияет_на_выбор(self, gen):
        с_залогом, _, _ = self._подобрать(gen, selectedCollateralOption="collateral")
        без_залога, _, _ = self._подобрать(gen, selectedCollateralOption="no_collateral")
        assert "залог" in с_залогом["postponement"]["path"].name.lower()
        assert с_залогом["postponement"]["path"] != без_залога["postponement"]["path"]

    def test_возврат_без_гп_у_фнс_не_готов(self, gen):
        _, нерешённые, data = self._подобрать(gen, creditorName="ФНС России",
                                              selectedCollateralOption="no_collateral")
        assert нерешённые == ["intermediate_return_no_duty"]
        assert data["_unresolvedReasons"]["intermediate_return_no_duty"]

    def test_продление_упрощёнки_не_готово_всегда(self, gen):
        акты = ["intermediate_extend_simplified"]
        data = данные(selectedActsIds=",".join(акты),
                      selectedActsData=json.dumps([{"id": a, "selected": True} for a in акты]))
        шаблоны, нерешённые = подобрать(gen, data)
        assert шаблоны == {}
        assert нерешённые == акты
        assert "в дереве нет" in data["_unresolvedReasons"]["intermediate_extend_simplified"]


class TestФинальныеАкты:
    def _подобрать(self, gen, акты=("final_rtk_inclusion",), **поля):
        data = данные(selectedActsIds=",".join(акты),
                      selectedActsData=json.dumps(
                          [{"id": a, "selected": True} for a in акты]),
                      **поля)
        шаблоны, нерешённые = подобрать(gen, data)
        return шаблоны, нерешённые, data

    def test_включение_из_папки_процедуры(self, gen):
        шаблоны, нерешённые, _ = self._подобрать(gen)
        assert нерешённые == []
        путь = шаблоны["rtk_inclusion"]["path"]
        assert "Реализация" in путь.parts, путь
        assert "полный текст" in путь.name.lower()

    def test_вариант_меняет_папку(self, gen):
        шаблоны, _, _ = self._подобрать(gen, final_rtk_inclusion_variant="restructuring")
        assert "Реструктуризация" in шаблоны["rtk_inclusion"]["path"].parts

    def test_юрлицу_наблюдение_и_конкурсное(self, gen):
        наблюдение, _, _ = self._подобрать(gen, selectedEntityType="legal")
        конкурс, _, _ = self._подобрать(gen, selectedEntityType="legal",
                                        selectedDebtorStatus="liquidation")
        assert "Наблюдение" in наблюдение["rtk_inclusion"]["path"].parts
        assert "Конкурсное" in конкурс["rtk_inclusion"]["path"].parts

    def test_короткий_текст_резолютивка(self, gen):
        шаблоны, нерешённые, _ = self._подобрать(gen, selectedShortText="true")
        assert нерешённые == []
        путь = шаблоны["short_text"]["path"]
        assert "Банкротство" in путь.parts, путь
        assert путь.is_file(), путь
        assert "резолютив" in путь.name.lower()

    def test_у_умершего_залог_различается_именем(self, gen):
        # В папке «Умерший\Реализация» лежат оба вида актов сразу.
        с_залогом, _, _ = self._подобрать(gen, selectedDebtorStatus="deceased",
                                          selectedCollateralOption="collateral")
        без_залога, _, _ = self._подобрать(gen, selectedDebtorStatus="deceased",
                                           selectedCollateralOption="no_collateral")
        путь_с = с_залогом["rtk_inclusion"]["path"]
        путь_без = без_залога["rtk_inclusion"]["path"]
        assert путь_с.parent == путь_без.parent, "оба лежат в одной папке"
        assert "залог" in путь_с.name.lower()
        assert "залог" not in путь_без.name.lower()

    def test_без_залога_не_берётся_залоговый(self, gen):
        шаблоны, _, _ = self._подобрать(gen, selectedCollateralOption="no_collateral")
        assert "залог" not in шаблоны["rtk_inclusion"]["path"].name.lower()

    def test_за_реестр_не_готов(self, gen):
        _, нерешённые, data = self._подобрать(gen, final_rtk_inclusion_variant="registry")
        assert нерешённые == ["final_rtk_inclusion"]
        assert "За реестр" in data["_unresolvedReasons"]["final_rtk_inclusion"]


class TestФинальныеФНС:
    def _подобрать(self, gen, **поля):
        акты = ["final_rtk_inclusion"]
        data = данные(selectedActsIds=",".join(акты),
                      selectedActsData=json.dumps([{"id": a, "selected": True} for a in акты]),
                      creditorName="ФНС России",
                      selectedCollateralOption="no_collateral",
                      **поля)
        шаблоны, нерешённые = подобрать(gen, data)
        return шаблоны, нерешённые, data

    def test_включение_это_резолютивка_по_очереди(self, gen):
        шаблоны, нерешённые, _ = self._подобрать(gen)
        assert нерешённые == []
        путь = шаблоны["rtk_inclusion"]["path"]
        assert "ФНС" in путь.parts
        assert "резолютивка" in путь.name.lower()

    @pytest.mark.parametrize("поля,начало", [
        ({}, "3-я"),
        ({"fnsQ2Total": "1000"}, "2-я_"),
        ({"fnsQ2Total": "1000", "fnsQ3Total": "500"}, "2-я_3-я"),
        ({"fnsQ3Arrears": "700"}, "3-я"),
    ])
    def test_очередь_по_суммам(self, gen, поля, начало):
        шаблоны, _, _ = self._подобрать(gen, **поля)
        assert шаблоны["rtk_inclusion"]["path"].name.startswith(начало), (
            шаблоны["rtk_inclusion"]["path"].name)

    def test_короткий_текст_не_добавляется(self, gen):
        # Включение у ФНС само резолютивка — второй такой же акт не нужен.
        шаблоны, _, _ = self._подобрать(gen, selectedShortText="true")
        assert "short_text" not in шаблоны


class TestИнициированиеНеПопадаетВРТК:
    """Инициирование ФЛ ходит в свою ветку; подробности — test_initiation_acts_from_tree."""

    @pytest.mark.parametrize("вид", ["other", "self"])
    def test_ветка_своя(self, gen, вид):
        data = данные(selectedApplicationKind=вид)
        оси = gen._bankruptcy_tree_axes(data, "individual", "no_collateral", АКТЫ)
        assert оси["branch"] == bankruptcy_tree.BRANCH_INITIATION
        шаблоны, _ = подобрать(gen, data)
        assert шаблоны
        assert all("Включение в РТК" not in с["path"].parts for с in шаблоны.values())


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
