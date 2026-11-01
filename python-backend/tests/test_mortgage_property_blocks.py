"""Реквизиты каждого объекта остаются в его блоке и в исходном порядке."""

from copy import deepcopy

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from mortgage_properties import expand_property_blocks
from test_civil_mortgage_generation import mortgage_data


@pytest.fixture
def generator(tmp_path):
    gen = DocumentGenerator()
    gen.generated_dir = tmp_path
    return gen


def block(doc, name="MortgageProperties_01", identifier="10"):
    paragraphs = [doc.add_paragraph("Объект: [1221]."),
                  doc.add_paragraph("Адрес: [1227]. Площадь: [1233]. Кадастр: [1226]."),
                  doc.add_paragraph("ЕГРН: [1229] от [1230]."),
                  doc.add_paragraph("Оценка: [1224]. Цена: [1225]. Отчёт: [1223].")]
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:name"), name)
    start.set(qn("w:id"), identifier)
    paragraphs[0]._p.insert(0, start)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), identifier)
    paragraphs[-1]._p.append(end)
    return paragraphs


def properties(count=2):
    return [dict(description=f"Объект {i}", address=f"Улица {i}, дом {i}",
                 cadastralNumber=f"61:44:0000:{i}", egrnRecord=f"ЕГРН-{i}",
                 egrnRecordDate=f"2020-01-{i:02d}", area=str(i*100),
                 value=str(i*1000), startingPrice=str(i*800), appraisalReport=f"Оценка-{i}")
            for i in range(1, count+1)]


def apply(generator, doc, items, source="mortgage_claim", nested=False):
    data = {"sourceDocumentType": source}
    if nested:
        data["fields"] = {"mortgageProperties": items}
    else:
        data["mortgageProperties"] = items
    before = deepcopy(data)
    result = expand_property_blocks(doc, data, generator._replace_span_in_paragraph,
                                    generator._format_amount_value, generator._normalize_date_format)
    assert data == before
    return result


@pytest.mark.parametrize("count", [1, 2, 3, 8])
@pytest.mark.parametrize("nested", [False, True])
def test_every_object_has_own_complete_requisites_in_order(generator, count, nested):
    doc = Document()
    doc.add_paragraph("Начало [1229].")
    block(doc)
    doc.add_paragraph("Конец.")
    assert apply(generator, doc, properties(count), nested=nested) == 1
    assert doc.paragraphs[0].text == "Начало [1229]."
    assert doc.paragraphs[-1].text == "Конец."
    for i in range(1, count+1):
        actual = [p.text for p in doc.paragraphs[1+(i-1)*4:1+i*4]]
        assert actual == [
            f"Объект: Объект {i}.",
            f"Адрес: Улица {i}, дом {i}. Площадь: {i*100}. Кадастр: 61:44:0000:{i}.",
            f"ЕГРН: ЕГРН-{i} от {i:02d}.01.2020.",
            f"Оценка: {i} 000. Цена: {i*800:,}. Отчёт: Оценка-{i}.".replace(",", " "),
        ]
    assert not list(doc.element.iter(qn("w:bookmarkStart")))
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))


def test_missing_land_record_never_borrows_house_record(generator):
    doc = Document()
    block(doc)
    items = properties()
    items[1].pop("egrnRecord")
    items[1].pop("egrnRecordDate")
    items[1]["startingPrice"] = "0"
    apply(generator, doc, items)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert text.count("ЕГРН-1") == 1
    assert "ЕГРН: ****** от ******." in text
    assert "Цена: 0." in text


def test_multiple_blocks_reverse_order_and_equal_descriptions(generator):
    doc = Document()
    block(doc)
    doc.add_paragraph("Разделитель")
    block(doc, "MortgageProperties_02", "11")
    items = list(reversed(properties()))
    items[0]["description"] = items[1]["description"] = "Имущество"
    assert apply(generator, doc, items) == 2
    actual = "\n".join(p.text for p in doc.paragraphs)
    assert actual.count("Имущество") == 4
    assert actual.count("ЕГРН-1") == actual.count("ЕГРН-2") == 2
    for part in actual.split("Разделитель"):
        assert part.index("ЕГРН-2") < part.index("ЕГРН-1")


