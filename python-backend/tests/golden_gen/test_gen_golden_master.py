# -*- coding: utf-8 -*-
"""Output-golden сверка: текущий generate() == зафиксированный текст документов.

СЕТЬ БЕЗОПАСНОСТИ для рефакторинга `document_generator.py`. Любое СТРУКТУРНОЕ
изменение (разбиение replace_document_data/generate, вынос резолверов шаблонов
в модули) обязано оставлять рендеренный текст итоговых .docx прежним — тогда
тесты зелёные. Падение после рефакторинга = регрессия, её нужно устранить
(а не регенерировать эталон).

Эталон регенерируется только при осознанном изменении вывода через
regenerate_gen_golden.py.
"""
import json
import logging
import os
import sys

import pytest

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)

from _gen_snapshot import GOLDEN_PATH, corpus_files, snapshot_one  # noqa: E402



def _load_golden():
    if not os.path.exists(GOLDEN_PATH):
        return None
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


_GOLDEN = _load_golden()
with open(os.path.join(_THIS, "unavailable_cases.json"), encoding="utf-8") as source:
    _UNAVAILABLE = json.load(source)
_FILES = corpus_files()


@pytest.fixture(scope="module")
def analyzer():
    from document_analyzer import DocumentAnalyzer
    return DocumentAnalyzer()


@pytest.fixture(scope="module")
def generator():
    from document_generator import DocumentGenerator
    return DocumentGenerator()


@pytest.mark.skipif(_GOLDEN is None, reason="output-эталон ещё не сгенерирован")
@pytest.mark.skipif(not _FILES, reason="корпус Заявления/ недоступен")
def test_gen_golden_corpus_unchanged_fileset():
    """Набор входных файлов совпадает с зафиксированным в эталоне."""
    assert set(_FILES) == set(_GOLDEN.keys()), (
        "состав корпуса изменился относительно эталона: "
        f"добавлены={set(_FILES) - set(_GOLDEN.keys())}, "
        f"удалены={set(_GOLDEN.keys()) - set(_FILES)}"
    )


@pytest.mark.skipif(_GOLDEN is None, reason="output-эталон ещё не сгенерирован")
@pytest.mark.parametrize("rel_path", _FILES or [])
def test_gen_golden_master_per_file(analyzer, generator, rel_path):
    """Текст сгенерированных документов на каждом входе идентичен эталону."""
    if rel_path not in _GOLDEN:
        pytest.skip(f"{rel_path} отсутствует в эталоне")
    expected = _GOLDEN[rel_path]
    actual = snapshot_one(analyzer, generator, rel_path)
    assert "__error__" not in actual, actual
    if rel_path in _UNAVAILABLE:
        assert actual.get("rejection", {}).get("code") == _UNAVAILABLE[rel_path]["code"], actual
    else:
        assert "rejection" not in actual, actual
    exp_s = json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=1)
    act_s = json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=1)
    assert act_s == exp_s, f"Регрессия в generate() для {rel_path}"


@pytest.mark.skipif(_GOLDEN is None, reason="No generation baseline")
def test_expected_rejection_registry_matches_baseline():
    assert set(_UNAVAILABLE) <= set(_FILES)
    rejected = {name for name, value in _GOLDEN.items() if "rejection" in value}
    assert rejected == set(_UNAVAILABLE)
    assert all("__error__" not in value for value in _GOLDEN.values())
