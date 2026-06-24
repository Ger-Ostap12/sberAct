# -*- coding: utf-8 -*-
"""Проверка инварианта при удалении хардкода: РЕАЛЬНЫЕ документы (не из _synthetic.json)
обязаны давать снимок, идентичный golden. Синтетические фикстуры могут меняться.

Запуск: venv/Scripts/python.exe tests/golden/check_invariant.py
Выход 0 — реальные не изменились; 1 — есть изменения среди реальных (регрессия).
"""
import io
import json
import logging
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "..", "app")))
logging.disable(logging.CRITICAL)

from _snapshot import GOLDEN_PATH, corpus_files, snapshot_one  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402

gold = json.load(io.open(GOLDEN_PATH, encoding="utf-8"))
syn_path = os.path.join(_THIS, "_synthetic.json")
synthetic = set(json.load(io.open(syn_path, encoding="utf-8"))) if os.path.exists(syn_path) else set()

da = DocumentAnalyzer()
real_changed, syn_changed = [], []
for rel in corpus_files():
    if rel not in gold:
        continue
    act = json.dumps(snapshot_one(da, rel), ensure_ascii=False, sort_keys=True)
    exp = json.dumps(gold[rel], ensure_ascii=False, sort_keys=True)
    if act != exp:
        (syn_changed if rel in synthetic else real_changed).append(rel)

print(f"Синтетических изменилось: {len(syn_changed)} (ожидаемо)")
for s in syn_changed:
    print(f"  ~ {s}")
print(f"РЕАЛЬНЫХ изменилось: {len(real_changed)} (должно быть 0)")
for r in real_changed:
    print(f"  ! {r}")
sys.exit(1 if real_changed else 0)
