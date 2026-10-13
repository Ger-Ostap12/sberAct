"""Нормализация регистра значений перед подстановкой в акт."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from text_case import (  # noqa: E402
    normalize_address_case,
    normalize_name_case,
    normalize_org_case,
    normalize_person_case,
)


class TestВорота:
    """Правим только однородный регистр — смешанный набран человеком."""

    @pytest.mark.parametrize("значение", [
        "Иванов Иван Иванович",
        "Ерёмин Ф.Ф.",
        "ООО «Форте Пром Стил ГмбХ»",
        "344000, г. Ростов-на-Дону, ул. Пушкинская, д. 10",
        "ООО МКК «УФ» (One Click Money)",
    ])
    def test_смешанный_регистр_не_трогаем(self, значение):
        assert normalize_name_case(значение) == значение
        assert normalize_address_case(значение) == значение

    @pytest.mark.parametrize("значение", ["", None, "   ", "12345", "№ 12/25"])
    def test_пустое_и_без_букв(self, значение):
        assert normalize_name_case(значение) == значение
        assert normalize_address_case(значение) == значение


class TestФИО:
    def test_капс_приводится(self):
        assert normalize_person_case("ЛАВРУХИН ДМИТРИЙ ЮРЬЕВИЧ") == "Лаврухин Дмитрий Юрьевич"

    def test_строчное_поднимается(self):
        assert normalize_person_case("иванов иван иванович") == "Иванов Иван Иванович"

    def test_падежная_форма(self):
        assert normalize_person_case("НУРИЕВОЙ ЕЛЕНЫ ВАЛИДИНОВНЫ") == "Нуриевой Елены Валидиновны"

    def test_инициалы_остаются_заглавными(self):
        assert normalize_person_case("ЖИГАЛО А.") == "Жигало А."
        assert normalize_person_case("ПЕСНЯ С.Н.") == "Песня С.Н."

    def test_двойная_фамилия_через_дефис(self):
        assert normalize_person_case("ИВАНОВ-ПЕТРОВ СЕРГЕЙ") == "Иванов-Петров Сергей"

    def test_частица_отчества_со_строчной(self):
        assert normalize_person_case("МАМЕДОВ АРИФ АГА ОГЛЫ") == "Мамедов Ариф Ага оглы"

    def test_опф_в_имени_остаётся_капсом(self):
        assert normalize_person_case("ИП РОМАНОВ ВАСИЛИЙ") == "ИП Романов Василий"
        assert normalize_person_case("ГЛАВА КФХ ПЕТРОВ ПЁТР") == "Глава КФХ Петров Пётр"

    def test_ё_не_теряется(self):
        assert normalize_person_case("ЕРЁМИН ФИЛИПП ФЁДОРОВИЧ") == "Ерёмин Филипп Фёдорович"


class TestОрганизации:
    def test_название_в_кавычках(self):
        assert normalize_org_case("ООО «СИРИУС»") == "ООО «Сириус»"

    def test_дефис_в_названии(self):
        assert normalize_org_case("АО «АЛЬФА-БАНК»") == "АО «Альфа-Банк»"

    def test_несколько_опф_подряд(self):
        assert normalize_org_case("ООО МКК «РУСИНТЕРФИНАНС»") == "ООО МКК «Русинтерфинанс»"

    def test_аббревиатура_названия_из_реестра(self):
        assert normalize_org_case("НАО ПКО «ПКБ»") == "НАО ПКО «ПКБ»"
        assert normalize_org_case("ПАО «БАНК ПСБ»") == "ПАО «Банк ПСБ»"

    def test_короткое_слово_не_считается_аббревиатурой(self):
        # «ПРОМ» и «СТИЛ» — слова, а не аббревиатуры: реестр, а не длина.
        assert normalize_org_case("ФОРТЕ ПРОМ СТИЛ") == "Форте Пром Стил"

    def test_гмбх_каноническая_форма(self):
        assert normalize_org_case("ООО «ФОРТЕ ГМБХ»") == "ООО «Форте ГмбХ»"

    def test_предлог_в_середине_со_строчной(self):
        assert normalize_org_case("ООО «ЗАВОД ПО ПЕРЕРАБОТКЕ»") == "ООО «Завод по Переработке»"

    def test_служебное_слово_первым_остаётся_с_заглавной(self):
        assert normalize_org_case("ПО ПЕРЕРАБОТКЕ СЫРЬЯ") == "По Переработке Сырья"

    def test_каждое_слово_названия_с_заглавной(self):
        # Граница слоя: для бренда «Совком Экспресс» это верно, для описательного
        # «завод по переработке отходов» — нет. Без словаря их не различить.
        assert normalize_org_case("ООО МФК «СОВКОМ ЭКСПРЕСС»") == "ООО МФК «Совком Экспресс»"

    def test_двойные_кавычки(self):
        assert normalize_org_case('АО "КОНЦЕРН "САРМАТ"') == 'АО "Концерн "Сармат"'


class TestАдреса:
    def test_сокращения_со_строчной(self):
        дано = "366666, ЧЕЧЕНСКАЯ РЕСПУБЛИКА, ШАЛИНСКИЙ Р-Н, С. ГЕРМЕНЧУК, УЛ. СТРОИТЕЛЬНАЯ, Д. 5"
        ждём = "366666, Чеченская Республика, Шалинский р-н, с. Герменчук, ул. Строительная, д. 5"
        assert normalize_address_case(дано) == ждём

    def test_составной_топоним(self):
        дано = "ОБЛ. РОСТОВСКАЯ, Г. РОСТОВ-НА-ДОНУ, УЛ. НОВАТОРОВ, Д. 6, КВ. 16"
        ждём = "обл. Ростовская, г. Ростов-на-Дону, ул. Новаторов, д. 6, кв. 16"
        assert normalize_address_case(дано) == ждём

    def test_падежная_форма_сокращения(self):
        assert normalize_address_case("С. ОКТЯБРЬСКОЕ ШАЛИНСКОГО РАЙОНА ЧИАССР") == (
            "с. Октябрьское Шалинского района ЧИАССР")

    def test_аббревиатура_республики_сохраняется(self):
        assert normalize_address_case("ПОС. ДУБКИ ГОР. КИЗИЛЮРТА ДАГЕСТАНСКОЙ АССР") == (
            "пос. Дубки гор. Кизилюрта Дагестанской АССР")

    def test_республика_с_заглавной(self):
        assert normalize_address_case("РЕСПУБЛИКА ИНГУШЕТИЯ, Г. МАГАС") == (
            "Республика Ингушетия, г. Магас")

    def test_строчный_адрес_поднимается(self):
        assert normalize_address_case("г. ростов-на-дону, ул. ленина, д. 1, кв. 2") == (
            "г. Ростов-на-Дону, ул. Ленина, д. 1, кв. 2")

    def test_место_рождения_через_слэш(self):
        assert normalize_address_case("РОССИЯ /АЗЕРБАЙДЖАН") == "Россия /Азербайджан"


class TestДиспетчер:
    def test_кавычки_признак_организации(self):
        assert normalize_name_case("ООО «СПОРТ»") == "ООО «Спорт»"

    def test_без_опф_это_человек(self):
        assert normalize_name_case("ПЕТРОВА АННА СЕРГЕЕВНА") == "Петрова Анна Сергеевна"

    def test_ип_не_делает_строку_организацией(self):
        # ИП и КФХ исключены из признака: за ними идёт ФИО человека.
        assert normalize_name_case("ИП СИДОРОВ ИВАН") == "ИП Сидоров Иван"

    def test_флаг_как_организацию(self):
        # legalShortName приходит без ОПФ и кавычек: «СИРИУС».
        assert normalize_name_case("СИРИУС", как_организацию=True) == "Сириус"
        assert normalize_name_case("ПКБ", как_организацию=True) == "ПКБ"
