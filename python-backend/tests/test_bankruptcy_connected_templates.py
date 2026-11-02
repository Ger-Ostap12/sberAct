"""Новые ветки банкротства: свой файл, корректная роль и отсутствие ошибки 500."""

import asyncio
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import zipfile

from docx import Document
from docx.document import Document as DocxDocument
import httpx
import pytest

from document_generator import DocumentGenerator

ROOT = Path(__file__).resolve().parents[2]


def request_data(entity="ip", kind="self", **patch):
    result = {
        "selectedApplicationKind": kind, "selectedEntityType": entity,
        "selectedCollateralOption": "no_collateral",
        "sourceDocumentType": "initiation_legal" if entity in ("legal", "kfh") else "initiation_physical",
        "entityType": "legal" if entity == "legal" else "individual",
        "isKfh": entity == "kfh",
        "applicantName": "Ароян Ваче Рушани", "debtorName": "Ароян Ваче Рушани",
        "kfhHeadName": "Ароян Ваче Рушани" if entity == "kfh" else "",
        "creditorName": "ООО «Кредитор»", "creditorOgrn": "1026100000001",
        "creditorInn": "6100000001", "inn": "610000000001",
        "ogrnip": "304610000000001", "ogrn": "1026100000002",
        "birthDate": "01.01.1980", "date": "03.11.2026", "judge": "Панова К.О.",
        "caseNumber": "А53-1234/2026", "applicantAddress": "г. Ростов-на-Дону",
        "totalDebt": "100000", "stateDuty": "1000", "obligations": [],
    }
    result.update(patch)
    return result


def resolve(gen, data, ids):
    return gen._map_selected_acts_to_templates(
        ",".join(ids), data["selectedEntityType"], data["selectedCollateralOption"], data,
    )


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


@pytest.mark.parametrize("entity", ["individual", "ip", "legal", "kfh"])
def test_self_initial_intermediate_and_final_use_own_tree(generator, entity):
    ids = ["acceptance_definition", "acceptance_after_no_motion", "acceptance_no_motion_other",
           "acceptance_no_motion_no_duty", "intermediate_postponement",
           "intermediate_postponement_third_party", "intermediate_return_general",
           "intermediate_return_no_duty", "intermediate_extend_no_motion"]
    ids += ["final_observation"] if entity in ("legal", "kfh") else ["final_realization", "final_restructuring"]
    templates, missing = resolve(generator, request_data(entity), ids)
    assert missing == []
    assert len(templates) == len(ids)
    own = {"individual": "ФЛ", "ip": "ИП", "legal": "ЮЛ", "kfh": "КФХ"}[entity]
    for item in templates.values():
        parts = item["path"].relative_to(ROOT / "Templates").parts
        assert parts[:4] == ("Банкротство", "Инициирование", own, "Самобанкрот")
        assert item["path"].is_file()


@pytest.mark.parametrize("entity", ["legal", "kfh"])
@pytest.mark.parametrize("status", ["", "liquidation", "absent"])
@pytest.mark.parametrize("collateral", ["no_collateral", "collateral"])
def test_new_legal_creditor_templates_remain_in_their_branch(generator, entity, status, collateral):
    data = request_data(entity, "other", selectedDebtorStatus=status, selectedCollateralOption=collateral)
    ids = ["acceptance_definition", "acceptance_after_no_motion", "acceptance_no_motion_other",
           "intermediate_postponement", "intermediate_postponement_third_party",
           "intermediate_return_general", "intermediate_return_no_duty", "intermediate_extend_no_motion"]
    ids.append("final_competition" if status else "final_observation")
    templates, missing = resolve(generator, data, ids)
    assert not missing, (missing, data.get("_unresolvedReasons"))
    assert len(templates) == len(ids)
    for item in templates.values():
        path = item["path"]
        assert "Инициирование" in path.parts and "Кредиторы" in path.parts
        assert ("ЮЛ" if entity == "legal" else "КФХ") in path.parts
        assert ("Залог" if collateral == "collateral" else "Незалог") in path.parts


@pytest.mark.parametrize("entity", ["individual", "ip", "legal", "kfh"])
@pytest.mark.parametrize("creditor", ["ООО «Кредитор»", "ФНС России в лице УФНС России по Ростовской области"])
def test_extend_simplified_is_available_only_for_rtk(generator, entity, creditor):
    data = request_data(entity, "rtk", creditorName=creditor)
    templates, missing = resolve(generator, data, ["intermediate_extend_simplified"])
    assert not missing
    assert "Включение в РТК" in templates["extend_simplified"]["path"].parts
    data["selectedApplicationKind"] = "other"
    templates, missing = resolve(generator, data, ["intermediate_extend_simplified"])
    assert templates == {}
    assert missing == ["intermediate_extend_simplified"]
    assert "только" in data["_unresolvedReasons"]["intermediate_extend_simplified"]


def test_missing_ip_creditor_does_not_borrow_physical_or_self_act(generator):
    data = request_data(kind="other")
    templates, missing = resolve(generator, data, ["acceptance_definition", "final_realization"])
    assert not templates
    assert missing == ["acceptance_definition", "final_realization"]


