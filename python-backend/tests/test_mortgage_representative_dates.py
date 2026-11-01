"""Даты доверенности из полей формы доходят до маркеров обоих сроков."""

import pytest
from docx import Document

from document_generator import DocumentGenerator
from test_civil_mortgage_generation import mortgage_data


@pytest.fixture
def generator(tmp_path):
    gen = DocumentGenerator()
    gen.generated_dir = tmp_path
    return gen


@pytest.mark.parametrize("kind", ["civil", "ddu", "military"])
def test_representative_dates_from_preview_request_fill_both_markers(generator, kind, tmp_path, monkeypatch):
    data = mortgage_data(True)
    data.update(selectedMortgageKind=kind, mortgageKind=kind,
                _current_doc_type="mortgage_full_decision")
    values = {"representativeName":"Орлов Олег Олегович",
              "representativePoaFrom":"29.02.2032", "representativePoaTo":"22.08.2034"}
    for key in values:
        data.pop(key, None)
        data["fields"].pop(key, None)
    data.update(values)
    data.pop("fields", None)
    doc = Document()
    doc.add_paragraph("С участием представителя истца [1440], действующего на основании "
                      "доверенности № ****** от [1441] г., действующей по [1442] г.")
    path = tmp_path / "poa.docx"
    doc.save(path)
    monkeypatch.setattr(generator, "_get_mortgage_templates", lambda data: {
        "mortgage_full_decision": {"name":"Проверка доверенности", "path":path, "order":1},
    })
    result = generator.generate("mortgage", data)
    assert result["success"], result
    generated = Document(result["documents"]["mortgage_full_decision"]["file_path"])
    actual = "\n".join(p.text for p in generated.paragraphs)
    assert "Орлов Олег Олегович" in actual
    assert "от 29.02.2032 г., действующей по 22.08.2034 г." in actual
    assert "№ ******" in actual
    assert "[1441]" not in actual and "[1442]" not in actual


@pytest.mark.parametrize("kind", ["civil", "ddu", "military"])
@pytest.mark.parametrize("start,end", [("29.02.2020",""), ("","22.08.2034"), ("","")])
def test_optional_dates_survive_independently(generator, tmp_path, monkeypatch, kind, start, end):
    data = mortgage_data(True)
    data.pop("fields", None)
    data.update(selectedMortgageKind=kind, mortgageKind=kind,
                representativePoaFrom=start, representativePoaTo=end)
    doc = Document()
    doc.add_paragraph("Представитель истца [1440] в судебное заседание не явился.")
    doc.add_paragraph("Доверенность представителя истца от [1441] г.")
    doc.add_paragraph("Доверенность представителя истца действует по [1442] г.")
    path = tmp_path / "optional-poa.docx"
    doc.save(path)
    monkeypatch.setattr(generator, "_get_mortgage_templates", lambda data: {
        "mortgage_full_decision": {"name":"Проверка сроков", "path":path, "order":1},
    })
    result = generator.generate("mortgage", data)
    assert result["success"], result
    generated = Document(result["documents"]["mortgage_full_decision"]["file_path"])
    text = "\n".join(p.text for p in generated.paragraphs)
    assert "Представитель истца Орлов Олег Олегович в судебное заседание не явился." in text
    assert ("от 29.02.2020 г." in text) == bool(start)
    assert ("по 22.08.2034 г." in text) == bool(end)
    assert "[1441]" not in text and "[1442]" not in text
