"""Обычная ипотека: исход иска, границы распоряжений и неустойка."""

from copy import deepcopy

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from document_generator import DocumentGenerator


CASES = [(representatives, solidary)
         for representatives in (False, True) for solidary in (False, True)]
OUTCOMES = ("full", "partial", "deny")
COMMANDS = ("Расторгнуть кредитный договор", "Взыскать",
            "Обратить взыскание", "Определить способ реализации")


def mortgage_data(representatives=False, solidary=False, outcome="full", penalty="50"):
    """Синтетическое дело с заполненными реквизитами всех пяти документов."""
    fields = {
        "selectedMortgageKind": "civil",
        "solidaryLiability": "true" if solidary else "",
        "claimResolution": outcome,
        "caseNumber": "2-1234/2026",
        "caseUid1304": "61RS0001-01-2026-000001-01",
        "courtName": "Октябрьский районный суд г. Ростова-на-Дону",
        "mortgageCourtNameGenitive": "Октябрьского районного суда г. Ростова-на-Дону",
        "courtAddress": "г. Ростов-на-Дону, ул. Тестовая, д. 1",
        "courtEmail": "court@example.test",
        "courtSite": "https://court.example.test",
        "higherCourt": "Ростовский областной суд",
        "higherCourtAddress": "г. Ростов-на-Дону, ул. Судебная, д. 2",
        "higherCourtPostalAddress": "г. Ростов-на-Дону, ул. Судебная, д. 2",
        "date": "01.11.2026",
        "courtDecisionDate": "01.11.2026",
        "noticeDate": "02.11.2026",
        "judge": "Петров Пётр Петрович",
        "authorName": "Сидоров Сергей Сергеевич",
        "authorRole": "секретарь",
        "creditorName": "ПАО Сбербанк",
        "creditorInn": "7707083893",
        "creditorOgrn": "1027700132195",
        "creditorAddress": "г. Москва, ул. Вавилова, д. 19",
        "creditorPostalAddress": "г. Москва, ул. Вавилова, д. 19",
        "creditorBranchAddress1443": "г. Ростов-на-Дону, ул. Банковская, д. 3",
        "applicantName": "Иванов Иван Иванович",
        "applicantNameGenitive": "Иванова Ивана Ивановича",
        "debtorName": "Иванов Иван Иванович",
        "mortgageDebtorName": "Иванов Иван Иванович",
        "inn": "616100000001",
        "birthDate": "01.01.1980",
        "applicantAddress": "г. Ростов-на-Дону, ул. Тестовая, д. 10",
        "contractNumber": "TEST-CREDIT-77",
        "contractDate": "01.01.2020",
        "creditAmount": "100000",
        "creditTermMonths": "120",
        "creditInterestRate": "10",
        "creditPenaltyRate": "1",
        "debtSnapshotDate": "01.10.2026",
        "mortgagePeriodStart120": "01.09.2026",
        "mortgagePeriodEnd121": "01.10.2026",
        "principalDebt": "1000",
        "loanDebt": "1000",
        "interest": "200",
        "forfeit": penalty,
        "forfeit15": penalty,
        "stateDuty16": "10",
        "stateDuty": "10",
        "totalDebt": "1250",
        "mortgageCollateralDescription1221": "квартира",
        "mortgageStartingPrice1225": "200000",
        "mortgageCollateralValue1224": "250000",
        "courtHearingDateTime99": "15.11.2026 10:30",
        "objectionsDeadline18": "10.11.2026",
        "representativeName": "Орлов Олег Олегович" if representatives else "",
        "respondentRepresentativeName": "Смирнов Семён Семёнович" if representatives else "",
        "representativePoaFrom": "01.01.2026",
        "representativePoaTo": "31.12.2026",
    }
    people = [
        {"name": "Иванов Иван Иванович", "inn": "616100000001",
         "birthDate": "01.01.1980", "address": fields["applicantAddress"],
         "passportSeries": "6000", "passportNumber": "123456"},
        {"name": "Петрова Анна Петровна", "inn": "616100000002",
         "birthDate": "02.02.1982", "address": fields["applicantAddress"],
         "passportSeries": "6001", "passportNumber": "234567"},
    ]
    properties = [{
        "description": "квартира", "address": "г. Ростов-на-Дону, ул. Тестовая, д. 10, кв. 1",
        "cadastralNumber": "61:44:0000000:100", "area": "50",
        "egrnRecord": "61:44:0000000:100-61/001/2020-1",
        "egrnRecordDate": "01.01.2020",
    }]
    return {
        "sourceDocumentType": "mortgage_claim", "mortgageKind": "civil",
        "entityType": "individual", "fields": fields, **fields,
        "debtors": people if representatives or solidary else people[:1],
        "mortgageProperties": properties,
    }