@pytest.mark.parametrize("entity,expected", [("ip", 3), ("legal", 2), ("kfh", 2)])
def test_standard_initiation_without_selected_ids_uses_new_tree(generator, entity, expected):
    data = request_data(entity)
    templates, _ = generator._resolve_standard_templates(
        data, "initiation_legal" if entity in ("legal", "kfh") else "initiation_physical", "", "", entity == "kfh",
    )
    assert len(templates) == expected
    assert not data["_default_unresolved_act_ids"]
    assert all("Самобанкрот" in item["path"].parts for item in templates.values())


@pytest.mark.parametrize("entity", ["individual", "ip", "legal", "kfh"])
def test_generated_self_package_is_valid_docx(generator, monkeypatch, entity):
    saved = []
    original_save = DocxDocument.save

    def capture(document, path):
        stream = BytesIO()
        original_save(document, stream)
        with zipfile.ZipFile(stream) as archive:
            assert archive.testzip() is None
        saved.append(document)

    monkeypatch.setattr(DocxDocument, "save", capture)
    monkeypatch.setattr(generator, "_save_document_meta", lambda *args: None)
    ids = ["acceptance_definition", "final_observation" if entity in ("legal", "kfh") else "final_realization"]
    data = request_data(entity, selectedActsIds=",".join(ids))
    if entity == "legal":
        data.update(applicantName="Сельскохозяйственный кооператив «Дон»",
                    debtorName="Сельскохозяйственный кооператив «Дон»")
    result = generator.generate("initiation_physical", data)
    assert result["success"], result
    assert result["count"] == len(saved) == 2
    text = "\n".join(p.text for doc in saved for p in doc.paragraphs)
    assert ("Сельскохозяйственного кооператива" if entity == "legal" else "Арояна Ваче Рушани") in text
    if entity == "kfh":
        assert "ОГРНИП 304610000000001" in text
        assert "ОГРН 304610000000001" not in text


def test_organization_cases_are_not_flattened_by_full_generation(generator):
    doc = Document()
    doc.add_paragraph("Должник [2]; о признании [2.1]; к [2.2]; с [2.3]; Признать [2.4].")
    name = "Сельскохозяйственный кооператив «Дон»"
    data = request_data("legal", applicantName=name, debtorName=name)
    before = deepcopy(data)
    generator.replace_document_data(doc, data)
    result = doc.paragraphs[0].text
    for expected in ["Сельскохозяйственного кооператива", "Сельскохозяйственному кооперативу",
                     "Сельскохозяйственным кооперативом", "Сельскохозяйственный кооператив"]:
        assert expected in result
    assert result.count("«Дон»") == 5
    assert data == before


def test_ip_api_generates_self_and_reports_missing_creditor_as_422(generator, monkeypatch):
    import main
    monkeypatch.setattr(main, "document_generator", generator)
    monkeypatch.setattr(DocxDocument, "save", lambda *args: None)
    monkeypatch.setattr(generator, "_save_document_meta", lambda *args: None)

    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            for kind, expected in [("self", 200), ("other", 422)]:
                data = request_data(kind=kind, selectedActsIds="acceptance_definition,final_realization")
                response = await client.post("/generate-document", json={"template_type": "initiation_physical", "data": data})
                assert response.status_code == expected, response.text
    asyncio.run(call())


@pytest.mark.parametrize("entity", ["individual", "ip"])
def test_missing_fns_initiation_does_not_borrow_creditor_or_rtk(generator, entity):
    data = request_data(entity, "other", creditorName="ФНС России")
    ids = ["acceptance_definition", "final_realization"]
    templates, missing = resolve(generator, data, ids)
    assert templates == {}
    assert missing == ids
    assert all("ФНС" in reason for reason in data["_unresolvedReasons"].values())


@pytest.mark.parametrize("entity", ["legal", "kfh"])
@pytest.mark.parametrize("act", ["acceptance_definition", "acceptance_after_no_motion", "acceptance_no_motion_other"])
def test_fns_initial_names_tax_authority_not_self_applicant(generator, entity, act):
    data = request_data(entity, "other", creditorName="ФНС России в лице УФНС России по Ростовской области")
    templates, missing = resolve(generator, data, [act])
    assert not missing
    doc = Document(next(iter(templates.values()))["path"])
    source = "\n".join(p.text for p in doc.paragraphs)
    assert "ФНС России в лице [989]" in source
    assert "ознакомившись с ФНС" not in source
    assert "установил: должник обратился" not in source
    generator.replace_document_data(doc, data)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "ФНС России в лице УФНС России по Ростовской области" in text
    assert "ФНС России в лице ФНС" not in text