def test_split_marker_styles_and_paragraph_settings_survive(generator):
    doc = Document()
    paragraphs = block(doc)
    p = paragraphs[0]
    p.clear()
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:name"), "MortgageProperties_01")
    start.set(qn("w:id"), "10")
    p._p.append(start)
    p.add_run("Объект: ").italic = True
    p.add_run("[12").bold = True
    p.add_run("21]").bold = True
    p.paragraph_format.keep_with_next = True
    p._p.set(qn("w14:paraId"), "12345678")
    apply(generator, doc, properties())
    for index in [0, 4]:
        p = doc.paragraphs[index]
        assert p.text == f"Объект: Объект {index//4+1}"
        assert any(r.bold and "Объект " in r.text for r in p.runs)
        assert any(r.italic and r.text == "Объект: " for r in p.runs)
        assert p.paragraph_format.keep_with_next
        assert p._p.get(qn("w14:paraId")) is None


@pytest.mark.parametrize("items", [None, [], [{}], "объект", [None], [1]])
def test_invalid_objects_rejected_without_document_mutation(generator, items):
    doc = Document()
    block(doc)
    before = doc.element.xml
    with pytest.raises(ValueError, match="предмет|Предмет|ипотеки"):
        apply(generator, doc, items)
    assert doc.element.xml == before


@pytest.mark.parametrize("damage", ["end", "partial", "nested", "duplicate"])
def test_bad_later_block_rejected_before_any_replacement(generator, damage):
    doc = Document()
    block(doc)
    second = block(doc, "MortgageProperties_02", "11")
    if damage == "end":
        second[-1]._p.remove(second[-1]._p.find(qn("w:bookmarkEnd")))
    elif damage == "partial":
        second[0]._p.insert(0, OxmlElement("w:r"))
        second[0]._p[0].append(OxmlElement("w:t"))
        second[0]._p[0][0].text = "За пределами"
    elif damage == "nested":
        other = OxmlElement("w:bookmarkStart")
        other.set(qn("w:name"), "Other")
        other.set(qn("w:id"), "90")
        second[1]._p.append(other)
    else:
        second[0]._p.find(qn("w:bookmarkStart")).set(qn("w:name"), "MortgageProperties_01")
    before = doc.element.xml
    with pytest.raises(ValueError):
        apply(generator, doc, properties())
    assert doc.element.xml == before


def test_blank_cards_are_ignored_without_losing_order(generator):
    doc = Document()
    block(doc)
    apply(generator, doc, [{}, properties()[1], {"id":"empty"}, properties()[0]])
    assert doc.paragraphs[0].text == "Объект: Объект 2."
    assert doc.paragraphs[4].text == "Объект: Объект 1."


def test_old_templates_and_other_document_types_unchanged(generator):
    doc = Document()
    doc.add_paragraph("Старый шаблон [1229]")
    before = doc.element.xml
    assert apply(generator, doc, "invalid") == 0
    assert doc.element.xml == before
    block(doc)
    before = doc.element.xml
    assert apply(generator, doc, properties(), source="rtk_application") == 0
    assert doc.element.xml == before


@pytest.mark.parametrize("kind", ["civil", "ddu", "military"])
def test_real_generate_uses_each_object_before_global_mapping(generator, tmp_path, monkeypatch, kind):
    doc = Document()
    doc.add_paragraph("Дело № [1]. Кредитор [989].")
    block(doc)
    path = tmp_path / "objects.docx"
    doc.save(path)
    monkeypatch.setattr(generator, "_get_mortgage_templates",
                        lambda data: {"property_review": {"name":"Объекты", "path":path, "order":1}})
    data = mortgage_data()
    data.update(selectedMortgageKind=kind, mortgageKind=kind, mortgageProperties=properties())
    data["fields"].update(selectedMortgageKind=kind)
    result = generator.generate("mortgage", data)
    assert result["success"], result
    output = Document(result["documents"]["property_review"]["file_path"])
    text = "\n".join(p.text for p in output.paragraphs)
    assert text.index("ЕГРН-1") < text.index("ЕГРН-2")
    assert "ЕГРН-1 от 01.01.2020" in text and "ЕГРН-2 от 02.01.2020" in text
    assert "Ипотека" not in text
    assert not list(output.element.iter(qn("w:bookmarkStart")))


@pytest.mark.parametrize("explicit", ["", None, "80"])
def test_area_from_description_is_only_a_fallback(generator, explicit):
    doc = Document()
    block(doc)
    item = properties(1)[0]
    item.update(description="Жилой дом общей площадью 42,7 кв. м.", area=explicit)
    apply(generator, doc, [item])
    assert ("Площадь: 80." if explicit else "Площадь: 42,7 кв. м.") in doc.paragraphs[1].text
