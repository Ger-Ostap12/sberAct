# -*- coding: utf-8 -*-
"""Отчёт покрытия полей по корпусу заявлений.

Задача — заменить вопрос «почему на ЭТОМ документе не извлёкся адрес?» вопросом
«на каком КЛАССЕ документов адрес не извлекается?». Первый порождает регулярку
под документ, второй — правку, которая чинит сразу девять.

Отчёт ничего не чинит и не трогает продовый код: гоняет тот же `analyze()`, что
и golden-тесты, на том же корпусе, и сводит результат по осям.

Разделы:
  1. Своднaя таблица по типам документов.
  2. Поля, не извлечённые НИ РАЗУ — мёртвое объявление или сломанный разбор.
  3. Классы пробелов — поле извлекается не везде; вот где именно пусто.
  4. Качество — распределение уровней доверия и топ претензий контракта.
  5. Паттерны, ни разу не совпавшие на корпусе, — кандидаты на удаление.

Использование:
    venv/Scripts/python.exe tools/field_coverage.py
    venv/Scripts/python.exe tools/field_coverage.py --out отчёт.txt --json отчёт.json
    venv/Scripts/python.exe tools/field_coverage.py --field applicantAddress
    venv/Scripts/python.exe tools/field_coverage.py --limit 5   # быстрый прогон
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_THIS, ".."))
sys.path.insert(0, os.path.join(_BACKEND, "app"))
sys.path.insert(0, os.path.join(_BACKEND, "tests", "golden"))

from _snapshot import CORPUS_DIR, corpus_files  # noqa: E402

# Сколько документов перечислять поимённо в классе пробелов, прежде чем свернуть
# в «…и ещё N». Класс важен целиком, но читать отчёт должно быть возможно.
_NAMES_SHOWN = 12


def _is_empty(value: Any) -> bool:
    """Пусто ли поле.

    Ноль и `False` — законные значения (сумма 0, флаг «без залога»), пустотой
    их считать нельзя: иначе отчёт объявит пробелом корректно извлечённое поле.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _normalized_text(analyzer, raw_text: str) -> str:
    """Текст в том виде, в каком его видят паттерны.

    Извлечение работает НЕ по `rawText`: перед сопоставлением анализатор
    маскирует суммы в перечне приложений и нормализует пробелы и переносы меток
    (`document_analyzer.analyze`). Отчёт о несовпавших паттернах, построенный по
    сырому тексту, врал бы в обе стороны — поэтому повторяем ту же цепочку.
    """
    text = analyzer._mask_attachment_list_amounts(raw_text)
    text = analyzer._normalize_whitespace_for_matching(text)
    return analyzer._normalize_label_wrap_for_matching(text)


