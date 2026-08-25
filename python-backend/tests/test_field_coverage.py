# -*- coding: utf-8 -*-
"""Тесты свода отчёта покрытия (`tools/field_coverage.summarize`).

Проверяется чистое ядро: вход — сырые наблюдения, выход — свод. Прогон корпуса
здесь не нужен и не делается, поэтому тесты быстрые и детерминированные.

Каждая проверка отвечает на вопрос «а не соврёт ли отчёт»: врущий отчёт о
качестве хуже отсутствующего — он уводит правку не туда.
"""
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "tools")))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "golden")))

from field_coverage import (  # noqa: E402
    _is_empty,
    field_consumers,
    probe_evidence,
    summarize,
)


def _raw(docs, declared=None, hits=None, all_patterns=None, consumers=None):
    return {
        "docs": docs,
        "declaredByType": declared or {},
        "patternHits": hits or {},
        "allPatterns": all_patterns or {},
        "consumers": consumers or {},
    }


def _doc(name, doc_type, fields, issues=None, quality=None, evidence=None):
    return {
        "file": name,
        "documentType": doc_type,
        "fields": fields,
        "fieldIssues": issues or [],
        "fieldQuality": quality or {},
        "evidence": evidence or {},
    }


class TestПустота:
    """Ноль и False — законные значения, а не пробел."""

    def test_ноль_и_false_не_пустота(self):
        assert _is_empty(0) is False
        assert _is_empty(0.0) is False
        assert _is_empty(False) is False

    def test_none_пустой_список_и_пробелы_пустота(self):
        assert _is_empty(None) is True
        assert _is_empty([]) is True
        assert _is_empty({}) is True
        assert _is_empty("   ") is True

    def test_обычное_значение_не_пустота(self):
        assert _is_empty("ООО Ромашка") is False
        assert _is_empty(["x"]) is False


class TestПробелы:
    def test_отсутствующий_ключ_считается_пробелом(self):
        """Регрессия: раньше поле без ключа не попадало ни в «заполнено», ни в
        «пусто» — и отчёт показывал «заполнено 2/3, пусто в 0»."""
        s = summarize(_raw([
            _doc("a.docx", "rtk", {"inn": "7707083893"}),
            _doc("b.docx", "rtk", {"inn": "7707083893"}),
            _doc("c.docx", "rtk", {}),  # ключа нет вовсе
        ]))
        st = s["perType"]["rtk"]["inn"]
        assert st["filled"] == 2
        assert st["total"] == 3
        assert st["gaps"] == ["c.docx"]
        assert st["emptyKey"] == []  # ключа не было, а не был пустым

    def test_пустое_значение_отмечается_отдельно_от_отсутствия(self):
        """Пустой ключ означает «извлекатель отработал»: либо не нашёл, либо
        значение вычистил контракт. Это другой диагноз, чем «ключа нет»."""
        s = summarize(_raw([
            _doc("a.docx", "rtk", {"addr": "г. Москва"}),
            _doc("b.docx", "rtk", {"addr": ""}),
            _doc("c.docx", "rtk", {}),
        ]))
        st = s["perType"]["rtk"]["addr"]
        assert st["filled"] == 1
        assert sorted(st["gaps"]) == ["b.docx", "c.docx"]
        assert st["emptyKey"] == ["b.docx"]


class TestРазрезПоТипу:
    def test_поля_чужого_типа_не_считаются_пробелом(self):
        """Ипотечное поле не должно всплывать пробелом в банкротных заявлениях:
        иначе настоящие пробелы утонут в шуме."""
        s = summarize(_raw(
            [
                _doc("ипотека.docx", "mortgage_claim", {"mortgagePrice": "1 000"}),
                _doc("ртк1.docx", "rtk_application", {"inn": "7707083893"}),
                _doc("ртк2.docx", "rtk_application", {"inn": "7707083893"}),
            ],
            declared={"rtk_application": ["inn"], "mortgage_claim": ["mortgagePrice"]},
        ))
        assert "mortgagePrice" not in s["perType"]["rtk_application"]
        assert "inn" not in s["perType"]["mortgage_claim"]

    def test_объявленное_но_никогда_не_извлечённое_поле_видно(self):
        """Поле объявлено в паттернах типа и молчит — главный сигнал отчёта.
        Без объявления его бы не было видно вообще: в fields оно не появляется."""
        s = summarize(_raw(
            [_doc("a.docx", "rtk", {"inn": "7707083893"})],
            declared={"rtk": ["inn", "ogrn"]},
        ))
        assert s["perType"]["rtk"]["ogrn"]["filled"] == 0
        assert s["perType"]["rtk"]["ogrn"]["gaps"] == ["a.docx"]


