# -*- coding: utf-8 -*-
"""Инвариант посекционного предпросмотра (`extract_sections`).

Ключевая гарантия нулевого риска для анализа/golden: секции — это лишь
ПРЕДСТАВЛЕНИЕ строк `extract_text`. Соединение строк всех секций в порядке их
глобального `index` должно быть БАЙТ-В-БАЙТ равно `extract_text`, а сами индексы
— полной партицией частей (без потерь и дублей).
"""
import glob
import os

import pytest

from document_analyzer import DocumentAnalyzer

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _corpus(limit=20):
    files = []
    for sub in ("Templates", "Заявления", "python-backend/generated"):
        base = os.path.join(_ROOT, sub)
        if os.path.isdir(base):
            files += [f for f in glob.glob(os.path.join(base, "**", "*.docx"), recursive=True)
                      if "~$" not in f]
    return sorted(files)[:limit]


CORPUS = _corpus()


def _reassemble(sections):
    lines = [ln for sec in sections for ln in sec["lines"]]
    lines.sort(key=lambda ln: ln["index"])
    return "\n".join(ln["text"] for ln in lines), [ln["index"] for ln in lines]


@pytest.mark.skipif(not CORPUS, reason="нет DOCX для проверки инварианта")
@pytest.mark.parametrize("path", CORPUS)
def test_sections_reassemble_to_extract_text(path):
    da = DocumentAnalyzer()
    text = da.extract_text(path)
    sections = da.extract_sections(path)
    n_parts = len(da._docx_text_parts(path))

    reassembled, indices = _reassemble(sections)
    assert reassembled == text, f"секции не пересобираются в extract_text: {path}"
    # Партиция: каждый индекс ровно один раз, покрыт весь диапазон частей.
    assert sorted(indices) == list(range(n_parts)), f"индексы не образуют партицию: {path}"


def _build_docx(tmp_path, petition="Прошу суд признать должника банкротом"):
    """Синтетический DOCX: вводная, титул, мотивировка, просьба, приложения, таблица."""
    from docx import Document

    doc = Document()
    doc.add_paragraph("В Арбитражный суд Ростовской области")           # вводная
    doc.add_paragraph("Должник: ИП Иванов Иван Иванович")               # вводная
    doc.add_paragraph("ЗАЯВЛЕНИЕ о признании должника банкротом")       # титул → body
    doc.add_paragraph("Между сторонами заключён кредитный договор.")     # body
    doc.add_paragraph(petition)                                          # просьба → prayer
    doc.add_paragraph("Приложения:")                                     # приложения
    doc.add_paragraph("1. Копия договора")                               # приложения
    table = doc.add_table(rows=1, cols=2)                                # таблица (после тела → приложения)
    table.rows[0].cells[0].text = "Договор №1"
    table.rows[0].cells[1].text = "1 000 000 руб."
    out = os.path.join(tmp_path, "synthetic.docx")
    doc.save(out)
    return out


def test_sections_four_blocks_full(tmp_path):
    da = DocumentAnalyzer()
    path = _build_docx(tmp_path)

    text = da.extract_text(path)
    sections = da.extract_sections(path)
    n_parts = len(da._docx_text_parts(path))
    reassembled, indices = _reassemble(sections)

    assert reassembled == text
    assert sorted(indices) == list(range(n_parts))
    assert [s["id"] for s in sections] == ["header", "body", "prayer", "attachments"]

    by_id = {s["id"]: " ".join(ln["text"] for ln in s["lines"]) for s in sections}
    assert "Арбитражный суд" in by_id["header"]
    assert "ЗАЯВЛЕНИЕ" in by_id["body"]
    assert "кредитный договор" in by_id["body"]
    assert "Прошу" in by_id["prayer"]
    assert "Приложения" in by_id["attachments"]
    # Таблица идёт за телом → в последний блок (приложения), не раньше.
    assert "Договор №1" in by_id["attachments"]
    assert "Прошу" not in by_id["attachments"]
    assert "Приложения" not in by_id["prayer"]


@pytest.mark.parametrize(
    "petition",
    ["ПРОСИТ признать банкротом", "ПРОСИМ СУД включить", "Ходатайствуем об отложении",
     "просит суд", "ХОДАТАЙСТВУЮ о приобщении"],
)
def test_prayer_anchor_variants(tmp_path, petition):
    """Разные глаголы-просьбы (ПРОСИТ/ПРОСИМ/ХОДАТАЙСТВУЮ…) открывают prayer."""
    da = DocumentAnalyzer()
    path = _build_docx(tmp_path, petition=petition)
    sections = da.extract_sections(path)
    by_id = {s["id"]: " ".join(ln["text"] for ln in s["lines"]) for s in sections}
    assert petition.split()[0] in by_id.get("prayer", ""), f"не распознан якорь: {petition}"


def test_prayer_anchor_ignores_inline_proshu_in_body(tmp_path):
    """«…управляющего прошу назначить…» в мотивировке НЕ открывает просительную —
    prayer стартует на строке-маркере «ПРОШУ:» (реальный кейс Андрея)."""
    da = DocumentAnalyzer()
    from docx import Document

    doc = Document()
    doc.add_paragraph("ЗАЯВЛЕНИЕ о признании банкротом")
    doc.add_paragraph(
        "Кандидатуру финансового управляющего прошу назначить из числа членов союза"
    )
    doc.add_paragraph("На основании вышеизложенного, руководствуясь ст. 213.4 Закона,")
    doc.add_paragraph("ПРОШУ:")
    doc.add_paragraph("1. Ввести реструктуризацию долгов гражданина.")
    p = os.path.join(tmp_path, "candidacy.docx")
    doc.save(p)

    sections = da.extract_sections(p)
    by_id = {s["id"]: "\n".join(ln["text"] for ln in s["lines"]) for s in sections}
    # Кандидатура — в мотивировочной части, не в просительной.
    assert "Кандидатуру" in by_id.get("body", "")
    assert "Кандидатуру" not in by_id.get("prayer", "")
    # Просительная открывается ровно на «ПРОШУ:».
    assert by_id.get("prayer", "").startswith("ПРОШУ:")
    assert "Ввести реструктуризацию" in by_id.get("prayer", "")


def test_prayer_anchor_ignores_prositelnoy(tmp_path):
    """«просительной» НЕ должно ложно срабатывать как якорь просьбы."""
    da = DocumentAnalyzer()
    from docx import Document

    doc = Document()
    doc.add_paragraph("ЗАЯВЛЕНИЕ")
    doc.add_paragraph("В просительной части указано следующее описание фактов.")
    doc.add_paragraph("Прошу признать банкротом")
    p = os.path.join(tmp_path, "prositelnoy.docx")
    doc.save(p)

    sections = da.extract_sections(p)
    by_id = {s["id"]: " ".join(ln["text"] for ln in s["lines"]) for s in sections}
    # Строка про «просительной» осталась в body, prayer открылся на «Прошу».
    assert "просительной части" in by_id.get("body", "")
    assert by_id.get("prayer", "").startswith("Прошу")
