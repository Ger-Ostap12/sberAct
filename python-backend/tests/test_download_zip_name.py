# -*- coding: utf-8 -*-
"""Сквозная проверка: имя архива доезжает до заголовка скачивания."""
import asyncio
import sys
from pathlib import Path

import pytest

КОРЕНЬ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(КОРЕНЬ / "app"))

main = pytest.importorskip("main")


def скачать(ids: str):
    """Зовём обработчик напрямую: TestClient в этой сборке httpx не заводится."""
    return asyncio.run(main.download_zip_get(ids=ids))


@pytest.fixture
def документ():
    """Один сгенерированный акт в хранилище и на диске."""
    генератор = main.document_generator
    doc_id = "тест-архив-1"
    путь = генератор.generated_dir / f"{doc_id}.docx"
    путь.parent.mkdir(parents=True, exist_ok=True)
    путь.write_bytes(b"PK\x03\x04 fake docx")
    генератор.documents[doc_id] = {
        "document_name": "Определение о принятии",
        "data": {"debtors": [{"name": "Иванов Иван Иванович"}]},
    }
    yield doc_id
    генератор.documents.pop(doc_id, None)
    путь.unlink(missing_ok=True)


def test_заголовок_несёт_фио_должника(документ):
    ответ = скачать(документ)
    assert ответ.status_code == 200
    cd = ответ.headers["content-disposition"]
    assert "filename*=UTF-8''" in cd
    assert "%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2" in cd  # «Иванов» в процентах
    assert cd.startswith("attachment;")


def test_в_заголовке_есть_дата_в_формате_день_месяц_год(документ):
    from datetime import date
    ответ = скачать(документ)
    assert date.today().strftime("%d-%m-%Y") in ответ.headers["content-disposition"]


def test_имя_больше_не_generated_documents(документ):
    ответ = скачать(документ)
    assert "generated_documents.zip" not in ответ.headers["content-disposition"]


def test_без_данных_должника_запасное_имя():
    генератор = main.document_generator
    doc_id = "тест-архив-2"
    путь = генератор.generated_dir / f"{doc_id}.docx"
    путь.parent.mkdir(parents=True, exist_ok=True)
    путь.write_bytes(b"PK\x03\x04 fake docx")
    генератор.documents[doc_id] = {"document_name": "Акт", "data": {}}
    try:
        ответ = скачать(doc_id)
        cd = ответ.headers["content-disposition"]
        # «Судебные акты» в процентной кодировке начинается с «Су».
        assert "%D0%A1%D1%83%D0%B4%D0%B5%D0%B1%D0%BD%D1%8B%D0%B5" in cd
    finally:
        генератор.documents.pop(doc_id, None)
        путь.unlink(missing_ok=True)
