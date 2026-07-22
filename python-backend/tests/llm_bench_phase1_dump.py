# -*- coding: utf-8 -*-
"""Бенчмарк LLM-извлечения полей (Андрей, замер скорости/качества): фаза 1.

Гоняет DocumentAnalyzer по подвыборке golden-корпуса, сохраняет для каждого
файла (а) окно шапки документа (где живут ФИО/адреса/ИНН всех ролей) и
(б) regex-поля по трём ролям (должник/кредитор/управляющий) в JSON. Фаза 2
(в converter/.venv, где есть llama-cpp-python) читает этот JSON и прогоняет
Qwen2.5-1.5B — venv'ы раздельные, поэтому в два шага.

Запуск: cd python-backend && venv/Scripts/python.exe tests/llm_bench_phase1_dump.py
"""
import argparse
import json
import logging
import os
import re
import sys

logging.disable(logging.CRITICAL)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.join(_THIS, "golden"))

from _snapshot import corpus_files, CORPUS_DIR  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402
from semantic_classifier import _extract_prayer_window  # noqa: E402

# Подвыборка для быстрых итераций промпта; весь корпус (58) — только для
# подтверждения финалиста в конце цикла (--full).
SAMPLE_SIZE = 12

ROLE_FIELDS = {
    "debtor": ("debtorName", "applicantAddress", "inn", "ogrn", "birthDate", "birthPlace"),
    "manager": ("managerName", "managerAddress", "sroName"),
}

# Шапка документа — там живут стороны/реквизиты должника. Управляющий/СРО
# обычно называются в просительной части («прошу утвердить управляющего из
# числа членов СРО ...») — это ЗНАЧИТЕЛЬНО дальше шапки (проверено: символ
# ~22000 из ~43000 в реальном документе), поэтому одной шапки недостаточно.
# Добавляем окно просьбы (переиспользуем _extract_prayer_window из
# semantic_classifier, тот же якорь "прошу/ходатайствую", что и в
# процедуре-оси) — вместе с шапкой это должно закрыть управляющего/СРО.
# Было 3500 — медиана длины документа в корпусе 9684 символа (проверено
# 2026-07-22), окно резало адрес должника у 4/58 файлов (ФНС-шаблоны кладут
# адрес после длинного блока реквизитов/приложений, за пределами 3500, в
# одном случае — за пределами даже 5000, символ ~8330). Замерили реальный
# токенайзер (не оценка на глаз): промпт с окном 5000 = 3646 токенов из
# n_ctx=8192 минус max_tokens=1200 на ответ = ~7000 доступно — запас большой.
# Подняли до 9000, покрывает выброс.
HEADER_WINDOW_CHARS = 9000
PRAYER_WINDOW_CHARS = 2000

# Какие поля manager реально нужны — зависит от вида заявления/кредитора
# (Андрей, 2026-07-22, см. handoff §R.10): та же логика, что уже управляет
# видимостью полей на фронте (`DocumentAnalysis.tsx`: showSroField/
# showFioField). `creditorName` на этом шаге уже прошёл ФНС-нормализацию
# через _apply_fns_authority/_build_fns_creditor (registry-сравнение по
# всем ИФНС/УФНС России) — простой regex по итоговому имени достаточен,
# повторно палить справочник не нужно.
_FNS_CREDITOR_RE = re.compile(r"фнс|налогов", re.IGNORECASE)


def _needs_fio_sro(result: dict) -> tuple[bool, bool]:
    """(need_fio, need_sro) по правилам Андрея. is_rtk определяется широко —
    ЛЮБОЙ documentType кроме rtk_application считается «Инициирование»
    (наблюдение/реструктуризация/конкурсное производство и т.п. — те же
    «процедурные акты», что и обычное инициирование для этой логики) —
    сам классификатор даёт много нишевых веток (ip_enforcement_restructuring,
    competition_collateral...), полагаться на конкретную строку хрупко."""
    fields = result.get("fields") or {}
    is_self = result.get("applicationKind") == "self_bankruptcy"
    if is_self:
        return False, True
    is_rtk = result.get("documentType") == "rtk_application"
    is_fns = bool(_FNS_CREDITOR_RE.search(fields.get("creditorName", "") or ""))
    need_sro = not is_rtk
    need_fio = is_rtk or is_fns
    return need_fio, need_sro


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Весь корпус (58), не подвыборка")
    ap.add_argument("--out", default=None, help="Путь для дампа (по умолчанию по SAMPLE_SIZE)")
    args = ap.parse_args()

    az = DocumentAnalyzer()
    all_files = corpus_files()
    files = all_files if args.full else all_files[:SAMPLE_SIZE]
    out = []
    for rel in files:
        try:
            result = az.analyze(os.path.join(CORPUS_DIR, rel))
        except Exception as exc:
            print(f"[ОШИБКА] {rel}: {exc}")
            continue
        raw_text = result.get("rawText", "") or ""
        fields = result.get("fields") or {}
        regex_roles = {
            role: {f: fields.get(f, "") or "" for f in fs}
            for role, fs in ROLE_FIELDS.items()
        }
        prayer_window = _extract_prayer_window(raw_text)[:PRAYER_WINDOW_CHARS]
        need_fio, need_sro = _needs_fio_sro(result)
        out.append({
            "file": rel,
            "header_window": raw_text[:HEADER_WINDOW_CHARS],
            "prayer_window": prayer_window,
            "entity_type": fields.get("entityType", "") or "",
            "regex_roles": regex_roles,
            "document_type": result.get("documentType", "") or "",
            "is_self_bankruptcy": result.get("applicationKind") == "self_bankruptcy",
            "need_manager_fio": need_fio,
            "need_manager_sro": need_sro,
        })
        print(f"[ok] {rel} (entityType={fields.get('entityType', '?')} "
              f"fio={need_fio} sro={need_sro})")

    default_name = "llm_bench_dump_debtorfields_full58.json" if args.full else "llm_bench_dump_debtorfields.json"
    dump_path = args.out or os.path.join(_THIS, default_name)
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nСохранено {len(out)} файлов -> {dump_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
