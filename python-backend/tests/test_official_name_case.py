# -*- coding: utf-8 -*-
"""Падежи ФИО судьи и ведущего протокол.

Контексты взяты из шаблонов: «в составе судьи [415]», «Судья [415]» в подписи,
«секретарем судебного заседания [29]», «при секретаре судебного заседания [29]».
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from official_name_case import (  # noqa: E402
    clerk_case,
    gender_of_person,
    gender_from_full_name,
    gender_from_surname,
    inflect_short_fio,
    judge_case,
)


class TestПадежСудьи:
    def test_в_составе_судьи_родительный(self):
        assert judge_case("Арбитражный суд Ростовской области в составе судьи ") == "gent"

    def test_председательствующего_судьи_родительный(self):
        assert judge_case("в составе: председательствующего судьи ") == "gent"

    def test_на_имя_судьи_родительный(self):
        assert judge_case("должны быть поданы на имя судьи ") == "gent"

    def test_подпись_именительный(self):
        assert judge_case("г. Ростов-на-Дону Дело № А53-1 Судья ") == "nomn"

    def test_судьёй_творительный(self):
        assert judge_case("дело рассмотрено судьёй ") == "ablt"

    def test_пустой_контекст_именительный(self):
        assert judge_case("") == "nomn"

    def test_берётся_ближайшее_слово(self):
        # «Судья» в шапке выше, «судьи» ближе к маркеру — падеж по ближнему.
        assert judge_case("Судья Арбитражного суда в составе судьи ") == "gent"


class TestПадежВедущегоПротокол:
    def test_секретарем_творительный(self):
        assert clerk_case("при ведении протокола судебного заседания секретарем судебного заседания ") == "ablt"

    def test_секретарём_через_ё(self):
        assert clerk_case("протокол вела секретарём судьи ") == "ablt"

    def test_помощником_творительный(self):
        assert clerk_case("при ведении протокола помощником судьи ") == "ablt"

    def test_при_секретаре_предложный(self):
        assert clerk_case("в составе: председательствующего судьи Иванова И.И., при секретаре судебного заседания ") == "loct"

    def test_при_помощнике_предложный(self):
        assert clerk_case("в составе: судьи Иванова И.И., при помощнике судьи ") == "loct"

    def test_по_умолчанию_творительный(self):
        assert clerk_case("") == "ablt"


class TestРод:
    def test_по_отчеству_мужскому(self):
        assert gender_from_full_name("Ерёмин Филипп Фёдорович") == "masc"

    def test_по_отчеству_женскому(self):
        assert gender_from_full_name("Власова Наталья Юрьевна") == "femn"

    def test_без_полного_фио(self):
        assert gender_from_full_name("") is None
        assert gender_from_full_name(None) is None

    def test_инициал_не_считается_женским_именем(self):
        # «Жигало А.»: разбор по инициалу давал femn — мужчина становился женщиной.
        assert gender_from_full_name("Жигало А.") is None
        assert gender_from_full_name("Жигало А.В.") is None
        assert gender_of_person("Жигало А.") is None

    def test_полное_фио_с_инициалами_тоже_не_разбирается(self):
        assert gender_from_full_name("Иванов И. Иванович") is None

    def test_по_окончанию_фамилии(self):
        assert gender_from_surname("Секретарева") == "femn"
        assert gender_from_surname("Иванов") == "masc"
        assert gender_from_surname("Жигало") is None
        assert gender_from_surname("Обама") is None


class TestСклонениеКороткогоФИО:
    def test_мужская_фамилия_родительный(self):
        assert inflect_short_fio("Ерёмин Ф.Ф.", "gent", "masc") == "Ерёмина Ф.Ф."

    def test_женская_фамилия_родительный(self):
        assert inflect_short_fio("Власова Н.Ю.", "gent", "femn") == "Власовой Н.Ю."

    def test_творительный_женский(self):
        assert inflect_short_fio("Помощникова Ф.А.", "ablt") == "Помощниковой Ф.А."

    def test_творительный_мужской(self):
        assert inflect_short_fio("Иванов И.И.", "ablt") == "Ивановым И.И."

    def test_предложный(self):
        assert inflect_short_fio("Секретарева С.В.", "loct") == "Секретаревой С.В."

    def test_именительный_не_трогаем(self):
        assert inflect_short_fio("Ерёмин Ф.Ф.", "nomn", "masc") == "Ерёмин Ф.Ф."

    def test_инициалы_остаются_как_есть(self):
        assert inflect_short_fio("Ерёмин Ф.Ф.", "gent", "masc").endswith("Ф.Ф.")

    def test_несклоняемая_фамилия_без_рода_не_меняется(self):
        # Род неизвестен — не гадаем: для женщины склонение было бы ошибкой.
        assert inflect_short_fio("Тарасенко О.А.", "gent") == "Тарасенко О.А."
        assert inflect_short_fio("Обама Ф.В.", "ablt") == "Обама Ф.В."

    def test_род_из_справочника_перебивает_окончание(self):
        # «Жигало» по окончанию не опознаётся, но отчество даёт род.
        род = gender_from_full_name("Жигало Наталья Александровна")
        assert inflect_short_fio("Жигало Н.А.", "gent", род) == "Жигало Н.А."

    def test_двойная_фамилия_склоняется_целиком(self):
        assert inflect_short_fio("Пупкина-Залупкина А.В.", "ablt") == "Пупкиной-Залупкиной А.В."

    def test_пустое_значение(self):
        assert inflect_short_fio("", "gent") == ""

    def test_значение_из_одних_инициалов_не_ломается(self):
        assert inflect_short_fio("Ф.Ф.", "gent") == "Ф.Ф."