def collect(limit: Optional[int] = None, progress=None) -> Dict[str, Any]:
    """Прогон корпуса. Возвращает сырые наблюдения, без интерпретации."""
    # Импорт внутри функции намеренный: DocumentAnalyzer тянет spaCy и модель
    # эмбеддингов (секунды и сотни мегабайт). Разбор `--help` не должен за это платить.
    import patterns as pattern_exec
    from document_analyzer import DocumentAnalyzer

    analyzer = DocumentAnalyzer()
    files = corpus_files()
    if limit:
        files = files[:limit]

    docs: List[Dict[str, Any]] = []
    # Паттерн -> на скольких документах он вообще способен совпасть. Ключ —
    # (имя поля, сама строка): один и тот же паттерн у разных полей это разные
    # позиции в исходнике, и мёртв он может быть только у одной из них.
    pattern_hits: Counter = Counter()
    # Учитываем ТОЛЬКО те объявления, которые корпус реально задействовал.
    # Иначе паттерны ипотечных полей попадут в «мёртвые» просто потому, что
    # ипотечных заявлений в корпусе нет, — и отчёт будет врать.
    applied: Dict[str, str] = {}
    declared_by_type: Dict[str, List[str]] = {}

    for i, rel in enumerate(files, 1):
        if progress:
            progress(i, len(files), rel)
        abs_path = os.path.join(CORPUS_DIR, rel)
        try:
            result = analyzer.analyze(abs_path)
        except Exception as exc:  # документ, который вообще не разбирается, — тоже факт
            docs.append({"file": rel, "error": f"{type(exc).__name__}: {exc}"})
            continue

        doc_type = result.get("documentType") or "?"
        fields = result.get("fields") or {}
        docs.append({
            "file": rel,
            "documentType": doc_type,
            "fields": {k: v for k, v in fields.items()},
            "fieldIssues": result.get("fieldIssues") or [],
            "fieldQuality": result.get("fieldQuality") or {},
        })

        # Какие паттерны в принципе способны совпасть на этом документе.
        text = _normalized_text(analyzer, result.get("rawText") or "")
        declared = analyzer.patterns.get(doc_type) or analyzer.patterns.get("rtk_application") or []
        declared_by_type.setdefault(doc_type, sorted({info["name"] for info in declared}))
        for info in declared:
            for pat in info["patterns"]:
                key = f"{info['name']}\x00{pat}"
                applied[key] = info["name"]
                if pattern_exec.search(pat, text):
                    pattern_hits[key] += 1

    return {
        "docs": docs,
        "patternHits": dict(pattern_hits),
        "allPatterns": applied,
        "declaredByType": declared_by_type,
    }


