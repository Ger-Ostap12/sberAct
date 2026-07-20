# -*- coding: utf-8 -*-
"""Измеритель сверки имени должника: regex `debtorName` против второго
независимого экстрактора `semantic_classifier.classify_debtor_name` (NER-харвест
по окну шапка+просьба + ролевой скоринг). План `new_asnaliz`, ось «имя должника»,
первый заход.

Сравнение по каноничному ключу `_debtor_key` (вид лица + фамилия/инициалы либо
`org_normalizer`). Совпало — согласие; семантика воздержалась (None) — abstain;
расходятся ключи — расхождение (кандидат в баннер `debtorNameWarning`).

Запуск: cd python-backend && venv/Scripts/python.exe tests/measure_debtor_name.py
"""
import logging
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.disable(logging.CRITICAL)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.join(_THIS, "golden"))

from _snapshot import corpus_files, CORPUS_DIR  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402
from semantic_classifier import (  # noqa: E402
    classify_debtor_name,
    debtor_names_match,
    _debtor_key,
)


def main() -> int:
    az = DocumentAnalyzer()
    files = corpus_files()
    agree = 0
    abstain = []
    disagree = []
    no_regex = 0

    for rel in files:
        path = os.path.join(CORPUS_DIR, rel)
        try:
            result = az.analyze(path)
        except Exception as exc:
            print(f"[ОШИБКА] {rel}: {exc}")
            continue
        raw_text = result.get("rawText", "")
        regex_name = (result.get("fields") or {}).get("debtorName", "") or ""
        if not regex_name.strip():
            no_regex += 1
            continue
        sem_name, meta = classify_debtor_name(raw_text)
        if not sem_name:
            abstain.append((rel, regex_name))
            continue
        if debtor_names_match(regex_name, sem_name):
            agree += 1
        else:
            disagree.append((rel, regex_name, sem_name, meta))

    decided = agree + len(disagree)
    print("=" * 72)
    print(f"Корпус: {len(files)} файлов")
    print(f"regex не дал имя (пропущены): {no_regex}")
    print(f"семантика воздержалась (abstain): {len(abstain)}")
    print(f"Согласие regex/семантика (там, где оба дали имя): {agree}/{decided} "
          f"({100 * agree // max(decided, 1)}%)")
    print("=" * 72)
    print("РАСХОЖДЕНИЯ (кандидаты в debtorNameWarning):")
    for rel, rn, sn, meta in disagree:
        print(f"  {rel}")
        print(f"    regex   : {rn!r}  -> {_debtor_key(rn)!r}")
        print(f"    семантика: {sn!r}  -> {_debtor_key(sn)!r}  {meta}")
    print("-" * 72)
    print("ВОЗДЕРЖАНИЯ (семантика не привязала кандидата к якорю должника):")
    for rel, rn in abstain:
        print(f"  {rel}  regex={rn!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
