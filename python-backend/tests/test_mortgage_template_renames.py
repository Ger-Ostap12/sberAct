
"""Переименованные ипотечные шаблоны сохраняют выбор пользователя и все объекты."""

from copy import deepcopy
from itertools import product
import re

import pytest
from docx import Document
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from mortgage_properties import BLOCK_NAME, MARKER
from test_mortgage_full_package import packet_data


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


@pytest.fixture(scope="module")
def combined_debtors():
    from document_analyzer import DocumentAnalyzer
    analyzer = DocumentAnalyzer()
    people = deepcopy(packet_data("civil", rep=True)["debtors"])
    third = dict(people[0], name="Кузнецов Олег Сергеевич", inn="616100000003")
    return {2: analyzer._combine_debtors(people),
            3: analyzer._combine_debtors(people + [third])}


@pytest.mark.parametrize("rep,solid,outcome,count", [
    (*flags, count) for flags in product((False, True), (False, True), ("full", "partial", "deny"))
    for count in (1, 2, 3)
])
def test_updated_templates_follow_solidarity_choice(generator, combined_debtors, rep, solid, outcome, count):
    data = packet_data("civil", rep=rep, solid=solid, outcome=outcome)
    data.update(sourceDocumentType="mortgage_claim", _current_doc_type="mortgage_decision")
    people = deepcopy(packet_data("civil", rep=True)["debtors"])
    data["debtors"] = people[:count]
    if count == 3:
        data["debtors"].append(dict(people[0], name="Кузнецов Олег Сергеевич", inn="616100000003"))
    data["applicantName"] = ", ".join(p["name"] for p in data["debtors"])
    data["fields"]["applicantName"] = data["applicantName"]
    if count >= 2:
        data.update(combined_debtors[count])
        data["fields"].update(combined_debtors[count])
    path = generator._get_mortgage_templates(data)["mortgage_decision"]["path"]
    assert path.name == ("реш_рез обычная представители солидарное ипотека.docx"
                         if rep else "реш_рез обычная 1 должник несолид ипот.docx")
    doc = Document(path)
    generator.set_times_new_roman_11(doc)
    generator.replace_document_data(doc, data)
    text = "\n".join(p.text for p in doc.paragraphs)
    recovery = [p.text for p in doc.paragraphs if p.text.startswith("Взыскать")]
    assert bool(recovery) == (outcome != "deny")
    assert bool(re.search(r"солидарно|в солидарном порядке", text)) == (solid and outcome != "deny")
    assert not re.search(r"\[\d+(?:\.\d+)?\]", text)
    if recovery:
        assert ("солидарно" in recovery[0]) == solid
        for person in data["debtors"]:
            assert person["name"].split()[0][:4] in recovery[0]


@pytest.mark.parametrize("rep,solid", list(product((False, True), repeat=2)))
def test_legacy_filenames_still_work(generator, tmp_path, monkeypatch, rep, solid):
    names = {
        (False, False): "реш_рез обычная должник не солидарное ипот.docx",
        (False, True): "реш_рез обычная должник солидарное ипот.docx",
        (True, False): "реш_рез обычная представители не солидарное ипотека.docx",
        (True, True): "реш_рез представители солидарное обычная ипот.docx",
    }
    path = tmp_path / "Ипотека" / "обычная ипотека решения" / names[rep, solid]
    path.parent.mkdir(parents=True)
    Document().save(path)
    monkeypatch.setattr(generator, "_templates_root", lambda: tmp_path)
    selected = generator._get_mortgage_templates(packet_data("civil", rep=rep, solid=solid))
    assert selected["mortgage_decision"]["path"] == path


@pytest.mark.parametrize("kind", ("civil", "ddu", "military"))
def test_every_full_property_description_is_inside_a_repeat_block(generator, kind):
    path = generator._get_mortgage_templates(packet_data(kind))["mortgage_full_decision"]["path"]
    doc = Document(path)
    nodes = list(doc.element.body.iter())
    spans = []
    for node in nodes:
        if node.tag == qn("w:bookmarkStart") and BLOCK_NAME.fullmatch(node.get(qn("w:name"), "")):
            ends = [e for e in nodes if e.tag == qn("w:bookmarkEnd")
                    and e.get(qn("w:id")) == node.get(qn("w:id"))]
            assert len(ends) == 1
            spans.append((nodes.index(node), nodes.index(ends[0])))
    assert spans
    for paragraph in doc.paragraphs:
        if "[1221]" not in paragraph.text:
            continue
        marker_nodes = [n for n in paragraph._p.iter(qn("w:t")) if MARKER.search(n.text or "")]
        assert marker_nodes, paragraph.text
        assert all(any(left < nodes.index(n) < right for left, right in spans) for n in marker_nodes), paragraph.text


def test_civil_full_repeats_all_seven_property_sections(generator):
    data = packet_data("civil")
    data.update(sourceDocumentType="mortgage_claim", _current_doc_type="mortgage_full_decision")
    path = generator._get_mortgage_templates(data)["mortgage_full_decision"]["path"]
    doc = Document(path)
    generator.set_times_new_roman_11(doc)
    generator.replace_document_data(doc, data)
    text = "\n".join(p.text for p in doc.paragraphs)
    for item in data["mortgageProperties"]:
        assert text.count(item["description"]) == 7
        assert text.count(item["cadastralNumber"]) == 5
        assert text.count(item["egrnRecord"]) == 5
    assert not list(doc.element.iter(qn("w:bookmarkStart")))


@pytest.mark.parametrize("count,solid", list(product((1, 3), (False, True))))
def test_api_keeps_all_respondents_in_the_updated_template(generator, monkeypatch, tmp_path, count, solid):
    from test_mortgage_full_package import render
    data = packet_data("civil", rep=True, solid=solid)
    data["sourceDocumentType"] = "mortgage_claim"
    people = deepcopy(data["debtors"])
    data["debtors"] = people[:count]
    if count == 3:
        data["debtors"].append(dict(people[0], name="Кузнецов Олег Сергеевич", inn="616100000003"))
    templates = generator._get_mortgage_templates(data)
    monkeypatch.setattr(generator, "_get_mortgage_templates",
                        lambda local: {"mortgage_decision": templates["mortgage_decision"]})
    result, docs = render(generator, monkeypatch, tmp_path, data)
    assert result["count"] == 1 and not result.get("warnings")
    paragraphs = [p.text for p in docs["mortgage_decision"].paragraphs]
    recovery = next(p for p in paragraphs if p.startswith("Взыскать"))
    for person in data["debtors"]:
        assert person["name"].split()[0][:4] in recovery
    assert ("солидарно" in recovery) == solid
    assert any(p.startswith("рассмотрев") for p in paragraphs)
    assert any(p.startswith("Исковые требования") for p in paragraphs)
    assert "представителя истца – Орлов Олег Олегович" in "\n".join(paragraphs)