@pytest.fixture
def generator(tmp_path):
    gen = DocumentGenerator()
    gen.generated_dir = tmp_path
    return gen


def text(doc):
    return "\n".join(p.text for p in doc.paragraphs)


def xml(doc):
    return doc.element.xml


def scope(**changes):
    data = {
        "sourceDocumentType": "mortgage_claim",
        "_current_doc_type": "mortgage_decision",
        "selectedMortgageKind": "civil",
        "claimResolution": "full",
    }
    data.update(changes)
    return data


def bookmarked_doc(end_in_body=False, outcome_marker="[888]", extra_paragraph=False):
    doc = Document()
    doc.add_paragraph("Исковые требования — " + outcome_marker + ".")
    commands = [
        "Расторгнуть кредитный договор № [110] от [100].",
        "Взыскать [13] — основной долг, [14] — проценты, [15] — неустойка.",
        "Обратить взыскание на имущество [1221].",
        "Определить способ реализации имущества за [1225].",
    ]
    paragraphs = [doc.add_paragraph(s) for s in commands]
    if extra_paragraph:
        paragraphs.append(doc.add_paragraph("Посторонний абзац."))
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), "77")
    start.set(qn("w:name"), "MortgageAwards")
    paragraphs[0]._p.insert(0, start)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), "77")
    if end_in_body:
        paragraphs[-1]._p.addnext(end)
    else:
        paragraphs[-1]._p.append(end)
    doc.add_paragraph("[889]")
    doc.add_paragraph("Решение может быть обжаловано.")
    doc.add_paragraph("Судья [415]")
    return doc


@pytest.mark.parametrize("representatives,solidary", CASES)
@pytest.mark.parametrize("outcome", OUTCOMES)
def test_real_packages(generator, representatives, solidary, outcome):
    data = mortgage_data(representatives, solidary, outcome)
    result = generator.generate("mortgage", deepcopy(data))
    assert result["success"], result
    assert result["count"] == 5
    assert not result.get("warnings")
    assert set(result["documents"]) == {
        "mortgage_summons", "mortgage_acceptance_short",
        "mortgage_acceptance_long", "mortgage_notice", "mortgage_decision",
    }
    doc = Document(result["documents"]["mortgage_decision"]["file_path"])
    output = text(doc)
    expected = {"full": "удовлетворить", "partial": "удовлетворить частично",
                "deny": "— отказать."}[outcome]
    assert expected in output
    assert "Судья" in output and "Решение может быть обжаловано" in output
    assert ("В удовлетворении исковых требований" if outcome == "deny" else "Исковые требования") in output
    assert all((command in output) == (outcome != "deny") for command in COMMANDS)
    assert ("остальной части" in output) == (outcome == "partial")
    assert ("в солидарном порядке" in output) == (solidary and outcome != "deny")
    assert "[888]" not in output and "[889]" not in output and "[15]" not in output
    assert "MortgageAwards" not in xml(doc)
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))
    assert data["caseUid1304"] in output
    assert "в Ростовский областной суд через" in output
    assert "руб.." not in output and "в виде путем" not in output
    if outcome == "deny":
        assert "отказать в удовлетворении" not in output
    if solidary and not representatives:
        introductory = next(p.text for p in doc.paragraphs if "рассмотрев" in p.text)
        assert "Иванову Ивану Ивановичу, Петровой Анне Петровне" in introductory
        if outcome != "deny":
            termination = next(p.text for p in doc.paragraphs if p.text.startswith("Расторгнуть"))
            assert "Ивановым Иваном Ивановичем, Петровой Анной Петровной" in termination
    if outcome != "deny":
        assert "TEST-CREDIT-77" in output and "неустойка" in output
        assert "200" in output and "1 000" in output


@pytest.mark.parametrize("value", ["", "0", "0,00", "0 руб.", 0, None])
def test_empty_penalty_preserves_neighbours_and_styles(generator, value):
    doc = Document()
    p = doc.add_paragraph()
    first = p.add_run("Взыскать [13] — основной долг")
    first.bold = True
    middle = p.add_run(", [14] — проценты")
    middle.italic = True
    for piece in (", [1", "5] — неустойка"):
        p.add_run(piece).underline = True
    last = p.add_run(", а также расходы [16], всего [1360].")
    last.font.name = "Arial"
    data = scope(forfeit=value, forfeit15=value)
    generator._apply_penalty_removal(doc, data)
    assert p.text == ("Взыскать [13] — основной долг, [14] — проценты"
                      ", а также расходы [16], всего [1360].")
    assert next(r for r in p.runs if "основной долг" in r.text).bold is True
    assert next(r for r in p.runs if "проценты" in r.text).italic is True
    assert next(r for r in p.runs if "расходы" in r.text).font.name == "Arial"


