"""Контекст шаблона задаёт падеж ФИО, включая женские формы."""

from copy import deepcopy
from pathlib import Path
import re
import zipfile

from docx import Document
from lxml import etree
import pytest

from document_generator import DocumentGenerator

ROOT = Path(__file__).resolve().parents[2]
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
MARKER = r"(?P<marker>\[2(?:\.[1-4])?\])"
CONTEXTS = [
    (
        "recognition",
        re.compile(
            r"о\s+признании\s+(?:несостоятельным\s*\(банкротом\)\s+)?"
            r"(?:(?:индивидуального\s+предпринимателя\s+Главы\s+КФХ|Главы\s+КФХ\s+индивидуального\s+предпринимателя)\s+)?"
            + MARKER,
            re.I,
        ),
        "[2.1]",
        "gent",
    ),
    ("recognize", re.compile(r"\bПризнать\s+" + MARKER, re.I), "[2.4]", "accs"),
    (
        "subject",
        re.compile(r"\[989\]\s+и\s+(?:ИП\s+)?" + MARKER + r"(?=\s*\(далее\s*[–-]\s*должник\)\s+заключили)", re.I),
        "[2]",
        "nomn",
    ),
    ("to_entrepreneur", re.compile(r"\bк\s+индивидуальному\s+предпринимателю\s*" + MARKER, re.I), "[2.2]", "datv"),
    (
        "kfh",
        re.compile(
            r'(?:банкротстве\)[\s«")]*|в\s+отношении\s*[«"]?\s*|взысканию\s+с\s*[«"]?\s*|должника\s*[«"]?\s*)(?P<title>Глав[аы])\s+КФХ\s*'
            + MARKER,
            re.I,
        ),
        "[2.1]",
        "gent",
    ),
]


def contexts():
    result = []
    for path in sorted((ROOT / "Templates").rglob("*.docx")):
        with zipfile.ZipFile(path) as archive:
            for part in archive.namelist():
                if not part.startswith("word/") or not part.endswith(".xml"):
                    continue
                tree = etree.fromstring(archive.read(part))
                for paragraph in tree.xpath("//w:p", namespaces=NS):
                    text = "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))
                    for role, pattern, expected, case in CONTEXTS:
                        for match in pattern.finditer(text):
                            result.append(
                                (
                                    path,
                                    role,
                                    text,
                                    match.group("marker"),
                                    expected,
                                    case,
                                    match.groupdict().get("title"),
                                )
                            )
    return result


ROWS = contexts()
PHRASES = sorted({(role, text, expected, case) for _, role, text, _, expected, case, _ in ROWS})


@pytest.mark.parametrize(
    "path,role,text,actual,expected,case,title",
    ROWS,
    ids=[str(row[0].relative_to(ROOT)) + ":" + row[1] for row in ROWS],
)
def test_actual_template_marker_matches_grammatical_context(path, role, text, actual, expected, case, title):
    assert actual == expected, (path, text)
    if role == "kfh":
        assert title == "Главы", (path, text)


def test_inventory_covers_each_grammar_and_original_recognition_problem():
    assert {row[1] for row in ROWS} == {row[0] for row in CONTEXTS}
    recognition_files = {row[0] for row in ROWS if row[1] == "recognition"}
    assert len(recognition_files) >= 77


@pytest.fixture(scope="module")
def generator():
    return DocumentGenerator()


NAMES = [
    (
        "Петрова Анна Ивановна",
        {
            "nomn": "Петрова Анна Ивановна",
            "gent": "Петровой Анны Ивановны",
            "datv": "Петровой Анне Ивановне",
            "accs": "Петрову Анну Ивановну",
        },
    ),
    (
        "Иванов Иван Иванович",
        {
            "nomn": "Иванов Иван Иванович",
            "gent": "Иванова Ивана Ивановича",
            "datv": "Иванову Ивану Ивановичу",
            "accs": "Иванова Ивана Ивановича",
        },
    ),
    (
        "Ароян Ваче Рушани",
        {
            "nomn": "Ароян Ваче Рушани",
            "gent": "Арояна Ваче Рушани",
            "datv": "Арояну Ваче Рушани",
            "accs": "Арояна Ваче Рушани",
        },
    ),
]


