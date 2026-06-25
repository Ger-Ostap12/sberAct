# -*- coding: utf-8 -*-
"""Генератор output-golden эталона для document_generator.

ЗАПУСКАТЬ ВРУЧНУЮ и осознанно — перезаписывает зафиксированный текст итоговых
документов. После структурного рефакторинга генератора эталон трогать НЕЛЬЗЯ
(вывод должен совпасть). Регенерация оправдана лишь при намеренном изменении
вывода (новый шаблон, исправление текста) и ручной проверке диффа.

Использование:
    venv/Scripts/python.exe tests/golden_gen/regenerate_gen_golden.py
"""
import json
import logging
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "..", "app")))

from _gen_snapshot import GOLDEN_PATH, build_snapshot, corpus_files  # noqa: E402

logging.disable(logging.CRITICAL)

from document_analyzer import DocumentAnalyzer  # noqa: E402
from document_generator import DocumentGenerator  # noqa: E402


def main() -> int:
    files = corpus_files()
    if not files:
        print("Корпус Заявления/ не найден — нечего фиксировать", file=sys.stderr)
        return 1
    print(f"Корпус: {len(files)} документов. Генерируем output-эталон...")
    analyzer = DocumentAnalyzer()
    generator = DocumentGenerator()
    snapshot = build_snapshot(analyzer, generator, files)

    errors = [f for f, s in snapshot.items() if "__error__" in s]
    with open(GOLDEN_PATH, "w", encoding="utf-8") as w:
        json.dump(snapshot, w, ensure_ascii=False, indent=1, sort_keys=True)

    print(f"Эталон сохранён: {GOLDEN_PATH}")
    print(f"  входных документов: {len(snapshot)}")
    print(f"  с ошибкой analyze/generate: {len(errors)}")
    for f in errors:
        print(f"    ERR  {f}: {snapshot[f]['__error__']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
