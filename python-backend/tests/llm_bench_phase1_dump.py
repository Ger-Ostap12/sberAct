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

# Ипотека (mortgage_claim) — своя роль-схема, не банкротная (нет управляющего/
# СРО, зато есть суд/стороны-МАССИВЫ/представители/финблок). Поля — плоские
# regex-ключи document_analyzer.py (см. handoff/план "LLM для ипотеки").
_MORTGAGE_FINANCIAL_FIELDS = (
    "mortgageCreditAmount111", "mortgageCreditTerm112", "mortgageInterestRate113",
    "mortgagePenaltyRate114",
)


def _mortgage_regex(result: dict) -> dict:
    """Regex-эталон для ипотечной роль-схемы: суд/должники-массив/третьи
    лица-массив/представители/финблок. `debtors`/`thirdParties` — уже готовые
    МАССИВЫ из result (extract_debtors/extract_third_parties, см. parties_mixin
    _resolve_debtors_and_third_parties) — не через _combine_debtors (та
    склеивает несколько должников в одну строку через запятую, для честного
    сравнения по элементам нужен именно массив)."""
    fields = result.get("fields") or {}
    return {
        "court": {
            "name": fields.get("mortgageCourtName002", "") or "",
            "address": fields.get("mortgageCourtAddress001", "") or "",
        },
        "debtors": result.get("debtors") or [],
        # Эталон для блока «Обязательства»: без него новые поля
        # (тип/номер/дата договора) нечем было бы сверять.
        "obligations": result.get("obligations") or [],
        "thirdParties": result.get("thirdParties") or [],
        "representatives": {
            "plaintiff": fields.get("mortgageRepresentative22", "") or "",
            "defendant": fields.get("respondentRepresentativeName", "") or "",
        },
        "financial": {f: fields.get(f, "") or "" for f in _MORTGAGE_FINANCIAL_FIELDS},
        "properties": result.get("mortgageProperties") or [],
    }


# Предмет(ы) ипотеки (mortgageProperties, план "LLM для ипотеки" §5) — данные
# ЖИВУТ В ДВУХ РАЗНЫХ местах документа, проверено эмпирически (АГЕЕВ: блок
# залога ~char 2000, блок оценки ~char 8000 из 18000, у более длинных
# документов оценка может выпасть даже за 9000). Тот же класс проблемы, что
# уже решали для СРО/manager (prayer_window) и representatives (изолированный
# вызов) — сужаем ДВУМЯ прицельными якорями, не одним бланкет-окном.
_MP_COLLATERAL_RE = re.compile(
    r"а\s+именно\s*:?\s*(.+?)(?:В\s+силу\s+(?:п\.?\s*1\s+)?ст\.?\s*77|В\s+силу\s+ст\.|"
    r"Банк\s+исполнил|Право\s+собственности\s+на\s+вышеуказанн|\n\s*\n|$)",
    re.IGNORECASE | re.DOTALL,
)
_MP_VALUATION_ANCHOR_RE = re.compile(
    r"залогов\w+\s+стоимост\w+|оценка\s+по\s+определению\s+рыночной\s+стоимости|"
    r"провед\w+\s+оценк\w+\s+рыночной\s+стоимости|"
    r"заключени\w+\s+о\s+стоимости\s+имуществ\w*",
    re.IGNORECASE,
)


def _extract_collateral_block(text: str) -> str:
    """Блок залога: «…залог… а именно: <объекты>» до законной оговорки —
    компактный, один абзац на объект (description/cadastralNumber/address/
    egrnRecord), см. _mp_collateral_chunks в document_analyzer.py (тот же
    якорь, здесь без пообъектной разбивки — её делает сам LLM)."""
    m = _MP_COLLATERAL_RE.search(text)
    return m.group(1).strip()[:1500] if m else ""


def _extract_valuation_block(text: str) -> str:
    """Блок оценки: стоимость/НПЦ/отчёт об оценке — ДАЛЕКО от блока залога
    (после длинных абзацев с цитатами закона). Якорь «залоговая стоимость»/
    «оценка по определению рыночной стоимости» (тот же, что _mp_npc_strategy/
    _mp_amounts используют для точечного regex-извлечения), окно вперёд —
    весь абзац с разбивкой «в том числе <тип> — <сумма>» умещается в ~900
    символов (замерено на реальных файлах)."""
    m = _MP_VALUATION_ANCHOR_RE.search(text)
    return text[m.start(): m.start() + 900].strip() if m else ""


def _needs_fio_sro(result: dict) -> tuple[bool, bool]:
    """(need_fio, need_sro) по правилам Андрея. is_rtk определяется широко —
    ЛЮБОЙ documentType кроме rtk_application считается «Инициирование»
    (наблюдение/реструктуризация/конкурсное производство и т.п. — те же
    «процедурные акты», что и обычное инициирование для этой логики) —
    сам классификатор даёт много нишевых веток (ip_enforcement_restructuring,
    competition_collateral...), полагаться на конкретную строку хрупко.

    Ипотека (mortgage_claim) — отдельная категория дел, там нет фигуры
    арбитражного управляющего/СРО вообще (это не банкротство). Если не
    исключить явно, схема попадёт в общую ветку «Инициирование» и попросит
    у LLM несуществующее поле — модели неоткуда его брать, кроме как
    придумать."""
    fields = result.get("fields") or {}
    if result.get("documentType") == "mortgage_claim":
        return False, False
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
        is_mortgage = result.get("documentType") == "mortgage_claim"
        regex_roles = {} if is_mortgage else {
            role: {f: fields.get(f, "") or "" for f in fs}
            for role, fs in ROLE_FIELDS.items()
        }
        mortgage_regex = _mortgage_regex(result) if is_mortgage else None
        collateral_block = _extract_collateral_block(raw_text) if is_mortgage else ""
        valuation_block = _extract_valuation_block(raw_text) if is_mortgage else ""
        prayer_window = _extract_prayer_window(raw_text)[:PRAYER_WINDOW_CHARS]
        need_fio, need_sro = _needs_fio_sro(result)
        out.append({
            "file": rel,
            # Полный текст — чтобы эксперименты с шириной окна не требовали
            # перезапуска дампа в ДРУГОМ venv (здесь тянется весь
            # DocumentAnalyzer со spacy/natasha). Нарезка окон становится
            # функцией на стороне раннера, итерируется за секунды.
            "raw_text": raw_text,
            "header_window": raw_text[:HEADER_WINDOW_CHARS],
            "prayer_window": prayer_window,
            "collateral_block": collateral_block,
            "valuation_block": valuation_block,
            "entity_type": fields.get("entityType", "") or "",
            "regex_roles": regex_roles,
            "mortgage_regex": mortgage_regex,
            "document_type": result.get("documentType", "") or "",
            "is_self_bankruptcy": result.get("applicationKind") == "self_bankruptcy",
            "need_manager_fio": need_fio,
            "need_manager_sro": need_sro,
        })
        if is_mortgage:
            n_debtors = len(mortgage_regex["debtors"])
            n_tp = len(mortgage_regex["thirdParties"])
            n_props = len(mortgage_regex["properties"])
            print(f"[ok] {rel} (ипотека, debtors={n_debtors} thirdParties={n_tp} "
                  f"properties={n_props} collateral_block={len(collateral_block)}с "
                  f"valuation_block={len(valuation_block)}с)")
        else:
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