@pytest.mark.parametrize("role,text,expected,case", PHRASES)
@pytest.mark.parametrize("name,forms", NAMES)
def test_real_template_phrase_generates_required_person_case(generator, role, text, expected, case, name, forms):
    # Другие упоминания ФИО не должны маскировать ошибку целевого маркера.
    target = CONTEXTS[[row[0] for row in CONTEXTS].index(role)][1].search(text)
    assert target
    left, right = target.span("marker")
    phrase = text[:left] + "PERSON_CASE_PROBE" + text[right:]
    phrase = re.sub(r"\[2(?:\.[1-4])?\]", "ДРУГОЕ_УПОМИНАНИЕ", phrase)
    phrase = phrase.replace("PERSON_CASE_PROBE", expected)
    data = {
        "sourceDocumentType": "rtk_application",
        "entityType": "individual",
        "applicantName": name,
        "debtorName": name,
        "applicantNameDative": forms["datv"],
        "creditorName": "ООО «Кредитор»",
        "caseNumber": "А53-1234/2026",
        "inn": "123456789012",
        "birthDate": "01.01.1980",
        "applicantAddress": "г. Ростов-на-Дону",
        "totalDebt": "1000",
        "stateDuty": "100",
        "obligations": [{"contractNumber": "1", "contractDate": "01.01.2020", "obligationType": "Кредитный договор"}],
    }
    if role == "kfh":
        data.update(isKfh=True, kfhHeadName=name)
    before = deepcopy(data)
    doc = Document()
    doc.add_paragraph(phrase)
    generator.replace_document_data(doc, data)
    result = " ".join(" ".join(p.text for p in doc.paragraphs).split())
    assert forms[case] in result
    assert data == before


@pytest.mark.parametrize("substitution", [False, True])
def test_live_initial_packet_uses_genitive_with_or_without_substitution(generator, monkeypatch, tmp_path, substitution):
    from docx.document import Document as DocumentClass

    saved = {}
    monkeypatch.setattr(generator, "generated_dir", tmp_path)
    monkeypatch.setattr(generator, "_save_document_meta", lambda *args: None)
    monkeypatch.setattr(DocumentClass, "save", lambda doc, path: saved.__setitem__(str(path), doc))
    ids = [
        "acceptance_definition",
        "acceptance_after_no_motion",
        "acceptance_no_motion_other",
        "acceptance_no_motion_no_duty",
        "intermediate_return_general",
    ]
    data = {
        "applicantName": "Петрова Анна Ивановна",
        "debtorName": "Петрова Анна Ивановна",
        "applicantNameDative": "Петровой Анне Ивановне",
        "entityType": "individual",
        "selectedEntityType": "individual",
        "selectedApplicationKind": "other",
        "selectedCollateralOption": "no_collateral",
        "selectedActsIds": ",".join(ids),
        "sourceDocumentType": "bankruptcy_application",
        "judge": "Панова К.О.",
        "judgeFullName": "Панова Ксения Олеговна",
    }
    if substitution:
        data.update(
            judgeSubstitutionEnabled="true",
            substituteJudge="Тютюник П.Н.",
            substituteJudgeFullName="Тютюник Павел Николаевич",
        )
    result = generator.generate("bankruptcy_application", data)
    assert result["success"], result
    assert result["count"] == 5
    direct_recognition = 0
    for info in result["documents"].values():
        text = " ".join(p.text for p in saved[info["file_path"]].paragraphs)
        assert "Петровой Анны Ивановны" in text, info
        direct_recognition += bool(re.search(r"о\s+признании\s+Петровой Анны Ивановны", text))
    # В Б/Д без госпошлины ФИО стоит после «в рамках дела о банкротстве».
    assert direct_recognition == 4


def test_recognition_noun_and_recognize_verb_use_different_female_cases(generator):
    data = {
        "applicantName": "Петрова Анна Ивановна",
        "entityType": "individual",
        "sourceDocumentType": "rtk_application",
    }
    doc = Document()
    doc.add_paragraph("О признании [2.1] несостоятельной.")
    doc.add_paragraph("Признать [2.4] несостоятельной.")
    generator.replace_document_data(doc, data)
    assert "Петровой Анны Ивановны" in doc.paragraphs[0].text
    assert "Петрову Анну Ивановну" in doc.paragraphs[1].text
