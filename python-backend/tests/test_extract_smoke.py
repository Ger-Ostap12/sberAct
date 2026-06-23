# -*- coding: utf-8 -*-
"""Интеграционный smoke: извлечение текста из реальных заявлений без падений.

Пропускается, если каталог Заявления/ отсутствует (не в репозитории на CI).
"""
import glob
import os

import pytest

_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Заявления"))


def _docx_samples(limit=8):
    if not os.path.isdir(_BASE):
        return []
    files = [f for f in glob.glob(os.path.join(_BASE, "**", "*.docx"), recursive=True)
             if "~$" not in f]
    return sorted(files)[:limit]


SAMPLES = _docx_samples()


@pytest.mark.skipif(not SAMPLES, reason="каталог Заявления/ недоступен")
@pytest.mark.parametrize("path", SAMPLES)
def test_extract_text_no_crash(path):
    from document_analyzer import DocumentAnalyzer
    da = DocumentAnalyzer()
    text = da.extract_text(path)
    assert isinstance(text, str)
    assert len(text) > 0
