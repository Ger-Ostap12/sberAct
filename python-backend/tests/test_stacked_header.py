# -*- coding: utf-8 -*-
"""Шапка «метки стопкой» (01.09.2026).

Двухколоночная шапка при конвертации разъезжается: сначала идут ПОДРЯД все
метки, затем ПОДРЯД все значения в том же порядке.

    Заинтересованное лицо (должник):        <- метка 1
    Адрес регистрации:                      <- метка 2
    Петросян Генрих Суренович (ИНН …)       <- значение 1
    344049, г. Ростов-на-Дону, ул. Еляна…   <- значение 2

В ПЛОСКОМ ТЕКСТЕ это неразличимо: подпись одного поля оказывается перед
значением другого («Адрес регистрации: Петросян Генрих Суренович»). Построчный
разбор здесь бессилен — две попытки починить его цикл дали регрессии на 5 и на
7 документах корпуса. Колонки восстанавливаются только по разметке DOCX.

Приём в проекте уже был, но захардкоженный под ОДНУ сигнатуру ВТБ
(`_STACKED_SIG_RE`). Здесь то же правило, но метки берутся из реестра.

Слой заполняет ТОЛЬКО пустые поля — поэтому он не может ничего испортить, и
эталон на нём не сдвинулся (0 расхождений на корпусе из 66).
"""
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

from doc_structure import DocPart, stacked_label_pairs  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402


@pytest.fixture(scope="module")
def analyzer():
    return DocumentAnalyzer()


def _parts(*texts):
    return [DocPart(text=t, origin="body", para_index=i) for i, t in enumerate(texts)]


# --- чтение стопки ------------------------------------------------------------

def test_пары_по_порядку():
    parts = _parts(
        "Заинтересованное лицо (должник):",
        "Адрес регистрации:",
        "Петросян Генрих Суренович (ИНН 616305248218)",
        "344049, г. Ростов-на-Дону, ул. Еляна, д. 40, кв. 271",
    )
    assert stacked_label_pairs(parts) == [
        ("Заинтересованное лицо (должник):", "Петросян Генрих Суренович (ИНН 616305248218)"),
        ("Адрес регистрации:", "344049, г. Ростов-на-Дону, ул. Еляна, д. 40, кв. 271"),
    ]


def test_одна_метка_не_стопка():
    """Метка со значением ниже — обычная раскладка, трогать её нельзя."""
    parts = _parts("Должник:", "Иванов Иван Иванович", "ИНН 616305248218")
    assert stacked_label_pairs(parts) == []


def test_метка_разорванная_переносом_колонки():
    """«ФИНАНСОВЫЙ» + «УПРАВЛЯЮЩИЙ:» — одна метка на две части. Без склейки
    хвост метки принимается за ЗНАЧЕНИЕ, и все пары съезжают."""
    parts = _parts(
        "КРЕДИТОР:", "ДОЛЖНИК:", "ФИНАНСОВЫЙ", "УПРАВЛЯЮЩИЙ:",
        "Банк ВТБ (ПАО)", "Иванов Иван Иванович", "Петров Пётр Петрович",
    )
    pairs = stacked_label_pairs(parts)
    assert [lbl for lbl, _ in pairs] == ["КРЕДИТОР:", "ДОЛЖНИК:", "ФИНАНСОВЫЙ УПРАВЛЯЮЩИЙ:"]
    assert [val for _, val in pairs] == [
        "Банк ВТБ (ПАО)", "Иванов Иван Иванович", "Петров Пётр Петрович"]


def test_значения_обрываются_на_следующей_метке():
    """Если значений меньше, чем меток, лишние метки остаются без пары —
    додумывать за документ нельзя."""
    parts = _parts("Кредитор:", "Должник:", "ООО «Ромашка»", "Третье лицо:")
    assert stacked_label_pairs(parts) == [("Кредитор:", "ООО «Ромашка»")]


def test_пустой_вход():
    assert stacked_label_pairs([]) == []


# --- подстановка в поля -------------------------------------------------------

_PETROSYAN = _parts(
    "Заинтересованное лицо (должник):",
    "Адрес регистрации:",
    "Петросян Генрих Суренович (ИНН 616305248218)",
    "344049, г. Ростов-на-Дону, ул. Еляна, д. 40, кв. 271",
)


