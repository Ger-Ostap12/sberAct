# -*- coding: utf-8 -*-
"""Ложная пометка «адреса кредитора в документе нет».

Пометка опиралась на то, собрал ли адрес разбор, а у заявлений ФНС шапка
свёрстана метками стопкой и построчно не собирается. Проверяем не структуру,
а назван ли адрес: индекс и улица по отдельности.
"""
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from address_match import address_named_in_text  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402

КОРПУС = os.path.abspath(os.path.join(_THIS, "..", "..", "Заявления"))
СИРИУС = os.path.join(КОРПУС, "НОвая конвертация",
                      "Заявление о включении в РТК  ООО СИРИУС.docx")

АДРЕС = "344002, Ростов-на-Дону г, Социалистическая ул, 96-98"
# Шапка СИРИУСа как её отдаёт конвертер: значения перемешаны с пометами «На №».
ШАПКА_СТОПКОЙ = (
    "УПРАВЛЕНИЕ ФЕДЕРАЛЬНОЙ НАЛОГОВОЙ СЛУЖБЫ ПО РОСТОВСКОЙ ОБЛАСТИ\n"
    " Заявитель: Управление ФНС России № по Ростовской области \n"
    " ул. Социалистическая, 96-98 На № г. Ростов-на-Дону, 344002\n"
)


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


# --- чистая функция ----------------------------------------------------------------


def test_адрес_назван_несмотря_на_вёрстку():
    assert address_named_in_text(АДРЕС, ШАПКА_СТОПКОЙ) is True


def test_адреса_нет_в_тексте():
    текст = "Арбитражный суд Ростовской области, ул. Станиславского, 8А, 344002"
    assert address_named_in_text(АДРЕС, текст) is False


def test_одного_индекса_недостаточно():
    """Суд и инспекция сидят в одном индексе 344002 — по индексу подтвердился бы
    чужой адрес."""
    текст = "344002, г. Ростов-на-Дону, ул. Станиславского, 8А"
    assert address_named_in_text(АДРЕС, текст) is False


def test_одной_улицы_недостаточно():
    текст = "ул. Социалистическая, 96-98, г. Ростов-на-Дону, 111111"
    assert address_named_in_text(АДРЕС, текст) is False


@pytest.mark.parametrize("адрес,текст", [
    # Разные написания одного адреса: индекс и улица важнее формы записи.
    ("115432, г. Москва, проспект Андропова, д. 18, корп. 1",
     'ПАО "МТС-Банк" проспект Андропова, д. 18, корп. 1, Москва, 115432'),
    ("346407, Ростовская обл, Новочеркасск г, Ермака пр-кт, 104",
     "пр. Ермака, 104, г. Новочеркасск, Ростовская область, 346407"),
    ("450075, Башкортостан Респ, Уфа г, Октября проспект, 95, 2",
     "пр. Октября, 95/2, г.Уфа, 450075"),
])
def test_разные_написания_одного_адреса(адрес, текст):
    assert address_named_in_text(адрес, текст) is True


def test_неполный_ключ_не_подтверждает():
    """Нечем подтверждать — не подтверждаем: без индекса или улицы ответ «нет»."""
    assert address_named_in_text("г. Москва", "г. Москва, 115432") is False
    assert address_named_in_text("115432", "115432") is False


# --- пометка на поле ---------------------------------------------------------------


def test_пометка_не_ставится_когда_адрес_назван(analyzer):
    fields = {}
    analyzer._advise_registry_address(fields, АДРЕС, ШАПКА_СТОПКОЙ)
    assert not (fields.get(analyzer._ADVISORY_KEY) or {}).get("creditorAddress")


def test_пометка_ставится_когда_адреса_нет(analyzer):
    fields = {}
    analyzer._advise_registry_address(fields, АДРЕС, "Текст без адреса кредитора")
    assert (fields.get(analyzer._ADVISORY_KEY) or {}).get("creditorAddress")


def test_без_текста_поведение_прежнее(analyzer):
    """Текст не передали — пометка ставится, как до правки."""
    fields = {}
    analyzer._advise_registry_address(fields, АДРЕС)
    assert (fields.get(analyzer._ADVISORY_KEY) or {}).get("creditorAddress")


# --- документ целиком --------------------------------------------------------------


@pytest.mark.skipif(not os.path.exists(СИРИУС), reason="документ вне корпуса недоступен")
def test_сириус_без_ложной_пометки(analyzer):
    r = analyzer.analyze(СИРИУС)
    пометки = [i.get("field") for i in (r.get("fieldIssues") or [])]
    assert "creditorAddress" not in пометки
    # Значение при этом на месте — пометку сняли, адрес не тронули.
    assert (r.get("fields") or {}).get("creditorAddress")


@pytest.mark.skipif(not os.path.exists(СИРИУС), reason="документ вне корпуса недоступен")
def test_сириус_родительный_падеж(analyzer):
    """Второй дефект СИРИУСа: в поле падежа стояла проза о процедуре."""
    f = (analyzer.analyze(СИРИУС).get("fields") or {})
    assert f.get("applicantNameGenitive") == "ООО «СИРИУС»"
