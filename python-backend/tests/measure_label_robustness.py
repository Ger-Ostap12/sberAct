# -*- coding: utf-8 -*-
"""Измеритель устойчивости разбора к НАПИСАНИЮ МЕТКИ (ось §S.2.D).

Родственник `measure_format_robustness.py`, но портит не типографику, а саму
метку: меняет её на синоним из `label_synonyms`, на бытовое сокращение, дописывает
уточнение в скобках, ставит тире вместо двоеточия. Смысл документа при этом не
меняется — так же выглядит то же заявление у другого банка.

Зачем. §S.2.D («нечёткое сопоставление меток») обещает закончить беговую дорожку
«добавь ещё синоним». Но цена этой работы — неделя, а разбор двигается, значит
golden под угрозой. Прежде чем платить, надо знать, СКОЛЬКО она даёт. Отчёт
корпуса (§S.2.E) на этот вопрос не отвечает: он видит только те написания меток,
которые в корпусе уже есть.

Число «сломалось N из M» здесь и есть цена вопроса. Оно же — определение
готовности: §S.2.D сделана, когда эти мутации перестают ломать извлечение.

Запуск: cd python-backend && venv/Scripts/python.exe tests/measure_label_robustness.py
Полный прогон корпуса — минуты. Ограничить: --limit N.
"""
import argparse
import collections
import logging
import os
import sys

logging.disable(logging.CRITICAL)
# Консоль Windows — cp1251: без reconfigure отчёт падает на первом же символе
# вне неё, уже после минут прогона (та же грабля, что в measure_format_robustness).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.join(_THIS, "golden"))
sys.path.insert(0, _THIS)

from _mutations import (  # noqa: E402
    LABEL_MUTATION_TITLES,
    LABEL_MUTATIONS,
    diff_fields,
    significant_result,
)
from _snapshot import CORPUS_DIR, corpus_files  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="взять только первые N документов")
    ap.add_argument("--quiet", action="store_true", help="без построчного прогресса")
    args = ap.parse_args()

    analyzer = DocumentAnalyzer()
    files = corpus_files()[: args.limit] if args.limit else corpus_files()

    # applicable — на скольких документах мутация вообще изменила текст. Документ,
    # где метки нет, не может считаться успехом: иначе устойчивость завышена.
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

        for name, mutate in LABEL_MUTATIONS:
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
        if not args.quiet:
            print(f"[{i}/{len(files)}] {rel}")

    print("\n" + "=" * 78)
    print(f"УСТОЙЧИВОСТЬ К НАПИСАНИЮ МЕТКИ: {len(files)} документов корпуса")
    print("=" * 78)
    print(f"{'мутация':40s} {'применима':>10s} {'сломалось':>10s} {'% док':>7s}")
    print("-" * 78)
    for name, _ in LABEL_MUTATIONS:
        total = applicable[name]
        bad = broken[name]
        share = 100 * bad / total if total else 0
        print(f"{LABEL_MUTATION_TITLES[name]:40s} {total:10d} {bad:10d} {share:6.0f}%")

    print("\nКакие поля поехали (топ по числу документов):")
    for name, _ in LABEL_MUTATIONS:
        if not fields_hit[name]:
            continue
        print(f"\n  {LABEL_MUTATION_TITLES[name]}")
        for field, count in fields_hit[name].most_common(15):
            print(f"      {field:34s} {count:3d} док.")

    print("\nСписки сломанных файлов — для точечного разбора:")
    for name, _ in LABEL_MUTATIONS:
        if not broken_files[name]:
            continue
        print(f"\n  {LABEL_MUTATION_TITLES[name]} ({len(broken_files[name])}):")
        for rel in broken_files[name][:15]:
            print(f"      {rel}")
        if len(broken_files[name]) > 15:
            print(f"      …и ещё {len(broken_files[name]) - 15}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