@pytest.mark.parametrize("entity", ["legal", "kfh"])
def test_new_templates_do_not_hardcode_llc_before_full_debtor_name(entity):
    import re
    from lxml import etree
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    folder = ROOT / "Templates/Банкротство/Инициирование" / {"legal": "ЮЛ", "kfh": "КФХ"}[entity]
    checked = 0
    for path in folder.rglob("*.docx"):
        with zipfile.ZipFile(path) as archive:
            for part in archive.namelist():
                if not part.startswith("word/") or not part.endswith(".xml"):
                    continue
                tree = etree.fromstring(archive.read(part))
                for paragraph in tree.xpath("//w:p", namespaces=ns):
                    text = "".join(paragraph.xpath(".//w:t/text()", namespaces=ns))
                    assert not re.search(
                        r'обществ\w*\s+(?:с\s+)?ограниченной\s+ответственностью\s*[«"]?\s*(?:Глав\w*\s+КФХ\s+)?\[2',
                        text, re.I,
                    ), (path, text)
                    if entity == "kfh":
                        assert not re.search(r"\bОГРН\s*\[3\]", text, re.I), (path, text)
                    checked += 1
    assert checked > 200


@pytest.mark.parametrize("template,source", [("mortgage", "mortgage_claim"), ("legal_collection", "legal_collection"),
                                         ("ip_collection", "ip_collection")])
def test_default_initiation_never_intercepts_civil_acts(generator, template, source):
    assert generator._initiation_default_templates(
        request_data(kind="other", sourceDocumentType=source), template,
    ) is None


def test_collateral_duty_name_can_include_bankruptcy_word_and_is_not_duplicated(generator):
    import bankruptcy_tree
    assert bankruptcy_tree.file_role("Определение БД не гп банкротство залог.docx") == "no_motion_no_duty_collateral"
    data = request_data("individual", "other", selectedCollateralOption="collateral")
    ids = ["acceptance_no_motion_no_duty", "acceptance_no_motion_no_duty_collateral"]
    templates, missing = resolve(generator, data, ids)
    assert not missing
    assert len(templates) == 1
    assert "Залог" in next(iter(templates.values()))["path"].parts


def test_ambiguous_primary_role_is_not_hidden_by_duty_alias(tmp_path):
    import bankruptcy_tree
    folder = tmp_path / "Банкротство/Инициирование/ИП/Кредиторы/Незалог/Первоначальные"
    folder.mkdir(parents=True)
    for name in ("Определение БД нет ГП первый.docx", "Определение БД нет ГП второй.docx",
                 "Определение БД нет ГП залог.docx"):
        (folder / name).touch()
    result = bankruptcy_tree.resolve(
        tmp_path, entity="ip", branch=bankruptcy_tree.BRANCH_INITIATION,
        role="no_motion_no_duty",
    )
    assert result.path is None
    assert result.reason.startswith("неоднозначно")


@pytest.mark.parametrize("entity", ["individual", "ip", "legal", "kfh"])
def test_initiation_short_text_reports_missing_without_borrowing_rtk(generator, entity):
    data = request_data(entity, "self", selectedShortText="true")
    templates, missing = resolve(generator, data, ["acceptance_definition"])
    assert list(templates) == ["acceptance"]
    assert missing == ["short_text"]
    assert data["_unresolvedReasons"]["short_text"]
    assert "Инициирование" in templates["acceptance"]["path"].parts


def test_ogrnip_always_uses_own_marker_not_birth_date_in_actual_templates():
    import re
    from lxml import etree
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    checked = 0
    for path in (ROOT / "Templates/Банкротство").rglob("*.docx"):
        with zipfile.ZipFile(path) as archive:
            for part in archive.namelist():
                if not part.startswith("word/") or not part.endswith(".xml"):
                    continue
                tree = etree.fromstring(archive.read(part))
                for paragraph in tree.xpath("//w:p", namespaces=ns):
                    text = "".join(paragraph.xpath(".//w:t/text()", namespaces=ns))
                    assert not re.search(r"\bОГРНИП\s*\[3\]", text, re.I), (path, text)
                    checked += 1
    assert checked > 1000


def test_kfh_debtor_is_registered_as_entrepreneur_not_legal_company():
    import re
    for path in (ROOT / "Templates/Банкротство/Инициирование/КФХ").rglob("*.docx"):
        for paragraph in Document(path).paragraphs:
            text = paragraph.text
            if "[2" in text:
                assert "является действующим юридическим лицом" not in text, (path, text)
                assert "реестра юридических лиц" not in text, (path, text)
                assert not re.search(r"\bООО\s+Глав", text), (path, text)


def test_kfh_title_and_person_marker_always_have_same_case():
    import re
    forms = {"глава": "[2]", "главы": "[2.1]", "главе": "[2.2]", "главой": "[2.3]", "главу": "[2.4]"}
    checked = 0
    for path in (ROOT / "Templates/Банкротство").rglob("*.docx"):
        if "КФХ" not in path.parts:
            continue
        for paragraph in Document(path).paragraphs:
            for match in re.finditer(r"(Глава|Главы|Главе|Главой|Главу)\s+КФХ\s*(\[2(?:\.[1-4])?\])", paragraph.text, re.I):
                assert match.group(2) == forms[match.group(1).lower()], (path, paragraph.text)
                checked += 1
    assert checked > 100