def _apply(analyzer, result, parts):
    """Обход чтения DOCX: подставляем готовую разметку."""
    analyzer._docx_structure = lambda *a, **kw: parts  # type: ignore[method-assign]
    try:
        analyzer._apply_stacked_header(result, "фиктивный.docx")
    finally:
        del analyzer._docx_structure


def test_уточнение_в_скобках_важнее_названия_блока(analyzer):
    """«Заинтересованное лицо (должник)» — это ДОЛЖНИК, хотя реестр относит
    «заинтересованное лицо» к третьим лицам. Без этого правила адрес уезжал в
    `thirdPartyAddress`."""
    result = {"fields": {}}
    _apply(analyzer, result, _PETROSYAN)
    assert result["fields"]["applicantAddress"].startswith("344049")
    assert "thirdPartyAddress" not in result["fields"]


def test_заполняются_только_пустые_поля(analyzer):
    """Свойство, из которого следует безопасность слоя: он не может подменить
    уже извлечённое значение."""
    result = {"fields": {"applicantAddress": "уже извлечено"}}
    _apply(analyzer, result, _PETROSYAN)
    assert result["fields"]["applicantAddress"] == "уже извлечено"


def test_карточка_должника_синхронизируется(analyzer):
    result = {"fields": {}, "debtors": [{"name": "Петросян Генрих Суренович", "address": ""}]}
    _apply(analyzer, result, _PETROSYAN)
    assert result["debtors"][0]["address"].startswith("344049")


def test_при_нескольких_должниках_карточки_не_трогаем(analyzer):
    """Чей это адрес — неизвестно, а угадывать нельзя."""
    result = {"fields": {}, "debtors": [{"address": ""}, {"address": ""}]}
    _apply(analyzer, result, _PETROSYAN)
    assert [d["address"] for d in result["debtors"]] == ["", ""]


def test_претензия_снимается_с_заполненного_поля(analyzer):
    """Контракт вычистил мусор («Петросян Генрих Суренович (» в адресе) и
    записал претензию «поле очищено». Слой подставил ВЕРНОЕ значение — значит
    претензию надо снять, иначе юрист видит заполненное поле с предупреждением
    «введите верное значение»."""
    result = {
        "fields": {},
        "debtors": [{"address": ""}],
        "fieldIssues": [
            {"field": "applicantAddress", "reason": "значение не содержит ни одного адресного признака",
             "value": "Петросян Генрих Суренович (", "cleared": True},
            {"field": "debtors[0].address", "reason": "значение не содержит ни одного адресного признака",
             "value": "Петросян Генрих Суренович (", "cleared": True},
        ],
        "fieldQuality": {"applicantAddress": {"level": "low", "cleared": True, "reasons": []}},
    }
    _apply(analyzer, result, _PETROSYAN)
    assert result["fieldIssues"] == []
    assert "applicantAddress" not in result["fieldQuality"]


def test_претензия_пометка_не_снимается(analyzer):
    """`cleared=False` — поле не очищалось, причина претензии могла остаться в
    силе. Снимать такую пометку слой не вправе."""
    result = {
        "fields": {},
        "fieldIssues": [
            {"field": "applicantAddress", "reason": "похоже на склейку",
             "value": "что-то", "cleared": False},
        ],
    }
    _apply(analyzer, result, _PETROSYAN)
    assert len(result["fieldIssues"]) == 1


def test_значение_проходит_контракт_поля(analyzer):
    """Слой не имеет права занести то, что контракт бы вычистил."""
    result = {"fields": {}}
    _apply(analyzer, result, _parts(
        "Должник:", "Адрес регистрации:",
        "Иванов Иван Иванович", "см. приложение"))
    assert "applicantAddress" not in result["fields"]


def test_подпись_поля_без_метки_блока_игнорируется(analyzer):
    """Роль берётся из метки блока. Если её не было, непонятно, чьё это поле."""
    result = {"fields": {}}
    _apply(analyzer, result, _parts(
        "Адрес регистрации:", "ИНН:", "344049, г. Ростов-на-Дону", "616305248218"))
    assert result["fields"] == {}
