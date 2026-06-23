# -*- coding: utf-8 -*-
"""Фича E: склонение ФИО по падежам (учёт рода, Surn-разбор, fallback)."""
import pytest


@pytest.fixture(scope="module")
def analyzer():
    from document_analyzer import DocumentAnalyzer
    return DocumentAnalyzer()


# (ФИО им.п., род.п., дат.п., твор.п., вин.п.) — эталонные формы.
CASES = [
    ("Иванов Иван Иванович",
     "Иванова Ивана Ивановича", "Иванову Ивану Ивановичу",
     "Ивановым Иваном Ивановичем", "Иванова Ивана Ивановича"),
    # Женская фамилия — главный фикс: во всех падежах фамилия в женском роде.
    ("Кузнецова Мария Сергеевна",
     "Кузнецовой Марии Сергеевны", "Кузнецовой Марии Сергеевне",
     "Кузнецовой Марией Сергеевной", "Кузнецову Марию Сергеевну"),
    ("Мартынова Ольга Павловна",
     "Мартыновой Ольги Павловны", "Мартыновой Ольге Павловне",
     "Мартыновой Ольгой Павловной", "Мартынову Ольгу Павловну"),
    # Фамилия-омоним (Surn-разбор) — не должна давать мн.ч.
    ("Тарасин Олег Петрович",
     "Тарасина Олега Петровича", "Тарасину Олегу Петровичу",
     "Тарасиным Олегом Петровичем", "Тарасина Олега Петровича"),
    # Несклоняемые фамилии — остаются неизменными.
    ("Шевченко Тарас Григорьевич",
     "Шевченко Тараса Григорьевича", "Шевченко Тарасу Григорьевичу",
     "Шевченко Тарасом Григорьевичем", "Шевченко Тараса Григорьевича"),
    ("Белых Иван Сергеевич",
     "Белых Ивана Сергеевича", "Белых Ивану Сергеевичу",
     "Белых Иваном Сергеевичем", "Белых Ивана Сергеевича"),
    # Прилагательная фамилия.
    ("Петровский Иван Ильич",
     "Петровского Ивана Ильича", "Петровскому Ивану Ильичу",
     "Петровским Иваном Ильичом", "Петровского Ивана Ильича"),
]


@pytest.mark.parametrize("nom,gent,datv,ablt,accs", CASES)
def test_full_name_inflection(analyzer, nom, gent, datv, ablt, accs):
    assert analyzer._convert_name_to_genitive(nom) == gent
    assert analyzer._convert_name_to_dative(nom) == datv
    assert analyzer._convert_name_to_instrumental(nom) == ablt
    assert analyzer._convert_name_to_accusative(nom) == accs


def test_caps_case_preserved(analyzer):
    """КАПС-написание сохраняется при склонении."""
    assert analyzer._convert_name_to_genitive("ИВАНОВ ИВАН ИВАНОВИЧ") == "ИВАНОВА ИВАНА ИВАНОВИЧА"


def test_double_surname(analyzer):
    """Двойная фамилия через дефис склоняется по обеим частям с сохранением регистра."""
    assert analyzer._convert_name_to_genitive("Петрова-Водкина Анна Сергеевна") == \
        "Петровой-Водкиной Анны Сергеевны"


def test_empty_and_none(analyzer):
    assert analyzer._convert_name_to_genitive("") is None
    assert analyzer._convert_name_to_genitive(None) is None


def test_inflect_surname_helper_direct():
    """Юнит хелпера без зависимости от pymorphy для несклоняемых форм."""
    from morph_utils import inflect_surname, detect_gender
    # Без morph: ручные правила всё равно работают для типовых суффиксов.
    assert inflect_surname(None, "Иванов", "gent", "masc") == "Иванова"
    assert inflect_surname(None, "Иванов", "datv", "femn") == "Ивановой"
    assert detect_gender(["Кузнецова", "Мария", "Сергеевна"]) == "femn"
    assert detect_gender(["Иванов", "Иван", "Иванович"]) == "masc"