class TestДиагнозПаттернов:
    """Различение «паттерна нет» и «паттерн совпал, значение отброшено» — то,
    ради чего отчёт вообще строится: это два РАЗНЫХ ремонта."""

    def test_все_паттерны_мертвы(self):
        s = summarize(_raw(
            [_doc("a.docx", "rtk", {})],
            declared={"rtk": ["ogrn"]},
            hits={},  # ни одного совпадения
            all_patterns={"ogrn\x00p1": "ogrn", "ogrn\x00p2": "ogrn"},
        ))
        assert s["deadByField"]["ogrn"] == 2
        assert s["patternsByField"]["ogrn"] == 2

    def test_паттерн_совпадал_но_поле_пусто(self):
        """Самый ценный случай: значение в тексте есть, регулярка срабатывает,
        а до поля оно не доходит — виновата логика извлечения, не паттерн."""
        s = summarize(_raw(
            [_doc("a.docx", "rtk", {"ogrn": ""})],
            declared={"rtk": ["ogrn"]},
            hits={"ogrn\x00p1": 1},
            all_patterns={"ogrn\x00p1": "ogrn", "ogrn\x00p2": "ogrn"},
        ))
        assert s["deadByField"]["ogrn"] == 1  # мёртв только p2
        assert s["patternsByField"]["ogrn"] == 2
        assert s["perType"]["rtk"]["ogrn"]["filled"] == 0


class TestКачество:
    def test_уровни_и_претензии_сводятся(self):
        s = summarize(_raw([
            _doc(
                "a.docx", "rtk", {"inn": "7707083893"},
                issues=[{"field": "addr", "reason": "в адресе подпись другого поля"}],
                quality={"inn": {"level": "high"}, "addr": {"level": "low"}},
            ),
            _doc(
                "b.docx", "rtk", {"inn": "7707083893"},
                issues=[{"field": "addr", "reason": "в адресе подпись другого поля"}],
                quality={"inn": {"level": "high"}},
            ),
        ]))
        assert s["levels"]["high"] == 2
        assert s["levels"]["low"] == 1
        assert s["reasons"][0] == ("в адресе подпись другого поля", 2)
        assert s["reasonFiles"]["в адресе подпись другого поля"] == ["a.docx", "b.docx"]


class TestНеразобравшиесяДокументы:
    def test_упавший_документ_не_ломает_свод_и_виден(self):
        """Документ, на котором analyze() бросил исключение, обязан попасть в
        отчёт: молча потерянный документ — худший вид пробела."""
        s = summarize(_raw([
            _doc("ok.docx", "rtk", {"inn": "7707083893"}),
            {"file": "битый.docx", "error": "KeyError: 'x'"},
        ]))
        assert s["totalDocs"] == 1  # в статистику идут только разобранные
        assert len(s["brokenDocs"]) == 1
        assert s["brokenDocs"][0]["file"] == "битый.docx"


