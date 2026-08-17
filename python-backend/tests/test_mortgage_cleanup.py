# -*- coding: utf-8 -*-
"""Ипотека: незаполненный маркер уносит фразу, опустевший абзац удаляется.

Банкротные акты должны остаться на прежнем поведении (маркер + пунктуация),
поэтому каждый сценарий проверяется в обоих режимах.
"""
import os
import sys

from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from document_generator import DocumentGenerator  # noqa: E402

MORTGAGE = {"sourceDocumentType": "mortgage_claim"}
BANKRUPTCY = {}


def _build(tmp_path, paragraphs, name="t.docx"):
    d = Document()
    for text in paragraphs:
        d.add_paragraph(text)
    path = tmp_path / name
    d.save(str(path))
    return Document(str(path))


def _run(tmp_path, paragraphs, data, name="t.docx"):
    doc = _build(tmp_path, paragraphs, name)
    DocumentGenerator().replace_document_data(doc, dict(data))
    return [p.text for p in doc.paragraphs]


def test_phrase_removed_neighbours_kept(tmp_path):
    """Уходит только предложение с маркером, соседние остаются."""
    out = _run(tmp_path, ["Первая цела. Вторая с [1229] уйдёт. Третья цела."], MORTGAGE)
    assert out == ["Первая цела. Третья цела."]


def test_paragraph_with_only_marker_is_deleted(tmp_path):
    """Абзац, состоящий из одного маркера, исчезает, а не остаётся пустой строкой."""
    out = _run(tmp_path, ["До.", "[1229]", "После."], MORTGAGE)
    assert out == ["До.", "После."]


def test_label_does_not_dangle(tmp_path):
    """Подпись без значения — брак: «Дата извещения:» не должна остаться."""
    out = _run(tmp_path, ["Дата извещения: [1310].", "Хвост."], MORTGAGE)
    assert out == ["Хвост."]


def test_blank_template_paragraphs_survive(tmp_path):
    """Пустые абзацы шаблона держат вёрстку — их трогать нельзя."""
    out = _run(tmp_path, ["До.", "", "[1229]", "", "После."], MORTGAGE)
    assert out == ["До.", "", "", "После."]


def test_untouched_text_survives(tmp_path):
    out = _run(tmp_path, ["Совсем без маркеров."], MORTGAGE)
    assert out == ["Совсем без маркеров."]


def test_marker_split_across_runs(tmp_path):
    """Маркер, разорванный по run'ам, тоже должен вычищаться вместе с фразой."""
    doc_path = tmp_path / "split.docx"
    d = Document()
    p = d.add_paragraph()
    p.add_run("Дата: [1")
    p.add_run("310]. ")
    p.add_run("Хвост.")
    d.save(str(doc_path))
    doc = Document(str(doc_path))

    DocumentGenerator().replace_document_data(doc, dict(MORTGAGE))

    assert [q.text for q in doc.paragraphs] == ["Хвост."]


def test_bankruptcy_behaviour_unchanged(tmp_path):
    """Банкротство ходит прежним путём: маркер снят, подпись и абзац на месте."""
    out = _run(tmp_path, ["Дата извещения: [1310].", "[1229]", "Хвост."], BANKRUPTCY)
    assert len(out) == 3
    assert out[0].startswith("Дата извещения")
    assert "[1310]" not in out[0]
