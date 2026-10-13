"""Регистр значений: подключение полей в генераторе и путь до текста акта."""
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
    "creditorAddress": "117312, г. Москва, ул. Вавилова, д. 19",
    "entityType": "individual",
    "date": "17.07.2026",
    "judge": "Ерёмин Ф.Ф.",
    "obligations": [],
    "selectedEntityType": "individual",
    "selectedCollateralOption": "collateral",
    "selectedApplicationKind": "rtk",
}

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


class TestДоАкта:
    """Сквозной путь: капсовое значение в данных — обычный регистр в документе."""

    def test_фио_должника_в_родительном(self, gen):
        текст = _текст(gen, applicantNameGenitive="ЛАВРУХИНА ДМИТРИЯ ЮРЬЕВИЧА")
        assert "Лаврухина Дмитрия Юрьевича" in текст
        assert "ЛАВРУХИНА" not in текст

    def test_юридический_адрес_кредитора(self, gen):
        текст = _текст(gen, creditorAddress="117312, Г. МОСКВА, УЛ. ВАВИЛОВА, Д. 19")
        assert "117312, г. Москва, ул. Вавилова, д. 19" in текст
        assert "УЛ. ВАВИЛОВА" not in текст

    def test_почтовый_адрес_кредитора(self, gen):
        текст = _текст(gen, creditorPostalAddress="109052, Г. МОСКВА, УЛ. СМИРНОВСКАЯ, Д. 10")
        assert "109052, г. Москва, ул. Смирновская, д. 10" in текст

    def test_смешанный_регистр_доезжает_без_правок(self, gen):
        # Ворота слоя: набранное человеком остаётся как есть.
        дано = "117312, г. Москва, ул. Вавилова-Южная, д. 19"
        assert дано in _текст(gen, creditorAddress=дано)


