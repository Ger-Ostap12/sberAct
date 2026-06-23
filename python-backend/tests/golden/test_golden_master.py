# -*- coding: utf-8 -*-
"""Golden-master сверка: текущий analyze() == зафиксированный эталон.

ЭТО СЕТЬ БЕЗОПАСНОСТИ для рефакторинга. Любое СТРУКТУРНОЕ изменение
(разбиение функций, вынос модулей) обязано оставлять вывод побайтово прежним —
тогда эти тесты зелёные. Если тест упал после рефакторинга — это регрессия,
её нужно устранить (а не регенерировать эталон).

Эталон намеренно регенерируется только при осознанном изменении поведения
(удаление хардкода, улучшение анализа) через regenerate_golden.py.
"""
import json
import logging
import os

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, _THIS)

from _snapshot import GOLDEN_PATH, corpus_files, snapshot_one  # noqa: E402

logging.disable(logging.CRITICAL)


def _load_golden():
    if not os.path.exists(GOLDEN_PATH):
        return None
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


_GOLDEN = _load_golden()
_FILES = corpus_files()


@pytest.fixture(scope="module")
def analyzer():
    from document_analyzer import DocumentAnalyzer
    return DocumentAnalyzer()


@pytest.mark.skipif(_GOLDEN is None, reason="эталон ещё не сгенерирован")
@pytest.mark.skipif(not _FILES, reason="корпус Заявления/ недоступен")
def test_golden_corpus_unchanged_fileset():
    """Набор файлов корпуса совпадает с зафиксированным в эталоне."""
    assert set(_FILES) == set(_GOLDEN.keys()), (
        "состав корпуса изменился относительно эталона: "
        f"добавлены={set(_FILES) - set(_GOLDEN.keys())}, "
        f"удалены={set(_GOLDEN.keys()) - set(_FILES)}"
    )


@pytest.mark.skipif(_GOLDEN is None, reason="эталон ещё не сгенерирован")
@pytest.mark.parametrize("rel_path", _FILES or [])
def test_golden_master_per_file(analyzer, rel_path):
    """Поведение analyze() на каждом документе идентично эталону."""
    if rel_path not in _GOLDEN:
        pytest.skip(f"{rel_path} отсутствует в эталоне")
    expected = _GOLDEN[rel_path]
    actual = snapshot_one(analyzer, rel_path)
    # Сравниваем через канонический JSON — порядок ключей не важен, значения строгие.
    exp_s = json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=1)
    act_s = json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=1)
    assert act_s == exp_s, f"Регрессия в analyze() для {rel_path}"
