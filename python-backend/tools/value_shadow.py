# -*- coding: utf-8 -*-
"""Теневой отчёт value-first слоя: сканеры + роли против текстового разбора (§S.2.C, C3).

Слой НЕ подключён к проду. Отчёт отвечает на один вопрос по каждому полю: если
искать значение по ФОРМЕ, а роль назначать по ближайшему якорю, — совпадёт ли
результат с тем, что даёт сегодняшний разбор по меткам?

Три исхода важны по-разному:

  совпало     основание для промоушена поля;
  разошлось   ЗАПРЕТ на промоушен до разбора глазами. Именно здесь живёт
              «ИНН кредитора уехал должнику» — молчаливая порча акта;
  воздержание слой не нашёл якоря. Это ЗАКОННЫЙ исход, а не провал: пустое
              поле видно, чужое значение — нет.

Запуск:
    venv/Scripts/python.exe tools/value_shadow.py --quiet --out отчёт.txt
    venv/Scripts/python.exe tools/value_shadow.py --kind inn
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

_THIS = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_THIS, ".."))
sys.path.insert(0, os.path.join(_BACKEND, "app"))
sys.path.insert(0, os.path.join(_BACKEND, "tests", "golden"))

from _snapshot import CORPUS_DIR, corpus_files  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402
from role_assignment import ROLE_ANCHORS, assign_all, best_by_role, role_field_name  # noqa: E402
from value_scanners import scan_all, valid_only  # noqa: E402

logger = logging.getLogger(__name__)

SAME = "совпало"
DIFFER = "разошлось"
ONLY_SHADOW = "только тень"
ONLY_PROD = "только прод"

# Типы с контрольной суммой или жёсткой формой — на них слой и рассчитан.
# Деньги/даты/ФИО намеренно не сверяются: их «правильность» зависит от роли
# в формуле расчёта, а не от формы, и сверка по имени поля тут врала бы.
DEFAULT_KINDS = ("inn", "ogrn", "ogrnip", "snils", "kpp")


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isalnum()).lower()


def _prod_matches(prod: str, shadow: str) -> bool:
    """Совпало ли теневое значение с продовым.

    Продовое поле бывает СПИСКОМ: у ипотечных заявлений с двумя ответчиками
    `inn` содержит «644986285759, 644122681613». Сравнение целиком объявляло бы
    такие случаи расхождением, хотя слой нашёл один из двух верных ИНН — так и
    вышло на первом прогоне (3 ложных расхождения из 21).
    """
    target = _norm(shadow)
    if _norm(prod) == target:
        return True
    return any(_norm(part) == target for part in re.split(r"[,;]", prod))


def compare_one(analyzer: DocumentAnalyzer, rel: str,
                kinds: List[str]) -> List[Dict[str, Any]]:
    abs_path = os.path.join(CORPUS_DIR, rel)
    result = analyzer.analyze(abs_path)
    text = result.get("rawText") or ""
    fields = result.get("fields") or {}

    found = valid_only(scan_all(text, kinds=kinds))
    best = best_by_role(assign_all(text, found))

    rows: List[Dict[str, Any]] = []
    seen_fields = set()

    for (role, kind), assigned in sorted(best.items()):
        field = role_field_name(role, kind)
        seen_fields.add(field)
        prod = str(fields.get(field) or "").strip()
        shadow = assigned.found.value
        if not prod:
            verdict = ONLY_SHADOW
        elif _prod_matches(prod, shadow):
            verdict = SAME
        else:
            verdict = DIFFER
        rows.append({
            "file": rel, "field": field, "role": role, "kind": kind,
            "verdict": verdict, "shadow": shadow, "prod": prod,
            "anchor": assigned.anchor, "distance": assigned.distance,
        })

    # Обратная сторона: прод заполнил поле, а слой воздержался. Без этой половины
    # отчёт показывал бы только успехи.
    for role in ROLE_ANCHORS:
        for kind in kinds:
            field = role_field_name(role, kind)
            if field in seen_fields:
                continue
            prod = str(fields.get(field) or "").strip()
            if prod:
                rows.append({
                    "file": rel, "field": field, "role": role, "kind": kind,
                    "verdict": ONLY_PROD, "shadow": "", "prod": prod,
                    "anchor": "", "distance": 0,
                })
    return rows


def analyze_corpus(kinds: List[str], limit: Optional[int] = None,
                   quiet: bool = False) -> Dict[str, Any]:
    analyzer = DocumentAnalyzer()
    files = corpus_files()
    if limit:
        files = files[:limit]

    rows: List[Dict[str, Any]] = []
    tally: Dict[str, Counter] = defaultdict(Counter)
    failed: List[str] = []

    for i, rel in enumerate(files, 1):
        if not quiet:
            print(f"[{i}/{len(files)}] {rel}", file=sys.stderr)
        try:
            got = compare_one(analyzer, rel, kinds)
        except Exception as exc:
            failed.append(f"{rel}: {type(exc).__name__}: {exc}")
            continue
        rows.extend(got)
        for r in got:
            tally[r["field"]][r["verdict"]] += 1

    return {"files": len(files), "rows": rows, "tally": tally, "failed": failed}


def render(report: Dict[str, Any]) -> str:
    out: List[str] = []
    w = out.append
    w("=" * 78)
    w("ТЕНЕВОЙ ОТЧЁТ VALUE-FIRST СЛОЯ (сканеры + роли)")
    w("=" * 78)
    w(f"документов: {report['files']}")
    w("")
    w(f"  {SAME:<14} основание для промоушена поля")
    w(f"  {DIFFER:<14} ЗАПРЕТ на промоушен: здесь «ИНН кредитора уехал должнику»")
    w(f"  {ONLY_SHADOW:<14} слой нашёл, разбор молчал — кандидат, разбирать глазами")
    w(f"  {ONLY_PROD:<14} слой воздержался — ЗАКОННЫЙ исход, не провал")
    w("")

    w("-" * 78)
    w("СВОДКА ПО ПОЛЯМ")
    w("-" * 78)
    w(f"{'поле':<22}{SAME:>10}{DIFFER:>12}{ONLY_SHADOW:>14}{ONLY_PROD:>14}")
    for field in sorted(report["tally"]):
        t = report["tally"][field]
        w(f"{field:<22}{t[SAME]:>10}{t[DIFFER]:>12}{t[ONLY_SHADOW]:>14}{t[ONLY_PROD]:>14}")
    w("")

    total = Counter()
    for t in report["tally"].values():
        total.update(t)
    w(f"ИТОГО: совпало {total[SAME]}, разошлось {total[DIFFER]}, "
      f"только тень {total[ONLY_SHADOW]}, только прод {total[ONLY_PROD]}")
    w("")

    for verdict, title in (
        (DIFFER, "РАСХОЖДЕНИЯ — ПРОМОУШЕН ЗАПРЕЩЁН ДО РАЗБОРА"),
        (ONLY_SHADOW, "КАНДИДАТЫ: СЛОЙ НАШЁЛ, РАЗБОР МОЛЧАЛ"),
    ):
        rows = [r for r in report["rows"] if r["verdict"] == verdict]
        w("-" * 78)
        w(f"{title}  ({len(rows)})")
        w("-" * 78)
        for r in rows:
            w(f"\n  {r['file']}")
            w(f"    поле={r['field']}  якорь={r['anchor']!r}  дистанция={r['distance']}")
            w(f"    тень: {r['shadow']}")
            if r["prod"]:
                w(f"    прод: {r['prod']}")
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
    ap.add_argument("--kind", action="append", help="только этот тип (можно повторять)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    logging.disable(logging.CRITICAL)
    kinds = args.kind or list(DEFAULT_KINDS)
    report = analyze_corpus(kinds, limit=args.limit, quiet=args.quiet)
    text = render(report)
    if args.out:
        io.open(args.out, "w", encoding="utf-8").write(text)
        print(f"Отчёт записан: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
