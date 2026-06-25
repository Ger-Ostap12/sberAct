# -*- coding: utf-8 -*-
"""Измеритель качества извлечения на чужих/иных раскладках (casebookWord).

Сравнивает текущий analyze() с эталоном правильных значений expected_other_banks.json
(мягкая нормализация). Печатает по каждому документу совпавшие/несовпавшие поля и
итоговый процент. Базовая линия ДО правок — точка отсчёта улучшения.

Запуск: cd python-backend && venv/Scripts/python.exe tests/measure_other_banks.py
"""
import json
import logging
import os
import re
import sys

logging.disable(logging.CRITICAL)
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
CORPUS = os.path.abspath(os.path.join(_THIS, "..", "..", "Заявления"))
EXPECTED = os.path.join(_THIS, "expected_other_banks.json")

from document_analyzer import DocumentAnalyzer  # noqa: E402


def norm(v) -> str:
    """Мягкая нормализация для сравнения: регистр, кавычки, пробелы, ИП-префикс, разделители сумм."""
    if v is None:
        return ""
    s = str(v).strip().lower()
    s = s.replace("«", "").replace("»", "").replace('"', "").replace("'", "")
    s = re.sub(r"^\s*(ип|ооо|ао|пао|оао|зао)\s+", "", s)  # ОПФ-префикс не учитываем
    s = s.replace(" ", " ").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" ,", ",").replace(", ", ",")
    return s.strip()


def amount_norm(v) -> str:
    return re.sub(r"[^\d]", "", str(v or "")).lstrip("0")


def main() -> int:
    expected = json.load(open(EXPECTED, encoding="utf-8"))
    az = DocumentAnalyzer()
    total = ok = 0
    for rel, exp in expected.items():
        if rel.startswith("_"):
            continue
        p = os.path.join(CORPUS, rel)
        print("=" * 70)
        print(rel.split("/")[-1], "|", exp.get("_bank", ""))
        if not os.path.exists(p):
            print("  НЕТ ФАЙЛА"); continue
        fields = az.analyze(p).get("fields", {})
        for k, want in exp.items():
            if k.startswith("_"):
                continue
            got = fields.get(k)
            if k == "totalDebt":
                hit = amount_norm(got) == amount_norm(want)
            elif want == "":
                hit = not (got and str(got).strip())
            else:
                hit = norm(got) == norm(want) or (norm(want) in norm(got) and norm(want) != "")
            total += 1
            ok += 1 if hit else 0
            mark = "OK " if hit else "FAIL"
            print(f"  [{mark}] {k}: want={want!r} got={got!r}")
    print("=" * 70)
    print(f"ИТОГО правильных полей: {ok}/{total} ({100*ok//max(total,1)}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