def test_penalty_uses_same_alias_as_substitution(generator):
    doc = Document()
    p = doc.add_paragraph("[13] — долг, [14] — проценты, [15] — неустойка.")
    data = scope(forfeit="0", forfeit15="50")
    generator._apply_penalty_removal(doc, data)
    assert "неустойка" not in p.text


def test_nonzero_penalty_does_not_change_xml(generator):
    doc = Document()
    p = doc.add_paragraph("[13] — долг, [14] — проценты, [15] — неустойка.")
    p.runs[0].bold = True
    before = xml(doc)
    generator._apply_penalty_removal(doc, scope(forfeit="50"))
    assert xml(doc) == before


@pytest.mark.parametrize("outcome", OUTCOMES)
@pytest.mark.parametrize("end_in_body", [False, True])
def test_bookmark_boundaries_and_adjacent_text(generator, outcome, end_in_body):
    doc = bookmarked_doc(end_in_body)
    generator._apply_civil_mortgage_awards(doc, scope(claimResolution=outcome))
    output = text(doc)
    expected = ("В удовлетворении исковых требований" if outcome == "deny" else "Исковые требования")
    assert expected + " — [888]." in output
    assert "Решение может быть обжаловано." in output and "Судья [415]" in output
    assert all((command in output) == (outcome != "deny") for command in COMMANDS)
    assert ("[889]" in output) == (outcome == "partial")
    assert not list(doc.element.iter(qn("w:bookmarkStart")))
    assert not list(doc.element.iter(qn("w:bookmarkEnd")))


@pytest.mark.parametrize("kind,doc_type,source", [
    ("ddu", "mortgage_decision", "mortgage_claim"),
    ("military", "mortgage_decision", "mortgage_claim"),
    ("civil", "mortgage_notice", "mortgage_claim"),
    ("civil", "mortgage_summons", "mortgage_claim"),
    ("civil", "mortgage_acceptance_short", "mortgage_claim"),
    ("civil", "mortgage_acceptance_long", "mortgage_claim"),
    ("civil", "mortgage_decision", "rtk_application"),
])
@pytest.mark.parametrize("outcome", OUTCOMES)
def test_other_documents_untouched(generator, kind, doc_type, source, outcome):
    doc = bookmarked_doc()
    before = xml(doc)
    generator._apply_civil_mortgage_awards(
        doc, scope(selectedMortgageKind=kind, _current_doc_type=doc_type,
                   sourceDocumentType=source, claimResolution=outcome))
    assert xml(doc) == before


@pytest.mark.parametrize("kind", ["ddu", "military"])
def test_zero_penalty_keeps_other_mortgage_behaviour(generator, kind):
    doc = Document()
    doc.add_paragraph("[13] — долг, [14] — проценты, [15] — неустойка.")
    before = xml(doc)
    generator._apply_penalty_removal(doc, scope(selectedMortgageKind=kind, forfeit="0"))
    assert xml(doc) == before


@pytest.mark.parametrize("problem", [
    "missing_start", "missing_end", "duplicate_start", "reversed",
    "extra_paragraph", "partial_start", "partial_end", "includes_889",
])
def test_bad_bookmark_is_rejected_before_changes(generator, problem):
    doc = bookmarked_doc(extra_paragraph=problem == "extra_paragraph")
    start = next(doc.element.iter(qn("w:bookmarkStart")))
    end = next(doc.element.iter(qn("w:bookmarkEnd")))
    if problem == "missing_start":
        start.getparent().remove(start)
    elif problem == "missing_end":
        end.getparent().remove(end)
    elif problem == "duplicate_start":
        start.addnext(deepcopy(start))
    elif problem == "reversed":
        start.getparent().remove(start)
        end.addnext(start)
    elif problem == "partial_start":
        first_run = start.getparent().find(qn("w:r"))
        start.getparent().remove(start)
        first_run.addnext(start)
    elif problem == "partial_end":
        end.getparent().remove(end)
        doc.paragraphs[4]._p.insert(0, end)
    elif problem == "includes_889":
        end.getparent().remove(end)
        doc.paragraphs[5]._p.append(end)
    before = xml(doc)
    with pytest.raises(ValueError, match="MortgageAwards"):
        generator._apply_civil_mortgage_awards(doc, scope(claimResolution="deny"))
    assert xml(doc) == before


