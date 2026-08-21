# -*- coding: utf-8 -*-
"""Генератор golden-master эталона.

ЗАПУСКАТЬ ВРУЧНУЮ и ТОЛЬКО осознанно — он перезаписывает зафиксированный эталон
поведения. После структурного рефакторинга эталон трогать НЕЛЬЗЯ (вывод должен
совпасть). Регенерация оправдана лишь когда поведение изменено намеренно
(удаление хардкода, улучшение анализа) и новый вывод проверен вручную.

Использование:
    venv/Scripts/python.exe tests/golden/regenerate_golden.py
    venv/Scripts/python.exe tests/golden/regenerate_golden.py --only "Самобанкрот/"
    venv/Scripts/python.exe tests/golden/regenerate_golden.py --only "Самобанкрот/" --skip "физического лица"
    venv/Scripts/python.exe tests/golden/regenerate_golden.py --only-fields fields.requirementsSum

С --only перезаписываются ТОЛЬКО снимки файлов, чей путь содержит подстроку;
--skip выводит из-под регенерации отдельные файлы внутри группы (их расхождение
разобрано и признано БАГОМ — такой снимок обязан остаться красным, пока баг жив);
--only-fields принимает группу по ПРИЧИНЕ, а не по папке: перезаписываются лишь
снимки, где расхождение не выходит за перечисленные поля. Файл, у которого рядом
разошлось что-то ещё, остаётся красным — иначе неразобранное уезжает заодно;
остальные берутся из существующего эталона без изменений. Это позволяет
принимать новое поведение по одной группе документов за раз, а не всем корпусом
сразу — иначе вместе с проверенной группой молча уезжают ещё не разобранные.
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


def _diff_paths(exp, act, path: str = "") -> list:
    """Пути полей, где два снимка разошлись ('fields.totalDebt', 'collaterals')."""
    if type(exp) is not type(act):
        return [path]
    if isinstance(exp, dict):
        out = []
        for k in sorted(set(exp) | set(act)):
            sub = f"{path}.{k}" if path else k
            out += _diff_paths(exp.get(k, _MISSING), act.get(k, _MISSING), sub)
        return out
    if isinstance(exp, list):
        if len(exp) != len(act):
            return [path]
        out = []
        for e, a in zip(exp, act):
            out += _diff_paths(e, a, path)
        return out
    return [] if exp == act else [path]


_MISSING = object()


def _load_existing() -> dict:
    if not os.path.exists(GOLDEN_PATH):
        return {}
    with open(GOLDEN_PATH, encoding="utf-8") as r:
        return json.load(r)


def main() -> int:
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    skip = None
    if "--skip" in sys.argv:
        skip = sys.argv[sys.argv.index("--skip") + 1]
    only_fields = None
    if "--only-fields" in sys.argv:
        only_fields = set(sys.argv[sys.argv.index("--only-fields") + 1].split(","))

    files = corpus_files()
    if not files:
        print("Корпус Заявления/ не найден — нечего фиксировать", file=sys.stderr)
        return 1

    analyzer = DocumentAnalyzer()
    if only_fields:
        golden = _load_existing()
        if not golden:
            print("Эталона ещё нет — --only-fields неприменим", file=sys.stderr)
            return 1
        fresh = build_snapshot(analyzer, [f for f in files if f in golden])
        targets = {}
        held = []
        for rel, snap in fresh.items():
            paths = set(_diff_paths(golden[rel], snap))
            if not paths:
                continue
            if paths <= only_fields:
                targets[rel] = snap
            else:
                held.append((rel, sorted(paths - only_fields)))
        print(f"Фильтр --only-fields {sorted(only_fields)}: принято {len(targets)}, "
              f"оставлено красными {len(held)}")
        for rel, extra in held:
            print(f"    ДЕРЖИМ  {rel}  (ещё: {', '.join(extra)})")
        if not targets:
            print("Под фильтр не попал ни один файл", file=sys.stderr)
            return 1
        snapshot = golden
        snapshot.update(targets)
    elif only:
        targets = [f for f in files if only in f and not (skip and skip in f)]
        if not targets:
            print(f"Под фильтр --only {only!r} не попал ни один файл", file=sys.stderr)
            return 1
        print(f"Фильтр --only {only!r}"
              + (f", --skip {skip!r}" if skip else "")
              + f": {len(targets)} из {len(files)} документов.")
        snapshot = _load_existing()
        if not snapshot:
            print("Эталона ещё нет — --only неприменим", file=sys.stderr)
            return 1
        snapshot.update(build_snapshot(analyzer, targets))
    else:
        print(f"Корпус: {len(files)} документов. Генерируем эталон...")
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
