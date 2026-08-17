# -*- coding: utf-8 -*-
"""Адрес управляющего без индекса и обязательства из перечня долгов самобанкрота.

1. **Адрес арбитражного управляющего.** Все паттерны `managerAddress` требовали
   шести цифр почтового индекса, а в заявлении он есть далеко не всегда:

       Финансовый управляющий: Сайгушев Денис Сергеевич
       Адрес: Ростовская область, г. Ростов-на-Дону, а/я 22 ИНН: 143101552700

   поле оставалось пустым. Метка «Адрес» обязана начинать строку: иначе сюда
   попадал адрес СРО из просительной («утвердить управляющего из числа
   Ассоциации …, ИНН …, адрес: 454100, г.Челябинск…»), а это не адрес
   управляющего.

2. **Обязательства самобанкрота.** Перечень долгов гражданина выглядит так:

       1. АО «АЛЬФА-БАНК». Задолженность по кредитному договору от 01.04.2025г.
          на сумму 72 353.70 рублей.

   номера договора в нём нет вовсе. Канонический экстрактор («<тип> №NUM от
   DATE») молчал, а финальный дедуп выбрасывал всё, у чего номер не проходит
   `_is_valid_contract_number` — блок «Обязательства» оставался пустым.
"""
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from document_analyzer import DocumentAnalyzer  # noqa: E402


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


# --- 1. Адрес управляющего --------------------------------------------------

CREDITOR_APP = """В Арбитражный суд Ростовской области
Кредитор: ПАО Сбербанк
Должник: БОЯЧУК ЕВГЕНИЙ СЕРГЕЕВИЧ
ИНН: 610602300237
Финансовый управляющий:
Сайгушев Денис Сергеевич
Адрес: {address} ИНН: 143101552700
СНИЛС:07790170790
Дело № А53-21258/2026
"""


@pytest.mark.parametrize(
    "address",
    [
        "Ростовская область, г. Ростов-на-Дону, а/я 22",       # без индекса
        "344000, г. Ростов-на-Дону, ул. Большая Садовая, 1",   # с индексом
    ],
)
def test_manager_address_with_and_without_index(analyzer, address):
    fields = analyzer.analyze_from_text(CREDITOR_APP.format(address=address))["fields"]
    assert fields.get("managerAddress") == address


def test_manager_address_ignores_sro_address(analyzer):
    """Адрес СРО из просительной — не адрес управляющего."""
    text = (
        "В Арбитражный суд Ростовской области\n"
        "Должник: Толпыгин Владимир Алексеевич\n"
        "ЗАЯВЛЕНИЕ о признании гражданина несостоятельным (банкротом)\n"
        "ПРОШУ:\n"
        "2. Утвердить финансового управляющего из числа Ассоциации арбитражных "
        "управляющих «Эверест», ОГРН 1247400013057, ИНН 7448257298, адрес: "
        "454100, г.Челябинск, ул.Шершневская,д.66, оф.21, тел.+7 919 300 08 52.\n"
    )
    assert not analyzer.analyze_from_text(text)["fields"].get("managerAddress")


def test_manager_address_stops_before_inn(analyzer):
    """ИНН/СНИЛС не утекают в адрес."""
    fields = analyzer.analyze_from_text(
        CREDITOR_APP.format(address="Ростовская область, г. Ростов-на-Дону, а/я 22"))["fields"]
    address = fields.get("managerAddress") or ""
    assert "ИНН" not in address and "143101552700" not in address


# --- 2. Обязательства самобанкрота ------------------------------------------

SELF_APP = """В Арбитражный суд Ростовской области
Заявитель: Проскурин Ярослав Андреевич
дата рождения: 03.09.1996 г.р.
ИНН: 616210637657, СНИЛС: 201-394-086 25
ЗАЯВЛЕНИЕ о признании гражданина несостоятельным (банкротом)
Я, Проскурин Ярослав Андреевич, являюсь должником перед кредитными
организациями, сумма требований по моим денежным обязательствам составляет
1 703 617,13 руб. на основании следующих документов:
1. АКЦИОНЕРНОЕ ОБЩЕСТВО «АЛЬФА-БАНК». Задолженность по кредитному договору от
01.04.2025г. на сумму 72 353.70 рублей.
2. ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО «МТС-БАНК». Задолженность по кредитному
договору от 30.01.2025г. на сумму 9 997.10 рублей.
3. ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО «СБЕРБАНК РОССИИ». Задолженность по кредитному
договору от 09.09.2024г. на сумму 1 369 946,47 рублей., по кредитному договору
от 09.10.2023г. на сумму 28 567,18 рублей.
Таким образом, общая сумма задолженности перед кредиторами составляет
1 703 617,13 руб.
"""


def test_self_bankruptcy_obligations_extracted(analyzer):
    obligations = analyzer.analyze_from_text(SELF_APP)["obligations"]
    assert len(obligations) == 4, obligations
    dates = [o["contractDate"] for o in obligations]
    assert dates == ["01.04.2025", "30.01.2025", "09.09.2024", "09.10.2023"]
    assert all(o["obligationType"] == "Кредитный договор" for o in obligations)
    # Номера в таком перечне не называют — поле пустое, и это норма.
    assert all(not o["contractNumber"] for o in obligations)


def test_self_bankruptcy_obligations_keep_amounts(analyzer):
    obligations = analyzer.analyze_from_text(SELF_APP)["obligations"]
    assert [o.get("amount") for o in obligations] == [
        "72 353,70", "9 997,10", "1 369 946,47", "28 567,18"]


def test_numberless_obligations_not_collapsed(analyzer):
    """Договоры без номера не должны схлопнуться в один по пустому ключу."""
    obligations = analyzer.analyze_from_text(SELF_APP)["obligations"]
    assert len({o["contractDate"] for o in obligations}) == len(obligations)


def test_creditor_application_obligations_untouched(analyzer):
    """Кредиторское заявление разбирается прежним каноном (номер + дата)."""
    text = (
        "В Арбитражный суд Ростовской области\n"
        "Кредитор: ПАО Сбербанк\n"
        "Должник: БОЯЧУК ЕВГЕНИЙ СЕРГЕЕВИЧ\n"
        "ЗАЯВЛЕНИЕ\n"
        "ПАО Сбербанк и БОЯЧУК ЕВГЕНИЙ СЕРГЕЕВИЧ заключили эмиссионный контракт "
        "№99ТКПР24022800788001 от 28.02.2024.\n"
    )
    obligations = analyzer.analyze_from_text(text)["obligations"]
    assert len(obligations) == 1
    assert obligations[0]["contractNumber"] == "99ТКПР24022800788001"
    assert obligations[0]["contractDate"] == "28.02.2024"


def test_self_obligations_not_taken_from_creditor_application(analyzer):
    """Гейт самобанкротства: в кредиторском заявлении перечень не ищется."""
    text = (
        "В Арбитражный суд Ростовской области\n"
        "Кредитор: ПАО Сбербанк\n"
        "Должник: Иванов Иван Иванович\n"
        "ЗАЯВЛЕНИЕ кредитора о включении в реестр требований кредиторов\n"
        "Задолженность по кредитному договору от 01.04.2025 на сумму 72 353,70 рублей.\n"
    )
    obligations = analyzer.analyze_from_text(text)["obligations"]
    assert all(o.get("id", "").startswith("obligation_sb_") is False for o in obligations)
