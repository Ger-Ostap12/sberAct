# -*- coding: utf-8 -*-
"""Генератор golden-master эталона.

ЗАПУСКАТЬ ВРУЧНУЮ и ТОЛЬКО осознанно — он перезаписывает зафиксированный эталон
поведения. После структурного рефакторинга эталон трогать НЕЛЬЗЯ (вывод должен
совпасть). Регенерация оправдана лишь когда поведение изменено намеренно
(удаление хардкода, улучшение анализа) и новый вывод проверен вручную.

Использование:
    venv/Scripts/python.exe tests/golden/regenerate_golden.py
"""
import json
import logging
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "..", "app")))

from _snapshot import APP_DIR, GOLDEN_PATH, build_snapshot, corpus_files  # noqa: E402

logging.disable(logging.CRITICAL)  # тихий прогон

from document_analyzer import DocumentAnalyzer  # noqa: E402


def main() -> int:
    files = corpus_files()
    if not files:
        print("Корпус Заявления/ не найден — нечего фиксировать", file=sys.stderr)
        return 1
    print(f"Корпус: {len(files)} документов. Генерируем эталон...")
    analyzer = DocumentAnalyzer()
    snapshot = build_snapshot(analyzer, files)

    errors = [f for f, s in snapshot.items() if "__error__" in s]
    with open(GOLDEN_PATH, "w", encoding="utf-8") as w:
        json.dump(snapshot, w, ensure_ascii=False, indent=1, sort_keys=True)

    print(f"Эталон сохранён: {GOLDEN_PATH}")
    print(f"  документов: {len(snapshot)}")
    print(f"  с ошибкой анализа: {len(errors)}")
    for f in errors:
        print(f"    ERR  {f}: {snapshot[f]['__error__']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