class TestУлики:
    """Зонд «данные есть» обязан отличать СВОЙ реквизит от чужого.

    Разбор корпуса дал цену ошибки: из 82 срабатываний широких зондов
    настоящими потерями оказались 28. Проверки ниже — ровно про те три
    подмены, которые давали больше всего шума.
    """

    def test_боилерплейт_про_управляющего_не_улика(self):
        """«финансовый управляющий» без ФИО есть в КАЖДОМ заявлении."""
        assert probe_evidence(
            "В силу закона финансовый управляющий утверждается судом", "managerName") is None
        assert probe_evidence(
            "Вознаграждение финансового управляющего составляет 25000 руб.", "managerName") is None

    def test_имя_сро_не_принимается_за_фио_управляющего(self):
        """«из числа членов Ассоциации Гарант» выглядит как ФИО ничуть не хуже."""
        assert probe_evidence(
            "финансового управляющего из числа членов Ассоциации Гарант", "managerName") is None

    def test_фио_управляющего_в_любой_форме_улика(self):
        for text in (
            "Финансовый управляющий: Бубнова Светлана Васильевна",
            "арбитражным управляющим утвердить Теплова Алексея Сергеевича",
            "Финансовым управляющим должника утвержден(-а) Рябинина Екатерина Сергеевна",
        ):
            assert probe_evidence(text, "managerName"), text

    def test_инн_сро_не_улика_для_инн_управляющего(self):
        """Управляющий — физлицо, его ИНН всегда 12 знаков.

        Десятизначный рядом со словом «управляющий» принадлежит СРО или
        должнику-ЮЛ: на корпусе это 16 ложных срабатываний из 21.
        """
        assert probe_evidence(
            "финансового управляющего из числа членов Ассоциации (ИНН 0274107073)",
            "managerInn") is None
        assert probe_evidence(
            "арбитражным управляющим Теплова Алексея Сергеевича ИНН 582704406654",
            "managerInn")

    def test_реквизит_чужой_стороны_не_улика(self):
        """ИНН кредитора — не улика того, что потерян ИНН должника."""
        text = "Кредитор: ООО ПКО Юнона ИНН: 7806253521"
        assert probe_evidence(text, "creditorInn")
        assert probe_evidence(text, "inn") is None

    def test_улики_собираются_только_по_пустым_полям(self):
        s = summarize(_raw([
            _doc("a.docx", "rtk", {"snils": ""}, evidence={"snils": "СНИЛС 136-024-294 28"}),
            _doc("b.docx", "rtk", {"snils": "063-843-816 80"}),
        ]))
        assert list(s["evidenceGaps"]) == ["snils"]
        assert s["evidenceGaps"]["snils"] == [
            {"file": "a.docx", "text": "СНИЛС 136-024-294 28"}
        ]


class TestНечитаемыеПоля:
    """Поле, которое никто не читает, даёт в отчёте ЛОЖНЫЙ НОЛЬ.

    Так вышло с «паспортом»: имя `passport` живёт только в реестре меток
    `label_synonyms.FIELD_LABELS`, извлекателя у него нет вовсе и не читает его
    никто — а настоящие данные лежат в `passportSeries` / `passportNumber`.
    Поле выглядело безнадёжно сломанным, чинить в нём было нечего.
    """

    def test_поле_без_потребителей_помечено(self):
        s = summarize(_raw(
            [_doc("a.docx", "rtk", {"passport": "", "inn": "7707083893"})],
            consumers={"passport": [], "inn": ["генератор", "фронт"]},
        ))
        assert s["unreadFields"] == ["passport"]

    def test_поле_вне_списка_потребителей_не_объявляется_мёртвым(self):
        """Молчание — не приговор: о поле, которого нет в разборе потребителей,
        отчёт не имеет права утверждать, что его никто не читает."""
        s = summarize(_raw(
            [_doc("a.docx", "rtk", {"неизвестное": ""})],
            consumers={},
        ))
        assert s["unreadFields"] == []


class TestПотребителиПоля:
    def _fake_root(self, tmp_path):
        app = tmp_path / "app"
        app.mkdir(parents=True, exist_ok=True)
        (app / "document_generator.py").write_text(
            'MARKERS = {"creditorAddress": "988"}', encoding="utf-8")
        front = tmp_path.parent / "electron-app" / "src"
        front.mkdir(parents=True, exist_ok=True)
        (front / "types.ts").write_text(
            "export interface F { managerSnils?: string }", encoding="utf-8")
        return str(tmp_path)

    def test_находит_генератор_и_фронт(self, tmp_path):
        root = self._fake_root(tmp_path / "backend")
        got = field_consumers(["creditorAddress", "managerSnils", "passport"], root)
        assert got["creditorAddress"] == ["генератор"]
        assert got["managerSnils"] == ["фронт"]
        assert got["passport"] == []

    def test_совпадение_только_по_целому_слову(self, tmp_path):
        """`inn` не должен «находиться» внутри `creditorInn`."""
        root = self._fake_root(tmp_path / "backend")
        assert field_consumers(["Address"], root)["Address"] == []
