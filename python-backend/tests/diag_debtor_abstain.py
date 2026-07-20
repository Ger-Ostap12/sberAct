# -*- coding: utf-8 -*-
"""Диагностика воздержаний `classify_debtor_name` (заход 2): по файлам, где
семантика вернула None, печатает извлечённых кандидатов и причину отсева
(нет якоря «Должник» слева / перекрыт якорём иной роли), плюс regex-имя.

Цель — понять, косинус-роль спасёт воздержания (имя найдено, но отвергнуто по
якорю) или нужен другой фикс (имя вообще не в харвесте). Модель не грузится.

Запуск: cd python-backend && venv/Scripts/python.exe tests/diag_debtor_abstain.py
"""
import logging
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.disable(logging.CRITICAL)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.join(_THIS, "golden"))

from _snapshot import corpus_files, CORPUS_DIR  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402
import semantic_classifier as sc  # noqa: E402


def diagnose(raw_text: str) -> list:
    """Повторяет отбор classify_debtor_name, но по КАЖДОМУ кандидату отдаёт вердикт."""
    window = sc._extract_debtor_window(raw_text)
    rows = []
    for name, pos, kind in sc._harvest_debtor_candidates(window):
        d = sc._nearest_preceding(sc._DEBTOR_ANCHOR_RE, window, pos)
        o = sc._nearest_preceding(sc._OTHER_ROLE_ANCHOR_RE, window, pos)
        if d is None:
            verdict = "нет якоря «Должник» слева"
        elif o is not None and o > d:
            verdict = f"перекрыт якорём иной роли (o={o} > d={d})"
        else:
            verdict = f"ПРИНЯТ (dist={pos - d})"
        rows.append((name, kind, pos, d, o, verdict))
    return rows


def main() -> int:
    az = DocumentAnalyzer()
    for rel in corpus_files():
        try:
            result = az.analyze(os.path.join(CORPUS_DIR, rel))
        except Exception as exc:
            print(f"[ОШИБКА] {rel}: {exc}")
            continue
        raw_text = result.get("rawText", "")
        regex_name = (result.get("fields") or {}).get("debtorName", "") or ""
        sem_name, _ = sc.classify_debtor_name(raw_text)
        if sem_name:  # интересуют только воздержания
            continue
        print("=" * 78)
        print(rel)
        print(f"  regex debtorName: {regex_name!r}")
        rows = diagnose(raw_text)
        if not rows:
            print("  КАНДИДАТОВ НЕТ (харвест пуст — имя не достаётся ни ЮЛ/ИП regex, ни NER)")
        for name, kind, pos, d, o, verdict in rows:
            print(f"    [{kind:10}] pos={pos:5} {name!r}  -> {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
