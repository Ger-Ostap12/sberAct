"""Знак номера повторяется у каждого договора в сводном перечне."""
import pytest
from docx import Document

from document_generator import DocumentGenerator


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


@pytest.mark.parametrize("source_type", ["rtk_application", "mortgage_claim"])
@pytest.mark.parametrize("numbers", [
    "123, 234, 3434",
    "123, №234, № 3434",
    "КД-123/А, КД-234/Б, КД-3434/В",
])
def test_summary_numbers_have_individual_signs(generator, source_type, numbers):
    doc = Document()
    paragraph = doc.add_paragraph("Задолженность по договорам № ")
    paragraph.add_run("[110]")
    paragraph.add_run(".")
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    cell.text = "По договорам № [110]."
    data = {"sourceDocumentType": source_type, "contractNumber": numbers}
    generator.replace_document_data(doc, data)
    expected_numbers = [
        part.strip().removeprefix("№").strip() for part in numbers.split(",")
    ]
    expected = "№ " + ", № ".join(expected_numbers)
    assert paragraph.text == f"Задолженность по договорам {expected}."
    assert cell.text == f"По договорам {expected}."
    assert data["contractNumber"] == numbers


def test_separate_obligation_slots_keep_one_sign_each(generator):
    doc = Document()
    doc.add_paragraph("По договорам № [110], № [111], № [112].")
    generator.replace_document_data(doc, {
        "sourceDocumentType": "rtk_application",
        "obligations": [
            {"contractNumber": number} for number in ("123", "234", "3434")
        ],
    })
    assert doc.paragraphs[0].text == "По договорам № 123, № 234, № 3434."


def test_single_number_stays_unchanged(generator):
    doc = Document()
    doc.add_paragraph("По договору № [110].")
    generator.replace_document_data(doc, {
        "sourceDocumentType": "rtk_application", "contractNumber": "КД-123/А",
    })
    assert doc.paragraphs[0].text == "По договору № КД-123/А."

def test_number_list_inside_obligation_card(generator):
    doc = Document()
    doc.add_paragraph("По договорам № [110].")
    generator.replace_document_data(doc, {
        "sourceDocumentType": "rtk_application",
        "obligations": [{"contractNumber": "123, 234, 3434"}],
    })
    assert doc.paragraphs[0].text == "По договорам № 123, № 234, № 3434."
