# -*- coding: utf-8 -*-
"""Детерминированная сериализация результата analyze() для golden-master.

Снимок фиксирует ВСЁ значимое поведение анализатора на одном документе:
извлечённые поля, обязательства, залоги, должников, третьих лиц, рекомендованные
акты, тип/уверенность и характеристику исходного текста (длина + sha256).

`rawText` целиком в снимок не кладём (он огромен и дублирует вход), но его
длина и sha256 служат стражем: если извлечение текста изменится — снимок
поймает это, не раздувая файл.

Один и тот же код используют генератор эталона и pytest-сверка — гарантия,
что сравнение идёт по идентичным правилам.
"""
from __future__ import annotations

import glob
import hashlib
import os
from typing import Any, Dict, List

# Каталоги
_THIS = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.abspath(os.path.join(_THIS, "..", "..", "app"))
CORPUS_DIR = os.path.abspath(os.path.join(_THIS, "..", "..", "..", "Заявления"))
GOLDEN_PATH = os.path.join(_THIS, "golden_master.json")

# Поля верхнего уровня результата analyze(), которые фиксируем (rawText — отдельно).
_TOP_FIELDS = (
    "documentType", "confidence", "fields", "obligations", "collaterals",
    "recommendedActs", "debtors", "thirdParties", "entityType", "metadata",
)


# Документы, исключённые из корпуса (слишком плохое качество исходника — разбор
# заведомо мусорный, держать в эталоне бессмысленно). Относительные пути от CORPUS_DIR.
EXCLUDED_FILES = {
    "casebookWord/Заявление (1).docx",
    # Исковое о ВЗЫСКАНИИ (ГПК РФ, исполнительный лист), а не банкротное —
    # по имени правило «взыскан» его не ловит, исключаем явно.
    "ИП заявл.docx",
}


def _is_excluded(rel: str) -> bool:
    """Файл вне корпуса, если он в EXCLUDED_FILES, это ЛЮБОЙ PDF, заявление о
    взыскании или синтетическая болванка «БМ …». Работаем только с docx
    (PDF-распознавание менее точное), без взысканий и болванок.
    """
    if rel in EXCLUDED_FILES:
        return True
    # PDF из эталона исключены полностью — работаем только с docx (договорённость:
    # PDF-распознавание менее точное, для каждого PDF есть/будет docx-вариант).
    if rel.lower().endswith(".pdf"):
        return True
    # Заявления о взыскании — вне задачи (не банкротные), в эталоне не держим.
    if "взыскан" in rel.lower():
        return True
    # Синтетические болванки «БМ …» (намеренно «трудные» фейковые данные) — не эталон.
    if os.path.basename(rel).startswith("БМ"):
        return True
    return False


def corpus_files() -> List[str]:
    """Отсортированный список относительных путей всех документов корпуса (без исключённых)."""
    if not os.path.isdir(CORPUS_DIR):
        return []
    files = []
    for ext in ("*.docx", "*.pdf"):
        for f in glob.glob(os.path.join(CORPUS_DIR, "**", ext), recursive=True):
            if "~$" in os.path.basename(f):
                continue
            rel = os.path.relpath(f, CORPUS_DIR).replace("\\", "/")
            if _is_excluded(rel):
                continue
            files.append(rel)
    return sorted(set(files))


def _round_floats(obj: Any) -> Any:
    """Рекурсивно округляет float до 6 знаков — устраняет дрейф представления."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v) for v in obj]
    return obj


def snapshot_one(analyzer, rel_path: str) -> Dict[str, Any]:
    """Снимок поведения analyze() на одном документе.

    При исключении фиксируем тип+сообщение ошибки — чтобы ловить и появление,
    и исчезновение ошибок при рефакторинге.
    """
    abs_path = os.path.join(CORPUS_DIR, rel_path)
    try:
        result = analyzer.analyze(abs_path)
    except Exception as exc:  # фиксируем ошибку как часть эталона
        return {"__error__": f"{type(exc).__name__}: {exc}"}

    snap: Dict[str, Any] = {}
    for key in _TOP_FIELDS:
        if key in result:
            snap[key] = result[key]
    raw = result.get("rawText", "") or ""
    snap["rawTextLen"] = len(raw)
    snap["rawTextSha"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return _round_floats(snap)


def build_snapshot(analyzer, files: List[str] | None = None) -> Dict[str, Any]:
    """Снимок по всему корпусу: {rel_path: snapshot_one(...)}"""
    files = files if files is not None else corpus_files()
    return {rel: snapshot_one(analyzer, rel) for rel in files}
