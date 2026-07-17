# -*- coding: utf-8 -*-
"""Измеритель устойчивости разбора к ФОРМЕ документа (мутационный стресс).

Берёт каждый документ корпуса, портит ему оформление, не трогая смысл (ё/е,
кавычки, неразрывные пробелы, регистр меток, перенос после метки, двойные
пробелы), и сравнивает извлечённые данные с разбором исходника. Расхождение
означает, что результат зависит от типографики: то же заявление, набранное в
другом банке, разберётся иначе. Это прямая оценка риска на НОВЫХ заявлениях,
которых в корпусе нет.

Печатает таблицу «мутация -> сколько документов сломалось» и разбивку по полям.
Базовая линия на 2026-07-17 (до фаз нормализации), «сломалось / применима»:
двойные пробелы 42/79, кавычки 21/75, перенос строки 8/74, ё/е 5/34,
неразрывный пробел 5/71, метки капсом 3/69.

Запуск: cd python-backend && venv/Scripts/python.exe tests/measure_format_robustness.py
Полный прогон корпуса — минуты. Быстрая проверка на подвыборке — pytest
tests/test_format_robustness.py.
"""
import collections
import logging
import os
import sys

logging.disable(logging.CRITICAL)
# Консоль Windows — cp1251: без этого любой символ вне неё роняет отчёт целиком
# (UnicodeEncodeError уже после многих минут прогона). errors="replace" — чтобы
# отчёт дошёл до конца при любой кодировке терминала.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.join(_THIS, "golden"))
sys.path.insert(0, _THIS)

from _mutations import MUTATION_TITLES, MUTATIONS, diff_fields, significant_result  # noqa: E402
from _snapshot import CORPUS_DIR, corpus_files  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402


def main() -> int:
    analyzer = DocumentAnalyzer()
    files = corpus_files()
    # applicable — на скольких документах мутация вообще что-то изменила в тексте
    # (например, ё/е неприменима к документу без буквы «ё» — её нельзя считать
    # успехом, иначе процент устойчивости будет завышен).
    applicable = collections.Counter()
    broken = collections.Counter()
    fields_hit = collections.defaultdict(collections.Counter)
    broken_files = collections.defaultdict(list)

    for i, rel in enumerate(files, 1):
        path = os.path.join(CORPUS_DIR, rel)
        try:
            text = analyzer.extract_text(path)
            base = significant_result(analyzer.analyze_from_text(text, 2))
        except Exception as exc:  # битый исходник — не предмет этого измерения
            print(f"[{i}/{len(files)}] SKIP {rel}: {exc}")
            continue

        for name, mutate in MUTATIONS:
            mutated_text = mutate(text)
            if mutated_text == text:
                continue
            applicable[name] += 1
            try:
                mutated = significant_result(analyzer.analyze_from_text(mutated_text, 2))
            except Exception:
                broken[name] += 1
                fields_hit[name]["#ПАДЕНИЕ"] += 1
                broken_files[name].append(rel)
                continue
            changed = diff_fields(base, mutated)
            if changed:
                broken[name] += 1
                broken_files[name].append(rel)
                for field in changed:
                    fields_hit[name][field] += 1
        print(f"[{i}/{len(files)}] {rel}")

    print("\n" + "=" * 78)
    print(f"УСТОЙЧИВОСТЬ К ФОРМАТУ: {len(files)} документов корпуса")
    print("=" * 78)
    print(f"{'мутация':32s} {'применима':>10s} {'сломалось':>10s} {'% док':>7s}")
    print("-" * 78)
    for name, _ in MUTATIONS:
        total = applicable[name]
        bad = broken[name]
        share = 100 * bad / total if total else 0
        print(f"{MUTATION_TITLES[name]:32s} {total:10d} {bad:10d} {share:6.0f}%")

    print("\nКакие поля поехали:")
    for name, _ in MUTATIONS:
        if not fields_hit[name]:
            continue
        print(f"\n  {MUTATION_TITLES[name]}")
        for field, count in fields_hit[name].most_common(12):
            print(f"      {field:34s} {count:3d} док.")

    print("\nСписки сломанных файлов — для точечного разбора:")
    for name, _ in MUTATIONS:
        if not broken_files[name]:
            continue
        print(f"\n  {MUTATION_TITLES[name]} ({len(broken_files[name])}):")
        for rel in broken_files[name]:
            print(f"      {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
