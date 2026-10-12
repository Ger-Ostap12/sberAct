# -*- coding: utf-8 -*-
"""Страж белого списка снимка golden: новый ключ analyze не должен выпасть молча.

Каждый ключ верхнего уровня обязан быть либо в `_TOP_FIELDS`, либо в списке
исключённых здесь — с причиной.
"""
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_THIS, "golden"))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))

import _snapshot as snap  # noqa: E402

# Ключи, которых в снимке нет НАМЕРЕННО. Причина обязательна — без неё список
# превращается в свалку, и страж перестаёт сторожить.
ИСКЛЮЧЕНЫ = {
    # Огромен и дублирует вход; вместо него rawTextLen + rawTextSha.
    "rawText",
    # 154 КБ (+41% к эталону) и почти целиком проекция fieldIssues и
    # происхождения полей: перекрашивается от любой смены порядка слоёв,
    # давая красноту без нового смысла.
    "fieldQuality",
}


@pytest.fixture(scope="module")
def ключи_анализа():
    """Ключи верхнего уровня на нескольких документах корпуса."""
    from document_analyzer import DocumentAnalyzer

    файлы = snap.corpus_files()
    if not файлы:
        pytest.skip("корпус недоступен")
    анализатор = DocumentAnalyzer()
    ключи = set()
    for rel in файлы[:6]:
        путь = os.path.join(snap.CORPUS_DIR, rel.replace("/", os.sep))
        ключи |= set(анализатор.analyze(путь))
    return ключи


def test_новых_ключей_вне_списка_нет(ключи_анализа):
    """Каждый ключ analyze — либо в снимке, либо в ИСКЛЮЧЕНЫ с причиной."""
    забытые = sorted(ключи_анализа - set(snap._TOP_FIELDS) - ИСКЛЮЧЕНЫ)
    assert not забытые, (
        "ключи analyze не попадают в снимок golden и не объявлены исключёнными: "
        + ", ".join(забытые)
        + ". Добавь в _TOP_FIELDS (и перегенерируй эталон) либо в ИСКЛЮЧЕНЫ с причиной."
    )


def test_список_исключений_не_протух(ключи_анализа):
    """Исключение на ключ, которого больше нет, — мусор: убрать из списка."""
    мёртвые = sorted(ИСКЛЮЧЕНЫ - ключи_анализа)
    assert not мёртвые, (
        "в ИСКЛЮЧЕНЫ перечислены ключи, которых analyze больше не отдаёт: "
        + ", ".join(мёртвые)
    )


def test_исключённые_в_снимок_не_попали():
    """Обратная сторона: исключённый ключ не должен оказаться в белом списке."""
    пересечение = sorted(ИСКЛЮЧЕНЫ & set(snap._TOP_FIELDS))
    assert not пересечение, (
        "ключ объявлен исключённым и одновременно лежит в _TOP_FIELDS: "
        + ", ".join(пересечение)
    )


@pytest.mark.parametrize("ключ", [
    # Кнопки и условные блоки формы — три фичи статуса, самобанкрот, ипотека.
    "debtorStatusHint", "applicationKind", "mortgageKind",
    # Предмет ипотеки юрист видит на форме.
    "mortgageProperties",
    # Тултип «откуда число»: слагаемые можно подменить, не меняя итог.
    "financeBreakdown",
    # Пометки юристу: ложная пометка — такой же дефект, как ложное значение.
    "fieldIssues",
    "documentTypeWarning", "debtorNameWarning", "entityTypeWarning",
    "collateralWarning",
])
def test_ключи_закрытой_дыры_остаются_в_снимке(ключ):
    """Эти десять ключей добавлены 12.10.2026 — не дать убрать их обратно."""
    assert ключ in snap._TOP_FIELDS, f"{ключ} убран из снимка — дыра  открыта снова"
