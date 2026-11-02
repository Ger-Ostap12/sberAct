
"""Взаимозамена затрагивает только первоначальные акты и сохраняет роли судей."""

from copy import deepcopy
from pathlib import Path

import pytest
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from document_generator import DocumentGenerator
from judge_substitution import (
    FOOTER, INTRO, apply_judge_substitution, is_initial_bankruptcy_template, substitution_error,
)

ROOT = Path(__file__).resolve().parents[2] / "Templates"
ALL_TEMPLATES = sorted(ROOT.rglob("*.docx"))
INITIAL_TEMPLATES = [p for p in ALL_TEMPLATES if is_initial_bankruptcy_template(p)]


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


def data(**patch):
    result = dict(sourceDocumentType="rtk_application", judgeSubstitutionEnabled="true",
                  judge="Панова К.О.", judgeFullName="Панова Кристина Олеговна",
                  substituteJudge="Тютюник П.Н.", substituteJudgeFullName="Тютюник Павел Николаевич",
                  creditorName="ПАО Сбербанк", courtName="Арбитражный суд Ростовской области",
                  applicantName="Иванов Иван Иванович", debtorName="Иванов Иван Иванович",
                  caseNumber="А53-12345/2026", _judge_substitution_initial=True)
    result.update(patch)
    return result


def text(doc):
    return "\n".join("".join(n.text or "" for n in p.iter(qn("w:t")))
                     for p in doc.element.body.iter(qn("w:p")))


