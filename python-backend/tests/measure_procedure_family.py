# -*- coding: utf-8 -*-
"""Измеритель facet-классификатора «процедура» (rtk/initiation) — presence-тест
по пунктам просительной части (`semantic_classifier.classify_procedure_family`)
против семейства, выводимого из regex `document_type` (план `new_asnaliz`
§Фаза 2, второй заход после провала nearest-neighbor-подхода на 48%).

Сопоставление document_type -> ожидаемое семейство:
  rtk_application                              -> rtk
  mortgage_claim, ip_collection, legal_collection,
  unknown                                      -> НЕ бэнкротная процедура, пропускаем
  всё остальное (initiation_*, ip_enforcement_*,
  physical_*_collateral, observation_collateral,
  competition_collateral)                      -> initiation

Запуск: cd python-backend && venv/Scripts/python.exe tests/measure_procedure_family.py
"""
import logging
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
logging.disable(logging.CRITICAL)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
sys.path.insert(0, os.path.join(_THIS, "golden"))

from _snapshot import corpus_files, CORPUS_DIR  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402
from semantic_classifier import classify_procedure_family, _ensure_model  # noqa: E402

_NOT_PROCEDURE = {"mortgage_claim", "ip_collection", "ip_collection_collateral",
                   "ip_collection_collateral_auto", "legal_collection",
                   "legal_collection_collateral", "legal_collection_collateral_auto",
                   "unknown"}


def expected_family(document_type: str) -> str | None:
    if document_type == "rtk_application":
        return "rtk"
    if document_type in _NOT_PROCEDURE:
        return None
    return "initiation"


def main() -> int:
    if not _ensure_model():
        print("Семантическая модель недоступна локально — измерение невозможно.")
        return 1

    az = DocumentAnalyzer()
    files = corpus_files()
    agree = 0
    disagree = []
    skipped = 0
    no_family = 0

    for rel in files:
        path = os.path.join(CORPUS_DIR, rel)
        try:
            result = az.analyze(path)
        except Exception as exc:
            print(f"[ОШИБКА] {rel}: {exc}")
            continue
        # Самобанкротство обрабатывается ОТДЕЛЬНЫМ флагом (`applicationKind`),
        # не через document_type: рутинно получает 'rtk_application' даже
        # когда по содержанию просительной части — инициирование (гражданин
        # признаёт себя банкротом). document_type здесь не годится как эталон.
        if result.get("applicationKind") == "self_bankruptcy":
            skipped += 1
            continue
        exp = expected_family(result.get("documentType"))
        if exp is None:
            skipped += 1
            continue
        raw_text = result.get("rawText", "")
        debtor_name = (result.get("fields") or {}).get("debtorName", "")
        fam, details = classify_procedure_family(raw_text, debtor_name)
        if fam is None:
            no_family += 1
            disagree.append((rel, result.get("documentType"), exp, fam, details))
            continue
        if fam == exp:
            agree += 1
        else:
            disagree.append((rel, result.get("documentType"), exp, fam, details))

    total = agree + len(disagree)
    print("=" * 70)
    print(f"Корпус: {len(files)} файлов, вне процедуры банкротства (пропущены): {skipped}")
    print(f"Facet не определился (presence-тест ничего не нашёл): {no_family}")
    print(f"Согласие regex-семейство / facet-классификатор: {agree}/{total} "
          f"({100 * agree // max(total, 1)}%)")
    print("=" * 70)
    print("РАСХОЖДЕНИЯ:")
    for rel, doc_type, exp, got, details in disagree:
        print(f"  {rel}")
        print(f"    documentType={doc_type!r}  ожидали={exp!r}  получили={got!r}")
        for k, (found, score, sent) in details.items():
            print(f"      {k}: {found} ({score:.2f}) {sent!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