@pytest.mark.parametrize("outcome", ["full", "deny"])
def test_non_partial_clears_stale_denial(generator, outcome):
    data = scope(claimResolution=outcome, claimPartialDenialText="СТАРЫЙ ОТКАЗ")
    generator._apply_claim_resolution(data)
    assert not data.get("claimPartialDenialText")


def test_user_selection_overrides_detected_kind(generator):
    doc = bookmarked_doc()
    generator._apply_civil_mortgage_awards(
        doc, scope(selectedMortgageKind="civil", mortgageKind="ddu", claimResolution="deny"))
    assert "Взыскать" not in text(doc)


def test_nested_kind_respects_other_document_scope(generator):
    doc = bookmarked_doc()
    before = xml(doc)
    data = scope(claimResolution="deny")
    data.pop("selectedMortgageKind")
    data["fields"] = {"selectedMortgageKind": "ddu"}
    generator._apply_civil_mortgage_awards(doc, data)
    assert xml(doc) == before


@pytest.mark.parametrize("count", [2, 3, 5])
def test_all_civil_debtors_reach_dative_and_instrumental(generator, count):
    data = mortgage_data(solidary=True)
    names = ["Иванов Иван Иванович", "Петрова Анна Петровна",
             "Сидоров Сергей Сергеевич", "Орлова Ольга Олеговна",
             "Смирнов Семён Семёнович"][:count]
    data["debtors"] = [{"name": name} for name in names] + [{}, None]
    data["_current_doc_type"] = "mortgage_decision"
    mapping = generator._apply_debtor_name_field_mapping(data, generator._base_field_mapping(), True)
    assert data["mortgageDebtorNameDative"] == ", ".join(
        generator._decline_person_name(name, "datv") for name in names)
    assert data["applicantNameInstrumental"] == ", ".join(
        generator._decline_person_name(name, "ablt") for name in names)
    assert mapping["mortgageDebtorNameDative"] == "2.2"
    assert mapping["applicantNameInstrumental"] == "2.3"


@pytest.mark.parametrize("kind,doc_type", [
    ("military", "mortgage_decision"),
    ("civil", "mortgage_summons"), ("civil", "mortgage_notice"),
    ("civil", "mortgage_acceptance_short"), ("civil", "mortgage_acceptance_long"),
])
def test_other_documents_keep_existing_debtor_cases(generator, kind, doc_type):
    data = mortgage_data(solidary=True)
    data.update(selectedMortgageKind=kind, _current_doc_type=doc_type)
    without_array = deepcopy(data)
    without_array.pop("debtors")
    first_mapping = generator._apply_debtor_name_field_mapping(data, generator._base_field_mapping(), True)
    second_mapping = generator._apply_debtor_name_field_mapping(without_array, generator._base_field_mapping(), True)
    assert first_mapping == second_mapping
    for field in ("mortgageDebtorNameDative", "applicantNameInstrumental"):
        assert data.get(field) == without_array.get(field)


@pytest.mark.parametrize("kind,doc_type,expected", [
    ("civil", "mortgage_decision", "отказать"),
    ("ddu", "mortgage_decision", "отказать"),
    ("military", "mortgage_decision", "отказать в удовлетворении"),
    ("civil", "mortgage_notice", "отказать в удовлетворении"),
])
def test_denial_wording_changes_supported_mortgage_decisions(generator, kind, doc_type, expected):
    data = scope(selectedMortgageKind=kind, _current_doc_type=doc_type, claimResolution="deny")
    generator._apply_claim_resolution(data)
    assert data["claimResolutionText"] == expected


def test_denial_prefix_preserves_current_run_styles(generator):
    doc = bookmarked_doc()
    paragraph = doc.paragraphs[0]
    paragraph.clear()
    paragraph.add_run("Исковые тре").bold = True
    paragraph.add_run("бования [989] к [2.2]").italic = True
    paragraph.add_run(", [888].")
    generator._apply_civil_mortgage_awards(doc, scope(claimResolution="deny"))
    assert paragraph.text == "В удовлетворении исковых требований [989] к [2.2] — [888]."
    assert next(run for run in paragraph.runs if "В удовлетворении" in run.text).bold
    assert next(run for run in paragraph.runs if "[989]" in run.text).italic