class TestПодключениеПолей:
    """Какие поля слой обходит: имена, организации, адреса и нумерованные слоты."""

    def _прогнать(self, gen, данные):
        gen._normalize_value_cases(данные)
        return данные

    def test_имена_сторон(self, gen):
        дано = {
            "debtorName": "ЛАВРУХИН ДМИТРИЙ ЮРЬЕВИЧ",
            "applicantName": "лаврухин дмитрий юрьевич",
            "managerName": "ПИСКОВА ТАТЬЯНА НИКОЛАЕВНА",
            "notaryName": "ЗУБКОВА КРИСТИНА СТАНИСЛАВОВНА",
        }
        стало = self._прогнать(gen, дано)
        assert стало["debtorName"] == "Лаврухин Дмитрий Юрьевич"
        assert стало["applicantName"] == "Лаврухин Дмитрий Юрьевич"
        assert стало["managerName"] == "Пискова Татьяна Николаевна"
        assert стало["notaryName"] == "Зубкова Кристина Станиславовна"

    def test_падежи_заявителя(self, gen):
        дано = {
            "applicantNameGenitive": "ЛАВРУХИНА ДМИТРИЯ",
            "applicantNameDative": "ЛАВРУХИНУ ДМИТРИЮ",
            "applicantNameInstrumental": "ЛАВРУХИНЫМ ДМИТРИЕМ",
            "applicantNameAccusative": "ЛАВРУХИНА ДМИТРИЯ",
        }
        стало = self._прогнать(gen, дано)
        assert стало["applicantNameGenitive"] == "Лаврухина Дмитрия"
        assert стало["applicantNameDative"] == "Лаврухину Дмитрию"
        assert стало["applicantNameInstrumental"] == "Лаврухиным Дмитрием"
        assert стало["applicantNameAccusative"] == "Лаврухина Дмитрия"

    def test_адресные_поля(self, gen):
        дано = {
            "applicantAddress": "344000, Г. РОСТОВ-НА-ДОНУ, УЛ. ЛЕНИНА, Д. 1",
            "creditorPostalAddress": "109052, Г. МОСКВА",
            "managerAddress": "386151, РЕСП ИНГУШЕТИЯ, СЕЛО ЭКАЖЕВО",
            "birthPlace": "С. ОКТЯБРЬСКОЕ ШАЛИНСКОГО РАЙОНА ЧИАССР",
        }
        стало = self._прогнать(gen, дано)
        assert стало["applicantAddress"] == "344000, г. Ростов-на-Дону, ул. Ленина, д. 1"
        assert стало["creditorPostalAddress"] == "109052, г. Москва"
        assert стало["managerAddress"] == "386151, Респ Ингушетия, село Экажево"
        assert стало["birthPlace"] == "с. Октябрьское Шалинского района ЧИАССР"

    def test_короткое_имя_юрлица_как_организация(self, gen):
        # legalShortName приходит без ОПФ и кавычек, человеком его считать нельзя:
        # аббревиатуру «ПКБ» путь для ФИО превратил бы в «Пкб».
        стало = self._прогнать(gen, {"legalShortName": "ПКБ", "sroName": "ГМБХ"})
        assert стало["legalShortName"] == "ПКБ"
        assert стало["sroName"] == "ГмбХ"

    def test_имя_юрлица_без_аббревиатур(self, gen):
        стало = self._прогнать(gen, {"legalShortName": "ФОРТЕ ПРОМ СТИЛ"})
        assert стало["legalShortName"] == "Форте Пром Стил"

    def test_нумерованные_слоты_заинтересованных(self, gen):
        дано = {
            "interestedName25_1": "ПЕТРОВА АННА СЕРГЕЕВНА",
            "interestedAddress54_1": "344000, Г. РОСТОВ-НА-ДОНУ",
            "interestedName25_5": "СИДОРОВ ПЁТР ПЕТРОВИЧ",
        }
        стало = self._прогнать(gen, дано)
        assert стало["interestedName25_1"] == "Петрова Анна Сергеевна"
        assert стало["interestedAddress54_1"] == "344000, г. Ростов-на-Дону"
        assert стало["interestedName25_5"] == "Сидоров Пётр Петрович"

    def test_слоты_ответчиков_по_ипотеке(self, gen):
        дано = {
            "mortgageRespNom1400_1": "ПЕТРОВА АННА",
            "mortgageRespGen1401_1": "ПЕТРОВОЙ АННЫ",
            "mortgageRespDat1402_1": "ПЕТРОВОЙ АННЕ",
            "mortgageRespAddr1403_1": "Г. МАГАС, УЛ. МАЛЬСАГОВА, Д. 32",
        }
        стало = self._прогнать(gen, дано)
        assert стало["mortgageRespNom1400_1"] == "Петрова Анна"
        assert стало["mortgageRespGen1401_1"] == "Петровой Анны"
        assert стало["mortgageRespDat1402_1"] == "Петровой Анне"
        assert стало["mortgageRespAddr1403_1"] == "г. Магас, ул. Мальсагова, д. 32"

    def test_судья_и_ведущий_протокол(self, gen):
        # Секретарь вводится вручную — приходит как набрали, часто капсом.
        дано = {
            "judge": "ЕРЁМИН Ф.Ф.",
            "judgeFullName": "ЕРЁМИН ФИЛИПП ФЁДОРОВИЧ",
            "authorName": "ИВАНОВ ИВАН ИВАНОВИЧ",
        }
        стало = self._прогнать(gen, дано)
        assert стало["judge"] == "Ерёмин Ф.Ф."
        assert стало["judgeFullName"] == "Ерёмин Филипп Фёдорович"
        assert стало["authorName"] == "Иванов Иван Иванович"

    def test_проза_не_трогается(self, gen):
        # Соседние поля — описания и номера, регистр в них осмысленный.
        дано = {
            "objectName": "ЖИЛОЙ ДОМ ПЛОЩАДЬЮ 120 КВ. М",
            "contractNumber": "1/25/016-40-ПЮЛ/1",
            "procedureTypeRaw": "реализации имущества гражданина",
            "obligationType": "кредитный договор",
        }
        стало = self._прогнать(gen, dict(дано))
        assert стало == дано

    def test_опф_без_имени_не_меняется(self, gen):
        стало = self._прогнать(gen, {"debtorName": "ИП"})
        assert стало["debtorName"] == "ИП"

    def test_фнс_кредитор_пропускается(self, gen):
        дано = {"creditorName": "МЕЖРАЙОННАЯ ИФНС РОССИИ № 12", "_fnsCreditor": True}
        стало = self._прогнать(gen, дано)
        assert стало["creditorName"] == "МЕЖРАЙОННАЯ ИФНС РОССИИ № 12"