@pytest.mark.parametrize("path", INITIAL_TEMPLATES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_initial_template_supports_substitution_without_changing_other_text(generator, path):
    doc = Document(path)
    before = text(doc)
    request = data()
    original = deepcopy(request)
    assert apply_judge_substitution(doc, request, generator)
    after = text(doc)
    assert after.count(FOOTER) == 1
    assert after.count(INTRO) == 1
    assert after.count("[416]") == before.count("[415]")
    assert after.count("[415]") == 1
    footer = next(p for p in doc.paragraphs if p.text.startswith(FOOTER))
    assert all(r.bold for r in footer.runs)
    without_footer = after.replace(FOOTER + "[415].\n", "").replace("\n" + FOOTER + "[415].", "")
    assert without_footer.replace(INTRO, "ознакомившись").replace("[416]", "[415]") == before
    assert request == original
    xml = doc.element.xml
    assert not apply_judge_substitution(doc, request, generator)
    assert doc.element.xml == xml


@pytest.mark.parametrize("path", ALL_TEMPLATES, ids=lambda p: str(p.relative_to(ROOT)))
def test_disabled_mode_preserves_every_template(generator, path):
    doc = Document(path)
    before = doc.element.xml
    assert not apply_judge_substitution(doc, data(judgeSubstitutionEnabled="false"), generator)
    assert doc.element.xml == before


@pytest.mark.parametrize("kind", ("mortgage", "intermediate", "final"))
def test_enabled_mode_does_not_change_other_documents(generator, kind):
    doc = Document()
    doc.add_paragraph("Арбитражный суд в составе судьи [415],")
    doc.add_paragraph("ознакомившись с заявлением")
    doc.add_paragraph("Судья [415]")
    before = doc.element.xml
    assert not apply_judge_substitution(doc, data(_judge_substitution_initial=False), generator)
    assert doc.element.xml == before


def test_declension_roles_tables_and_electronic_signature(generator):
    doc = Document()
    doc.add_paragraph("Арбитражный суд в составе судьи [415],")
    p = doc.add_paragraph()
    p.add_run("ознако"); p.add_run("мившись с заявлением [989]")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Судья"
    table.cell(0, 1).text = "[415]"
    doc.add_paragraph("Кому выдана [415]")
    request = data()
    generator.replace_document_data(doc, request)
    result = text(doc)
    assert "в составе судьи Тютюника П.Н." in result
    assert FOOTER + "Пановой К.О." in result
    assert table.cell(0, 1).text == "Тютюник П.Н."
    assert "Кому выдана Тютюник П.Н." in result
    assert "[415]" not in result and "[416]" not in result
    assert request["judge"] == "Панова К.О."
    children = list(doc.element.body)
    footer = next(p for p in doc.paragraphs if p.text.startswith(FOOTER))
    assert children.index(footer._p) + 1 == children.index(table._tbl)
    assert footer.paragraph_format.keep_with_next is True
    assert all(run.bold and run.font.size.pt == 11 for run in footer.runs)


@pytest.mark.parametrize("patch", [{"judge":""}, {"substituteJudge":""}, {"judgeSubstitutionEnabled":"wrong"}])
def test_invalid_input_fails_before_any_files(generator, monkeypatch, patch):
    saved = []
    monkeypatch.setattr(DocxDocument, "save", lambda *args: saved.append(args))
    result = generator.generate("physical_realization", data(**patch))
    assert not result["success"] and result["error"]
    assert not saved


def test_missing_signature_fails_clearly(generator):
    doc = Document()
    doc.add_paragraph("ознакомившись с заявлением")
    with pytest.raises(ValueError, match="подпись"):
        apply_judge_substitution(doc, data(), generator)


def test_fields_input_and_mortgage_isolation():
    assert not substitution_error({"fields":data()})
    assert substitution_error({"fields":data(substituteJudge="")})
    assert not substitution_error(data(sourceDocumentType="mortgage_claim", substituteJudge=""))
    assert not is_initial_bankruptcy_template(ROOT/"Ипотека"/"Определение о принятии.docx")
    assert not is_initial_bankruptcy_template(ROOT/"Банкротство"/"Первоначальные"/"продление БД Инициирование.docx")


def test_mixed_api_packet_does_not_swap_the_main_judge_globally(generator, tmp_path, monkeypatch):
    templates = {}
    for key, name in (("acceptance","Определение о принятии.docx"),
                      ("postponement","Общее отложение.docx"),("final_realization","Решение реализация.docx")):
        path = tmp_path/"Банкротство"/name
        path.parent.mkdir(exist_ok=True)
        doc = Document()
        doc.add_paragraph("Арбитражный суд в составе судьи [415],")
        doc.add_paragraph("ознакомившись с заявлением [989]")
        doc.add_paragraph("Судья [415]")
        doc.save(path)
        templates[key] = dict(path=path,name=key,order=len(templates)+1)
    monkeypatch.setattr(generator,"_map_selected_acts_to_templates",lambda *args:(templates,[]))
    monkeypatch.setattr(generator,"generated_dir",tmp_path)
    monkeypatch.setattr(generator,"_save_document_meta",lambda *args:None)
    saved = {}
    monkeypatch.setattr(DocxDocument,"save",lambda doc,path:saved.__setitem__(str(path),doc))
    request = data(selectedActsIds="acceptance_definition,intermediate_postponement,final_realization")
    result = generator.generate("physical_realization",request)
    assert result["success"] and result["count"] == 3,result
    for key,entry in result["documents"].items():
        rendered = text(saved[entry["file_path"]])
        if key=="acceptance":
            assert INTRO in rendered and "Тютюник" in rendered and FOOTER+"Пановой" in rendered
        else:
            assert INTRO not in rendered and FOOTER not in rendered and "Тютюник" not in rendered
            assert "Пановой" in rendered
    assert request["judge"] == "Панова К.О."


def test_live_bankruptcy_tree_packet_applies_substitution_only_to_initial_acts(generator, tmp_path, monkeypatch):
    request = data(selectedApplicationKind="rtk", selectedEntityType="individual",
                   selectedCollateralOption="no_collateral",
                   selectedActsIds="acceptance_definition,acceptance_after_no_motion,acceptance_no_motion_other,intermediate_postponement",
                   obligations=[], fields={})
    monkeypatch.setattr(generator,"generated_dir",tmp_path)
    monkeypatch.setattr(generator,"_save_document_meta",lambda *args:None)
    saved = {}
    monkeypatch.setattr(DocxDocument,"save",lambda doc,path:saved.__setitem__(str(path),doc))
    result=generator.generate("rtk_single_obligation",request)
    assert result["success"] and result["count"]==4,result
    for kind,item in result["documents"].items():
        output=text(saved[item["file_path"]])
        if kind=="postponement":
            assert FOOTER not in output and INTRO not in output and "Тютюник" not in output
        else:
            assert INTRO in output and FOOTER+"Пановой К.О." in output and "Тютюник" in output
            footer=next(p for p in saved[item["file_path"]].paragraphs if p.text.startswith(FOOTER))
            assert all(r.bold for r in footer.runs)
    assert request["judge"]=="Панова К.О."
