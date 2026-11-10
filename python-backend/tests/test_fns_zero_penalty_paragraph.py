"""Точное удаление абзаца о санкциях только в резолютивках ФНС без санкций."""
import re

import pytest
from docx import Document
from lxml import etree

from document_generator import DocumentGenerator


PREFIX = ('В соответствии с пунктом 3 статьи 137 Федерального закона от 26.10.2002 '
          '№127-ФЗ «О несостоятельности (банкротстве)» ')
ENDING = ('учесть отдельно в реестре требований кредиторов, как подлежащие удовлетворению '
          'после погашения основной суммы задолженности и причитающихся процентов.')
FNS = PREFIX + 'требование в части неустоек (штрафов, пеней) и иных финансовых санкций ' + ENDING
MARKER = PREFIX + 'требования об установлении [15] руб. неустойки ' + ENDING
BASE = {"creditorName": "ФНС России в лице инспекции", "_current_doc_type": "rtk_inclusion"}


@pytest.fixture(scope="module")
def gen():
    return DocumentGenerator()


def xml_children(doc):
    return [etree.tostring(node) for node in doc.element.body]


@pytest.mark.parametrize("text", [FNS, MARKER])
@pytest.mark.parametrize("zero", [None, "", 0, "0", "0,00", "0.00", "0 руб."])
def test_only_exact_paragraph_removed_and_neighbors_byte_identical(gen, text, zero):
    doc = Document()
    doc.add_paragraph("Перед абзацем: 100 руб. госпошлины.").runs[0].bold = True
    paragraph = doc.add_paragraph()
    for char in text:
        paragraph.add_run(char).italic = True
    doc.add_paragraph(text + " Дополнительное условие — не удалять.")
    doc.add_paragraph("После абзаца: 200 руб. госпошлины.")
    before = xml_children(doc)
    gen._remove_zero_fns_penalty_paragraph(doc, {
        **BASE, "forfeit15": zero, "fnsQ3Forfeit": zero, "fnsQ3Penalties": zero,
        "obligations": [{"forfeit": zero}],
    })
    assert xml_children(doc) == before[:1] + before[2:]


@pytest.mark.parametrize("creditor", ["ПАО Сбербанк", "Другой кредитор", "", None])
@pytest.mark.parametrize("text", [FNS, MARKER])
def test_other_creditors_unchanged(gen, creditor, text):
    doc = Document()
    doc.add_paragraph(text)
    before = xml_children(doc)
    gen._remove_zero_fns_penalty_paragraph(doc, {**BASE, "creditorName": creditor})
    assert xml_children(doc) == before


@pytest.mark.parametrize("field", [
    "forfeit15", "forfeit", "penalties", "penalty0071",
    "fnsQ1Forfeit", "fnsQ2Forfeit", "fnsQ3Forfeit",
    "fnsQ1Penalties", "fnsQ2Penalties", "fnsQ3Penalties",
])
@pytest.mark.parametrize("value", ["0,01", "100", "неразобранная сумма"])
@pytest.mark.parametrize("nested", [False, True])
def test_any_nonzero_or_unknown_penalty_keeps_paragraph(gen, field, value, nested):
    doc = Document()
    doc.add_paragraph(FNS)
    before = xml_children(doc)
    extra = {"obligations": [{field: value}]} if nested else {field: value}
    gen._remove_zero_fns_penalty_paragraph(doc, {**BASE, "forfeit15": "0", **extra})
    assert xml_children(doc) == before


@pytest.mark.parametrize("doc_type", ["acceptance", "notice", "initiation", "mortgage_decision", None])
def test_other_document_types_unchanged(gen, doc_type):
    doc = Document()
    doc.add_paragraph(FNS)
    before = xml_children(doc)
    gen._remove_zero_fns_penalty_paragraph(doc, {**BASE, "_current_doc_type": doc_type})
    assert xml_children(doc) == before


def fns_templates(gen):
    import bankruptcy_tree
    return sorted(path for path in gen._templates_root().rglob("*.docx")
                  if "ФНС" in path.parts and bankruptcy_tree.file_role(path.name) == "rtk_short")


@pytest.mark.parametrize("nonzero", [False, True])
def test_all_actual_fns_templates_exact_xml_change(gen, nonzero):
    paths = fns_templates(gen)
    assert len(paths) == 12
    for path in paths:
        doc = Document(path)
        paragraphs = list(gen._iter_all_paragraphs(doc))
        targets = [p for p in paragraphs if re.sub(r"\s+", " ", gen._paragraph_text(p)).strip() == FNS]
        assert len(targets) == 1, path
        before = xml_children(doc)
        target_xml = etree.tostring(targets[0]._element)
        expected = before if nonzero else [node for node in before if node != target_xml]
        assert nonzero or len(expected) == len(before) - 1
        gen._remove_zero_fns_penalty_paragraph(doc, {**BASE, "fnsQ3Penalties": "0,01" if nonzero else "0"})
        assert xml_children(doc) == expected, path


@pytest.mark.parametrize("nonzero", [False, True])
def test_full_replacement_all_actual_fns_templates(gen, nonzero):
    for path in fns_templates(gen):
        doc = Document(path)
        gen.replace_document_data(doc, {
            **BASE, "entityType": "individual", "fnsQ3LoanDebt": "1000",
            "fnsQ3Forfeit": "10" if nonzero else "0", "fnsQ3Penalties": "0",
        })
        text = "\n".join(gen._paragraph_text(p) for p in list(gen._iter_all_paragraphs(doc)))
        assert (FNS in text) == nonzero, path
