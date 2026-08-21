# -*- coding: utf-8 -*-
"""Триаж golden-расхождений: где именно текущий analyze() разошёлся с эталоном.

Не тест, а инструмент разбора: печатает по каждому файлу список изменившихся
путей (поле → эталон/факт) и сводную гистограмму «какое поле ломается чаще».
Нужен, чтобы чинить причины (одна причина = N файлов), а не файлы по одному.
"""
import json
import logging
import os
import sys
from collections import Counter

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)
from _snapshot import APP_DIR, GOLDEN_PATH, corpus_files, snapshot_one  # noqa: E402

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

logging.disable(logging.CRITICAL)


def walk(exp, act, path=""):
    """Рекурсивный обход двух снимков → список (путь, эталон, факт)."""
    if type(exp) is not type(act):
        return [(path, exp, act)]
    if isinstance(exp, dict):
        out = []
        for k in sorted(set(exp) | set(act)):
            out += walk(exp.get(k, "<нет>"), act.get(k, "<нет>"), f"{path}.{k}" if path else k)
        return out
    if isinstance(exp, list):
        if len(exp) != len(act):
            return [(path + f"[len {len(exp)}→{len(act)}]", exp, act)]
        out = []
        for i, (e, a) in enumerate(zip(exp, act)):
            out += walk(e, a, f"{path}[{i}]")
        return out
    return [] if exp == act else [(path, exp, act)]


def short(v, n=90):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = s.replace("\n", "\n")
    return s if len(s) <= n else s[:n] + "…"


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    golden = json.load(open(GOLDEN_PATH, encoding="utf-8"))
    from document_analyzer import DocumentAnalyzer
    an = DocumentAnalyzer()
    hist, per_file = Counter(), {}
    for rel in corpus_files():
        if rel not in golden or (only and only not in rel):
            continue
        diffs = walk(golden[rel], snapshot_one(an, rel))
        if not diffs:
            continue
        per_file[rel] = diffs
        for p, _, _ in diffs:
            hist[p.split("[")[0]] += 1
    for rel, diffs in per_file.items():
        print(f"\n=== {rel}  ({len(diffs)} расхождений)")
        for p, e, a in diffs[:40]:
            print(f"  {p}\n     эталон: {short(e)}\n     факт  : {short(a)}")
        if len(diffs) > 40:
            print(f"  … ещё {len(diffs) - 40}")
    print(f"\n=== СВОДКА: {len(per_file)} файлов с расхождениями")
    for p, n in hist.most_common(40):
        print(f"  {n:4d}  {p}")


if __name__ == "__main__":
    main()
