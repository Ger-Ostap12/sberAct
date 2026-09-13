# -*- coding: utf-8 -*-
"""Выбор резолютивки ипотеки по представителям (13.09.2026).

ЧТО ЗАПИРАЕМ. Резолвер шаблонов читает ТОЛЬКО `representativeName`, а ипотечная
ветка анализа кладёт имя в номерное `mortgageRepresentative22`. Пока зеркала не
было, резолвер видел пустоту и выбирал «должник» на КАЖДОМ ипотечном заявлении
корпуса — восемь из восьми, хотя представитель в документе назван. Ошибка не
ловилась ни golden (поля в снимке не было), ни эталоном (класса под выбор акта
нет): она видна только в готовом документе.

Связка «зеркало -> резолвер» держится на одном присваивании в двух разных
файлах. Эти тесты — единственное, что не даёт ей молча развалиться снова.
"""
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from document_analyzer import DocumentAnalyzer  # noqa: E402
from document_generator import DocumentGenerator  # noqa: E402


@pytest.fixture(scope="module")
def генератор():
    return DocumentGenerator()


@pytest.fixture(scope="module")
def анализатор():
    return DocumentAnalyzer()


# --- зеркало на стороне анализа ----------------------------------------------

def test_ипотечное_имя_зеркалится_в_каноническое_поле(анализатор):
    """Без этой строки резолвер не увидит представителя вовсе."""
    поля = {"mortgageRepresentative22": "Чепелов Иван Александрович"}
    анализатор._fill_representative_name(поля, "", "mortgage_claim")
    assert поля["representativeName"] == "Чепелов Иван Александрович"


def test_общий_разбор_к_ипотеке_не_подпускается(анализатор):
    """ГЛАВНАЯ ЗАЩИТА.

    В конце ипотечных заявлений подшито письмо банка должнику со своей подписью.
    Если метки «Представитель истца:» в шапке не оказалось, общий разбор взял бы
    подпись из этого письма — и резолвер ушёл бы на вариант «представители» по
    чужому имени. Пусто лучше правдоподобного чужого.
    """
    письмо = ("заёмщик ЁЛКИН ДЕНИС АЛЕКСАНДРОВИЧ\n"
              "Представитель ПАО Сбербанк\nпо доверенности\nРезулов И.А.\n"
              "Уважаемый клиент! ")
    поля = {}
    анализатор._fill_representative_name(поля, письмо, "mortgage_claim")
    assert "representativeName" not in поля


def test_в_банкротстве_общий_разбор_работает(анализатор):
    """Та же подпись в банкротном заявлении — законный источник."""
    поля = {}
    анализатор._fill_representative_name(
        поля, "Представитель ПАО Сбербанк\nпо доверенности\tЮсупова Е.О.\n9",
        "rtk_application")
    assert поля["representativeName"] == "Юсупова Е.О."


# --- выбор акта на стороне резолвера -----------------------------------------

ИПОТЕКА = {"mortgageKind": "civil", "fields": {"solidaryLiability": ""}}


def _выбор(генератор, **поля):
    данные = {"mortgageKind": "civil", "fields": dict(поля)}
    return генератор._mortgage_selection(данные)


def test_представитель_истца_переключает_акт(генератор):
    выбор = _выбор(генератор, representativeName="Чепелов Иван Александрович")
    assert выбор["representatives"] is True
    assert "представители" in генератор._mortgage_decision_file(выбор)


def test_без_представителя_акт_по_должнику(генератор):
    выбор = _выбор(генератор)
    assert выбор["representatives"] is False
    assert "должник" in генератор._mortgage_decision_file(выбор)


def test_хватает_представителя_одной_стороны(генератор):
    """Решение Андрея 30.07.2026: достаточно представителя ЛЮБОЙ стороны."""
    выбор = _выбор(генератор, respondentRepresentativeName="Сидоров П.П.")
    assert выбор["representatives"] is True


def test_номерное_поле_резолвер_не_читает(генератор):
    """Ровно та дыра, из-за которой акт выбирался неверно.

    Если кто-то решит, что зеркало в анализе лишнее, — этот тест объяснит, чем
    оно было: одного mortgageRepresentative22 резолверу НЕ достаточно.
    """
    выбор = _выбор(генератор, mortgageRepresentative22="Чепелов Иван Александрович")
    assert выбор["representatives"] is False


def test_военная_ипотека_ветвлений_не_имеет(генератор):
    """У военки один акт на все сочетания — представители его не меняют."""
    с_пред = генератор._mortgage_selection(
        {"mortgageKind": "military", "fields": {"representativeName": "Иванов И.И."}})
    без = генератор._mortgage_selection({"mortgageKind": "military", "fields": {}})
    assert (генератор._mortgage_decision_file(с_пред)
            == генератор._mortgage_decision_file(без)
            == "Решение резолютивка военка.docx")


# --- сквозной прогон на настоящем документе ----------------------------------

def test_сквозь_анализ_ипотечный_акт_идёт_с_представителями(анализатор, генератор):
    """Восемь ипотечных документов корпуса уходили в акт «должник». Проверяем
    связку целиком: файл -> анализ -> резолвер."""
    sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "golden")))
    import _snapshot as s

    путь = next((os.path.join(s.CORPUS_DIR, rel.replace("/", os.sep))
                 for rel in s.corpus_files() if "ДДУ.docx" in rel), None)
    if not путь or not os.path.exists(путь):
        pytest.skip("корпус недоступен")

    r = анализатор.analyze(путь)
    assert r.get("documentType") == "mortgage_claim", "предпосылка теста"
    assert (r.get("fields") or {}).get("representativeName"), "зеркало не сработало"

    выбор = генератор._mortgage_selection(r)
    assert выбор["representatives"] is True
    assert выбор["kind"] == "ddu"
    assert "представители" in генератор._mortgage_decision_file(выбор)
