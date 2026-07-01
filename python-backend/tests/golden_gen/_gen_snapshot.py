# -*- coding: utf-8 -*-
"""Детерминированный снимок поведения генератора (analyze -> generate -> текст docx).

Защищаемое поведение здесь — РЕНДЕРЕННЫЙ ТЕКСТ итоговых .docx. Рефакторинг
`document_generator.py` (replace_document_data, generate, резолверы шаблонов и т.д.)
не должен менять ни набор формируемых документов, ни их текст.

Снимок на один входной документ:
    {input_rel: {
        "documents": {
            doc_key: {"name": ..., "order": ..., "text": <полный текст docx>}
        }
    }}
либо {"__error__": "Type: msg"} при исключении analyze/generate.

Полный текст хранится намеренно — диффы при регрессии должны быть читаемыми
(в отличие от rawText в analyze-снимке, тут текст docx и есть результат работы).

Недетерминизм нейтрализуется:
  * UUID-имена файлов (document_id, file_path) в снимок НЕ кладём.
  * `datetime.now()` замораживается (`freeze_now`), иначе плейсхолдер currentDate
    в части шаблонов делал бы эталон зависящим от дня прогона.

Один и тот же код используют генератор эталона и pytest-сверка.
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from datetime import datetime as _RealDateTime
from typing import Any, Dict, List

_THIS = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.abspath(os.path.join(_THIS, "..", "..", "app"))
# Корпус и список файлов переиспользуем из analyze-снимка — единый источник правды.
_GOLDEN_DIR = os.path.abspath(os.path.join(_THIS, "..", "golden"))
sys.path.insert(0, _GOLDEN_DIR)
sys.path.insert(0, APP_DIR)

from _snapshot import CORPUS_DIR, corpus_files  # noqa: E402,F401  (re-export)

GOLDEN_PATH = os.path.join(_THIS, "gen_golden_master.json")

# Зафиксированный «сейчас» для воспроизводимости currentDate в шаблонах.
_FROZEN_NOW = _RealDateTime(2026, 1, 1, 12, 0, 0)


class _FrozenDateTime(_RealDateTime):
    @classmethod
    def now(cls, tz=None):  # noqa: D401
        return _FROZEN_NOW if tz is None else _FROZEN_NOW.astimezone(tz)


@contextlib.contextmanager
def freeze_now():
    """Замораживает datetime.now() внутри document_generator на время прогона."""
    import document_generator as dg

    saved = dg.datetime
    dg.datetime = _FrozenDateTime
    try:
        yield
    finally:
        dg.datetime = saved


def _docx_text(path: str) -> str:
    """Полный текст docx: абзацы + ячейки таблиц, в порядке тела документа."""
    from docx import Document

    doc = Document(path)
    parts: List[str] = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def snapshot_one(analyzer, generator, rel_path: str) -> Dict[str, Any]:
    """Снимок: analyze(вход) -> generate('', data) -> текст каждого docx.

    template_type пустой — это режим авто-роутинга по sourceDocumentType
    (детерминированно выводится из данных анализа), без пользовательских
    selectedActsIds. Этого достаточно как стабильной сети для рефакторинга ядра.
    """
    abs_path = os.path.join(CORPUS_DIR, rel_path)
    try:
        data = analyzer.analyze(abs_path)
    except Exception as exc:
        return {"__error__": f"analyze {type(exc).__name__}: {exc}"}

    # ВАЖНО: фронт (DocumentPreview.tsx) шлёт в generate() ПЛОСКИЕ данные —
    # разворачивает analyze()['fields'] в top-level + sourceDocumentType + obligations.
    # Без этого generate() читает пустой top-level и рендерит акты без сумм/сторон.
    # Тест обязан повторять реальный путь фронта, иначе не проверяет генерацию.
    _fields = data.get("fields") or {}
    gen_data = {
        **_fields,
        "sourceDocumentType": _fields.get("sourceDocumentType")
        or data.get("sourceDocumentType") or data.get("documentType"),
        "obligations": data.get("obligations") or _fields.get("obligations") or [],
    }

    # Каждый прогон — в свежий temp-каталог, чтобы не мусорить generated/.
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path

        generator.generated_dir = Path(tmp)
        try:
            with freeze_now():
                res = generator.generate("", gen_data)
        except Exception as exc:
            return {"__error__": f"generate {type(exc).__name__}: {exc}"}

        if not res.get("success"):
            return {"__error__": f"generate failed: {res.get('error')}"}

        docs_out: Dict[str, Any] = {}
        for key, info in (res.get("documents") or {}).items():
            fp = info.get("file_path")
            try:
                text = _docx_text(fp) if fp and os.path.exists(fp) else ""
            except Exception as exc:
                text = f"__read_error__ {type(exc).__name__}: {exc}"
            docs_out[key] = {
                "name": info.get("name"),
                "order": info.get("order"),
                "text": text,
            }
    return {"documents": docs_out}


def build_snapshot(analyzer, generator, files: List[str] | None = None) -> Dict[str, Any]:
    files = files if files is not None else corpus_files()
    return {rel: snapshot_one(analyzer, generator, rel) for rel in files}