def summarize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Свод наблюдений по осям. Чистая функция — вход один, выход один."""
    docs = [d for d in raw["docs"] if "error" not in d]
    broken = [d for d in raw["docs"] if "error" in d]

    by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for d in docs:
        by_type[d["documentType"]].append(d)

    # Разрез по ТИПУ документа — это и есть «класс». Иначе ипотечные поля,
    # которых в банкротных заявлениях нет по определению, попадут в пробелы и
    # утопят настоящие.
    #
    # Поле «ожидается» для типа, если оно объявлено в паттернах этого типа ЛИБО
    # хоть раз в нём извлеклось (вычисляемые поля вроде entityType паттернами не
    # объявлены). Отсутствие ключа в словаре и пустое значение — одинаково «не
    # извлечено»; разница лишь в том, что пустой ключ означает «извлекатель
    # отработал и ничего не дал или контракт вычистил».
    per_type: Dict[str, Dict[str, Any]] = {}
    filled: Counter = Counter()
    empty_where: Dict[str, List[str]] = defaultdict(list)
    seen_fields: set = set()

    for doc_type, group in by_type.items():
        expected = set(raw["declaredByType"].get(doc_type, []))
        for d in group:
            for name, value in d["fields"].items():
                if not _is_empty(value):
                    expected.add(name)
        stats: Dict[str, Dict[str, Any]] = {}
        for name in sorted(expected):
            got, gaps, cleared = 0, [], []
            for d in group:
                if name not in d["fields"]:
                    gaps.append(d["file"])
                elif _is_empty(d["fields"][name]):
                    gaps.append(d["file"])
                    cleared.append(d["file"])
                else:
                    got += 1
            stats[name] = {"filled": got, "total": len(group), "gaps": gaps, "emptyKey": cleared}
        per_type[doc_type] = stats

    for d in docs:
        for name, value in d["fields"].items():
            seen_fields.add(name)
            if _is_empty(value):
                empty_where[name].append(d["file"])
            else:
                filled[name] += 1

    levels: Counter = Counter()
    level_by_field: Dict[str, Counter] = defaultdict(Counter)
    reasons: Counter = Counter()
    reason_files: Dict[str, List[str]] = defaultdict(list)
    for d in docs:
        for name, q in (d["fieldQuality"] or {}).items():
            lvl = q.get("level", "?")
            levels[lvl] += 1
            level_by_field[name][lvl] += 1
        for issue in d["fieldIssues"]:
            reason = issue.get("reason", "?")
            reasons[reason] += 1
            reason_files[reason].append(d["file"])

    hits = raw["patternHits"]
    dead = sorted(k for k in raw["allPatterns"] if hits.get(k, 0) == 0)
    dead_by_field: Dict[str, int] = Counter(raw["allPatterns"][k] for k in dead)
    patterns_by_field: Dict[str, int] = Counter(raw["allPatterns"].values())

    total = len(docs)

    return {
        "totalDocs": total,
        "brokenDocs": broken,
        "byType": {t: len(v) for t, v in sorted(by_type.items())},
        "fieldsSeen": len(seen_fields),
        "perType": per_type,
        "filled": dict(filled),
        "emptyWhere": {k: v for k, v in empty_where.items()},
        "levels": dict(levels),
        "levelByField": {k: dict(v) for k, v in level_by_field.items()},
        "reasons": reasons.most_common(),
        "reasonFiles": {k: v for k, v in reason_files.items()},
        "deadPatterns": dead,
        "deadByField": dict(dead_by_field),
        "patternsByField": dict(patterns_by_field),
        "patternsTotal": len(raw["allPatterns"]),
    }


def render(s: Dict[str, Any], out, field: Optional[str] = None) -> None:
    """Человекочитаемый отчёт."""
    w = lambda line="": print(line, file=out)  # noqa: E731

    if field:
        w(f"ПОЛЕ {field}")
        w("=" * 72)
        lvl = s["levelByField"].get(field)
        if lvl:
            w("уровни доверия: " + ", ".join(f"{k}={v}" for k, v in sorted(lvl.items())))
        dead = s["deadByField"].get(field, 0)
        if dead:
            w(f"паттернов без единого совпадения на корпусе: {dead}")
        for doc_type, stats in sorted(s["perType"].items()):
            st = stats.get(field)
            if not st:
                continue
            w()
            w(f"{doc_type}: извлечено {st['filled']}/{st['total']}")
            for f in st["gaps"]:
                mark = "пусто" if f in st["emptyKey"] else "нет ключа"
                w(f"   [{mark}] {f}")
        return

    w("ПОКРЫТИЕ ПОЛЕЙ ПО КОРПУСУ")
    w("=" * 72)
    w(f"документов разобрано: {s['totalDocs']}   полей встречено: {s['fieldsSeen']}")
    w("по типам документов: " + ", ".join(f"{t}={n}" for t, n in s["byType"].items()))
    if s["brokenDocs"]:
        w()
        w(f"НЕ РАЗОБРАЛИСЬ ВОВСЕ ({len(s['brokenDocs'])}):")
        for d in s["brokenDocs"]:
            w(f"   {d['file']}: {d['error']}")

    for doc_type, stats in sorted(s["perType"].items(), key=lambda x: -len(x[1])):
        group_size = next(iter(stats.values()))["total"] if stats else 0
        never = [n for n, st in stats.items() if st["filled"] == 0]
        always = [n for n, st in stats.items() if st["filled"] == st["total"]]
        partial = sorted(
            (n for n, st in stats.items() if 0 < st["filled"] < st["total"]),
            key=lambda n: (-len(stats[n]["gaps"]), n),
        )
        w()
        w("=" * 72)
        w(f"ТИП {doc_type} — {group_size} документов, {len(stats)} ожидаемых полей")
        w(f"   всегда: {len(always)}   не везде: {len(partial)}   ни разу: {len(never)}")

        if never:
            w()
            w("   НИ РАЗУ НЕ ИЗВЛЕКЛИСЬ — объявлены, но на этом типе молчат.")
            w("   Диагноз в скобках — самое полезное здесь:")
            w("     «нет совпадений»    — под формат корпуса паттерна просто нет;")
            w("     «совпало, отброшено» — паттерн срабатывает, но значение не")
            w("                            доходит до поля: его отбрасывает логика")
            w("                            извлечения или вычищает контракт.")
            for n in sorted(never):
                dead = s["deadByField"].get(n, 0)
                total_pat = s["patternsByField"].get(n, 0)
                if total_pat and dead == total_pat:
                    note = f"  (нет совпадений: все {total_pat})"
                elif total_pat:
                    note = f"  (совпало, отброшено: {total_pat - dead} из {total_pat} паттернов совпадали)"
                else:
                    note = "  (поле вычисляемое, паттернов нет)"
                w(f"      {n}{note}")

        if partial:
            w()
            w("   КЛАССЫ ПРОБЕЛОВ — чинить класс, а не документ:")
            for n in partial:
                st = stats[n]
                w(f"      {n}: {st['filled']}/{st['total']}, не извлечено в {len(st['gaps'])}")
                for f in st["gaps"][:_NAMES_SHOWN]:
                    mark = "пусто" if f in st["emptyKey"] else "нет ключа"
                    w(f"           [{mark}] {f}")
                if len(st["gaps"]) > _NAMES_SHOWN:
                    w(f"           …и ещё {len(st['gaps']) - _NAMES_SHOWN}")

    w()
    w("=" * 72)
    w("КАЧЕСТВО ИЗВЛЕЧЁННОГО (по всему корпусу)")
    lv = s["levels"]
    w(f"   уровни доверия: high={lv.get('high', 0)}, medium={lv.get('medium', 0)}, low={lv.get('low', 0)}")
    if s["reasons"]:
        w("   претензии контракта (сколько раз / поля):")
        for reason, cnt in s["reasons"]:
            files = s["reasonFiles"][reason]
            w(f"      x{cnt}  {reason}")
            for f in files[:5]:
                w(f"             {f}")
            if len(files) > 5:
                w(f"             …и ещё {len(files) - 5}")
    else:
        w("   претензий нет")

    w()
    w("=" * 72)
    w(f"ПАТТЕРНЫ БЕЗ ЕДИНОГО СОВПАДЕНИЯ — {len(s['deadPatterns'])} из {s['patternsTotal']}")
    w("   Проверено по НОРМАЛИЗОВАННОМУ тексту — тому же, что видят паттерны.")
    w("   Ни одного совпадения на корпусе значит «на этом корпусе не сработал»,")
    w("   а не «не нужен»: паттерн может держать формат банка, которого здесь нет.")
    w("   Список — повод посмотреть, а не удалять не глядя.")
    for name, cnt in sorted(s["deadByField"].items(), key=lambda x: (-x[1], x[0])):
        w(f"   {name}: {cnt}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Отчёт покрытия полей по корпусу заявлений")
    ap.add_argument("--out", help="файл текстового отчёта (по умолчанию — stdout)")
    ap.add_argument("--json", dest="json_path", help="файл со сводными данными в JSON")
    ap.add_argument("--field", help="детализация по одному полю")
    ap.add_argument("--limit", type=int, help="взять только первые N документов (быстрый прогон)")
    ap.add_argument("--quiet", action="store_true", help="без индикатора прогресса")
    args = ap.parse_args()

    logging.disable(logging.CRITICAL)  # анализатор очень болтлив на INFO

    if not os.path.isdir(CORPUS_DIR):
        print(f"корпус недоступен: {CORPUS_DIR}", file=sys.stderr)
        return 2

    started = time.time()

    def progress(i, n, rel):
        if not args.quiet:
            print(f"[{i}/{n}] {rel}", file=sys.stderr)

    raw = collect(limit=args.limit, progress=progress)
    summary = summarize(raw)

    if args.json_path:
        with io.open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)

    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as f:
            render(summary, f, field=args.field)
        print(f"отчёт записан: {args.out} ({time.time() - started:.1f} с)", file=sys.stderr)
    else:
        render(summary, sys.stdout, field=args.field)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
