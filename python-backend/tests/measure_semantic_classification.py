# -*- coding: utf-8 -*-
"""Измеритель shadow-слоя семантической классификации (план `new_asnaliz`).

Прогоняет `document_type` (regex, `classify_mixin.classify_document`) против
`classify_semantic` (эмбеддинги) по ВСЕМУ golden-корпусу и печатает согласие/
расхождения — данные для ручного разбора Андреем (план §1.3/§Фаза 2). Ничего
не чинит и не сравнивается с golden: это диагностика, не тест на регрессию.

Требует локально установленный `sentence-transformers` + модель в
`python-backend/models/paraphrase-multilingual-MiniLM-L12-v2/` (см.
`requirements.txt`, `semantic_classifier.py`). Без них — сообщение и выход.

Запуск: cd python-backend && venv/Scripts/python.exe tests/measure_semantic_classification.py
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

from _snapshot import corpus_files, APP_DIR, CORPUS_DIR  # noqa: E402
from document_analyzer import DocumentAnalyzer  # noqa: E402
from semantic_classifier import classify_semantic, _ensure_model  # noqa: E402
from semantic_reference_phrases import SEMANTIC_DOCUMENT_TYPES  # noqa: E402


def main() -> int:
    if not _ensure_model():
        print("Семантическая модель недоступна локально — измерение невозможно.")
        print(f"Ожидается: {os.path.join(APP_DIR, '..', 'models', 'paraphrase-multilingual-MiniLM-L12-v2')}")
        return 1

    az = DocumentAnalyzer()
    files = corpus_files()
    agree = 0
    disagree = []
    no_semantic = 0

    for rel in files:
        path = os.path.join(CORPUS_DIR, rel)
        try:
            fields_result = az.analyze(path)
        except Exception as exc:
            print(f"[ОШИБКА] {rel}: {exc}")
            continue
        regex_type = fields_result.get("documentType")
        raw_text = fields_result.get("rawText", "")
        sem_label, sem_score, sem_sentence = classify_semantic(raw_text, SEMANTIC_DOCUMENT_TYPES)

        if sem_label is None:
            no_semantic += 1
            continue
        if sem_label == regex_type:
            agree += 1
        else:
            disagree.append((rel, regex_type, sem_label, sem_score, sem_sentence))

    total_compared = agree + len(disagree)
    print("=" * 70)
    print(f"Корпус: {len(files)} файлов")
    print(f"Семантика не дала кандидата выше порога: {no_semantic}")
    print(f"Согласие regex/семантика: {agree}/{total_compared} "
          f"({100 * agree // max(total_compared, 1)}%)")
    print("=" * 70)
    print("РАСХОЖДЕНИЯ (для ручного разбора):")
    for rel, regex_type, sem_label, sem_score, sem_sentence in disagree:
        print(f"  {rel}")
        print(f"    regex={regex_type!r}  semantic={sem_label!r} (score={sem_score:.2f})")
        print(f"    предложение: {sem_sentence!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
