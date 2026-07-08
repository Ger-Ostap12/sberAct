# -*- coding: utf-8 -*-
"""Тесты детектора САМОБАНКРОТСТВА (`_detect_self_bankruptcy`).

Самобанкротство — заявление о банкротстве подаёт сам должник. Детектор — слои:
вето (кредиторские приметы/ФНС) → обязательное отсутствие «включить в РТК/очередь»
в просительной части → хотя бы один сильный сигнал (первое лицо, заголовок
заявления должника, «Заявитель (Должник)», шапка «должник первым»).

Позитивы — реальные .docx из `Заявления/Самобанкрот/` (по имени, без индексов:
файлы двигаются) + синтетические фрагменты краевых случаев (склеенный без
пробелов текст конвертации из PDF). Негативы — кредиторские ловушки из корпуса:
«должник первым» при «Заявитель (Кредитор)» (САРМАТ/БАЗОВ), включение в РТК, ФНС.
"""
import glob
import os

import pytest

from document_analyzer import DocumentAnalyzer

CORPUS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "Заявления")
)
SELF_BK_DIR = os.path.join(CORPUS_DIR, "Самобанкрот")


@pytest.fixture(scope="module")
def da():
    return DocumentAnalyzer()


def _corpus_docx_by_key(key: str):
    """Первый .docx корпуса, содержащий key в пути (индексы плавают — ищем по имени)."""
    for f in sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.docx"), recursive=True)):
        if key.lower() in os.path.relpath(f, CORPUS_DIR).lower() and "~$" not in f:
            return f
    return None


# --- Позитивы: все реальные самобанкроты распознаются ------------------------
def _self_bk_files():
    return sorted(glob.glob(os.path.join(SELF_BK_DIR, "*.docx")))


@pytest.mark.parametrize(
    "path", _self_bk_files(), ids=[os.path.basename(f) for f in _self_bk_files()]
)
def test_real_self_bankruptcy_detected(da, path):
    text = da.extract_text(path)
    assert da._detect_self_bankruptcy(text) is True


def test_self_bankruptcy_folder_present():
    # Страж: если папку переместили — позитивы выше молча опустеют, ловим явно.
    assert _self_bk_files(), "в Заявления/Самобанкрот/ нет .docx"


def test_analyze_sets_application_kind(da):
    # Флаг уходит top-level (НЕ в fields → не в golden и не в editedFields фронта).
    files = _self_bk_files()
    result = da.analyze(files[0])
    assert result["applicationKind"] == "self_bankruptcy"
    assert "applicationKind" not in result["fields"]


# --- Негативы: кредиторские заявления корпуса --------------------------------
@pytest.mark.parametrize("key", [
    "САРМАТ",      # «должник первым» в шапке, но «Заявитель (Кредитор): ПАО Сбербанк»
    "БАЗОВ",       # аналогичная ловушка «только должник» в шапке
    "вкл в ртк",   # включение в РТК — «включить … в реестр требований»
])
def test_creditor_applications_not_self(da, key):
    path = _corpus_docx_by_key(key)
    if path is None:
        pytest.skip(f"файл с ключом «{key}» не найден в корпусе (перемещён)")
    text = da.extract_text(path)
    assert da._detect_self_bankruptcy(text) is False


def test_whole_corpus_no_false_positives(da):
    # Ни один документ корпуса ВНЕ папки Самобанкрот не должен детектиться.
    fp = []
    for f in sorted(glob.glob(os.path.join(CORPUS_DIR, "**", "*.docx"), recursive=True)):
        rel = os.path.relpath(f, CORPUS_DIR)
        if "~$" in f or rel.startswith("Самобанкрот"):
            continue
        if da._detect_self_bankruptcy(da.extract_text(f)):
            fp.append(rel)
    assert fp == []


# --- Синтетические краевые случаи (слои детектора) ----------------------------
_PRAYER_SELF = "ПРОШУ:\n1. Признать меня несостоятельным (банкротом).\n2. Ввести процедуру реализации имущества."


def test_glued_pdf_text(da):
    # Конвертация из PDF склеивает слова — паттерны обязаны работать без пробелов.
    text = "Должник:ИвановИванИванович\nКредиторы:ПАОСбербанк\nЗАЯВЛЕНИЕФИЗИЧЕСКОГОЛИЦА\nопризнанииегонесостоятельным(банкротом)\nПРОШУ:Признатьменябанкротом."
    assert da._detect_self_bankruptcy(text) is True


def test_veto_applicant_creditor_wins(da):
    # «Заявитель (Кредитор)» перебивает любые сильные сигналы.
    text = "Заявитель (Кредитор): ПАО Сбербанк\nДолжник: Иванов И.И.\n" + _PRAYER_SELF
    assert da._detect_self_bankruptcy(text) is False


def test_veto_vzyskat_v_polzu(da):
    text = "Должник: Иванов И.И.\nПРОШУ:\n1. Признать меня банкротом.\n2. Взыскать с должника в пользу ПАО Сбербанк 100 руб."
    assert da._detect_self_bankruptcy(text) is False


def test_rtk_in_prayer_blocks(da):
    # Ключевой контр-сигнал: «включить в третью очередь» в просительной части.
    text = ("Должник: Иванов И.И.\nКредиторы: ПАО Сбербанк\n"
            "ПРОШУ:\n1. Признать Иванова И.И. банкротом.\n"
            "2. Включить требования в третью очередь реестра требований кредиторов.")
    assert da._detect_self_bankruptcy(text) is False


def test_applicant_is_debtor_signature(da):
    # Подпись «Заявитель (Должник):» — явный сильный сигнал (файл Федоренко).
    text = ("Федоренко Алексей Алексеевич\nКредитор 1. ООО МКК «Русинтерфинанс»\n"
            "ПРОШУ:\nПризнать гражданина РФ Федоренко А.А. несостоятельным (банкротом).\n"
            "Заявитель (Должник):\nГражданин Российской Федерации")
    assert da._detect_self_bankruptcy(text) is True


def test_no_strong_signals_negative(da):
    # Нет ни вето, ни РТК, но и сильных сигналов нет — не самобанкрот.
    text = "Некоторый текст про банкротство без примет.\nПРОШУ:\nНазначить управляющего."
    assert da._detect_self_bankruptcy(text) is False
