# -*- coding: utf-8 -*-
"""Теневой отчёт структурного слоя: что он даёт сверх разбора по тексту (§S.2.B, B4).

Слой НЕ подключён к продовому пути и ничего не подменяет. Задача отчёта — дать
основание для промоушена каждого отдельного поля: где разметка отвечает так же,
как текстовый разбор, где расходится, а где отвечает вместо молчания.

Порядок работы задан планом фазы 2: сначала тенью со сверкой на корпусе, потом
промоушен по полю. Продвигать поле, не увидев его строку в этом отчёте, нельзя —
ровно так в §S.2.A и §S.6.6 отменялись правки, обоснованные рассуждением вместо
замера.

Запуск:
    venv/Scripts/python.exe tools/structural_shadow.py --out отчёт.txt
    venv/Scripts/python.exe tools/structural_shadow.py --field inn
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_THIS, ".."))
sys.path.insert(0, os.path.join(_BACKEND, "app"))
sys.path.insert(0, os.path.join(_BACKEND, "tests", "golden"))

from _snapshot import CORPUS_DIR, corpus_files  # noqa: E402
from doc_structure import structural_value  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402
from label_synonyms import FIELD_LABELS  # noqa: E402

logger = logging.getLogger(__name__)

# Вердикты — сознательно грубые: тонкие градации тут только маскируют разбор глазами.
SAME = "совпало"
DIFFER = "разошлось"
ONLY_STRUCT = "только структурный"
ONLY_TEXT = "только текст"


def _norm(value: Any) -> str:
    """Сравниваем по существу: пробелы и регистр разметки к делу не относятся."""
    return " ".join(str(value or "").split()).strip().lower()


def _prod_values(result: Dict[str, Any], field: str) -> Dict[str, str]:
    """Прод-значения, относящиеся к полю: `inn` -> inn, creditorInn, debtors[].inn.

    Структурный запрос находит значение, но НЕ ЗНАЕТ роли: «ИНН» в таблице может
    принадлежать кому угодно. Поэтому сверяем со всеми ролевыми вариантами поля
    сразу — совпадение хотя бы с одним и означает «разметка сказала то же самое».
    Назначение роли — задача §S.2.C, а не этого слоя.
    """
    out: Dict[str, str] = {}
    needle = field.lower()

    def collect(prefix: str, mapping: Dict[str, Any]) -> None:
        for key, value in (mapping or {}).items():
            if not isinstance(value, (str, int, float)):
                continue
            if needle in str(key).lower():
                text = str(value).strip()
                if text:
                    out[prefix + key] = text

    collect("", result.get("fields") or {})
    for i, debtor in enumerate(result.get("debtors") or []):
        if isinstance(debtor, dict):
            collect(f"debtors[{i}].", debtor)
    return out


def _verdict(struct: Optional[str], prod: Dict[str, str]) -> Tuple[str, str]:
    """Вердикт по одному полю одного документа + пояснение к нему."""
    if struct is None and not prod:
        return "", ""
    if struct is None:
        return ONLY_TEXT, ", ".join(sorted(prod))
    if not prod:
        return ONLY_STRUCT, ""
    for name, value in prod.items():
        if _norm(value) == _norm(struct):
            return SAME, name
        # Разметка часто отдаёт значение с хвостом («7707083893, КПП 770701001»).
        if _norm(struct).startswith(_norm(value)) and len(_norm(value)) >= 6:
            return SAME, name + " (с хвостом)"
    return DIFFER, ", ".join(f"{k}={v}" for k, v in sorted(prod.items()))


def analyze_corpus(fields: List[str], limit: Optional[int] = None,
                   quiet: bool = False) -> Dict[str, Any]:
    """Прогон по корпусу: структурное значение против продового, по каждому полю."""
    analyzer = DocumentAnalyzer()
    files = [f for f in corpus_files() if f.lower().endswith(".docx")]
    if limit:
        files = files[:limit]

    rows: List[Dict[str, Any]] = []
    tally: Dict[str, Counter] = defaultdict(Counter)
    queries: Dict[str, Counter] = defaultdict(Counter)
    failed: List[str] = []

    for i, rel in enumerate(files, 1):
        if not quiet:
            print(f"[{i}/{len(files)}] {rel}", file=sys.stderr)
        abs_path = os.path.join(CORPUS_DIR, rel)
        try:
            parts = analyzer._docx_structure(abs_path)
            result = analyzer.analyze(abs_path)
        except Exception as exc:
            failed.append(f"{rel}: {type(exc).__name__}: {exc}")
            continue

        for field in fields:
            found = structural_value(parts, field)
            struct_value = found[0] if found else None
            query = found[1] if found else ""
            prod = _prod_values(result, field)
            verdict, note = _verdict(struct_value, prod)
            if not verdict:
                continue
            tally[field][verdict] += 1
            if query:
                queries[field][query] += 1
            rows.append({
                "file": rel, "field": field, "verdict": verdict,
                "structural": struct_value, "query": query, "note": note,
            })

    return {"files": len(files), "rows": rows, "tally": tally,
            "queries": queries, "failed": failed}


def render(report: Dict[str, Any], fields: List[str]) -> str:
    out: List[str] = []
    w = out.append
    w("=" * 78)
    w("ТЕНЕВОЙ ОТЧЁТ СТРУКТУРНОГО СЛОЯ")
    w("=" * 78)
    w(f"DOCX корпуса: {report['files']}")
    w("")
    w("Слой ничего не подменяет. Это основание для промоушена ПО ПОЛЮ:")
    w(f"  {SAME:<20} разметка сказала то же — поле можно продвигать")
    w(f"  {DIFFER:<20} разошлись — разбирать глазами, промоушен запрещён")
    w(f"  {ONLY_STRUCT:<20} разметка нашла там, где текст молчал — КАНДИДАТ")
    w(f"  {ONLY_TEXT:<20} разметки нет (не табличный документ) — норма")
    w("")
    w("⚠️  «только структурный» — это КАНДИДАТ, а не находка. Слой не знает РОЛИ:")
    w("    «КПП» в таблице платёжных реквизитов принадлежит банку-получателю, а не")
    w("    стороне спора. Роль назначается в §S.2.C, до тех пор — разбор глазами.")
    w("")

    w("-" * 78)
    w("СВОДКА ПО ПОЛЯМ")
    w("-" * 78)
    w(f"{'поле':<18}{SAME:>10}{DIFFER:>12}{ONLY_STRUCT:>20}{ONLY_TEXT:>14}   примечание")
    for field in fields:
        t = report["tally"].get(field, Counter())
        if not sum(t.values()):
            continue
        # Поле, у которого на всём корпусе НИ РАЗУ не было продового значения,
        # некуда продвигать: либо его нет в результате анализа, либо оно не
        # заполняется никогда. Тот же признак, что «поле никем не читается» в
        # отчёте покрытия — повод посмотреть, а не приговор.
        no_prod = "  ← прод-значения нет ни разу" if not (
            t[SAME] + t[DIFFER] + t[ONLY_TEXT]) else ""
        w(f"{field:<18}{t[SAME]:>10}{t[DIFFER]:>12}{t[ONLY_STRUCT]:>20}"
          f"{t[ONLY_TEXT]:>14}{no_prod}")
    w("")

    w("-" * 78)
    w("КАКИМ ЗАПРОСОМ ВЗЯТО")
    w("-" * 78)
    w("Запрос — это и уровень доверия: своя ячейка справа однозначнее,")
    w("чем «следующий абзац» (тот же приём, что слои с confidence в разборе).")
    for field in fields:
        q = report["queries"].get(field, Counter())
        if q:
            w(f"  {field:<18}" + "  ".join(f"{k}={v}" for k, v in q.most_common()))
    w("")

    for verdict, title in (
        (ONLY_STRUCT, "КАНДИДАТЫ: РАЗМЕТКА НАШЛА, ТЕКСТ МОЛЧАЛ"),
        (DIFFER, "РАСХОЖДЕНИЯ — РАЗБИРАТЬ ГЛАЗАМИ"),
    ):
        rows = [r for r in report["rows"] if r["verdict"] == verdict]
        w("-" * 78)
        w(f"{title}  ({len(rows)})")
        w("-" * 78)
        for r in rows:
            w(f"\n  {r['file']}")
            w(f"    поле={r['field']}  запрос={r['query']}")
            w(f"    разметка: {r['structural']}")
            if r["note"]:
                w(f"    текст:    {r['note']}")
        w("")

    if report["failed"]:
        w("-" * 78)
        w(f"НЕ ОБРАБОТАНЫ ({len(report['failed'])})")
        w("-" * 78)
        for line in report["failed"]:
            w(f"  {line}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--field", action="append", help="только это поле (можно повторять)")
    ap.add_argument("--limit", type=int, help="только первые N документов")
    ap.add_argument("--out", help="записать отчёт в файл")
    ap.add_argument("--quiet", action="store_true", help="без построчного прогресса")
    args = ap.parse_args()

    logging.disable(logging.CRITICAL)
    fields = args.field or sorted(FIELD_LABELS)
    unknown = [f for f in fields if f not in FIELD_LABELS]
    if unknown:
        print(f"Нет в реестре меток: {', '.join(unknown)}", file=sys.stderr)
        return 2

    report = analyze_corpus(fields, limit=args.limit, quiet=args.quiet)
    text = render(report, fields)
    if args.out:
        io.open(args.out, "w", encoding="utf-8").write(text)
        print(f"Отчёт записан: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
