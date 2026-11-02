
"""Взаимозамена судьи в первоначальных актах банкротства."""

from pathlib import Path
import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

from bankruptcy_tree import INITIAL_ACT_ROLES, file_role

FOOTER = "Обособленный спор находится в производстве судьи "
INTRO = "ознакомившись в порядке взаимозаменяемости"


def substitution_error(data):
    fields = data.get("fields") or {}
    def pick(key):
        return str(data.get(key) or fields.get(key) or "").strip()
    if pick("documentCategory") == "mortgage" or pick("sourceDocumentType") == "mortgage_claim":
        return ""
    flag = pick("judgeSubstitutionEnabled").lower()
    if flag not in ("", "false", "true"):
        return "Некорректное значение режима взаимозамены судьи"
    if flag != "true":
        return ""
    if not pick("judge"):
        return "Для взаимозамены укажите основного судью"
    if not pick("substituteJudge"):
        return "Укажите судью по взаимозамене"
    return ""


def is_initial_bankruptcy_template(path):
    path = Path(path)
    return ("банкротство" in {part.lower() for part in path.parts}
            and file_role(path.name) in set(INITIAL_ACT_ROLES.values()))


def apply_judge_substitution(doc, data, generator):
    """Изменяет копию первоначального акта до подстановки ФИО."""
    fields = data.get("fields") or {}
    enabled = str(data.get("judgeSubstitutionEnabled") or fields.get("judgeSubstitutionEnabled") or "").lower()
    if enabled != "true" or data.get("_judge_substitution_initial") is not True:
        return False
    error = substitution_error(data)
    if error:
        raise ValueError(error)
    footers = [p for p in doc.paragraphs if p.text.strip().startswith(FOOTER)]
    intros = [p for p in doc.paragraphs if re.search(r"\bознакомившись\b", p.text, re.I)]
    if len(intros) != 1:
        raise ValueError("В первоначальном акте не найдена единственная вводная фраза для взаимозамены")
    if footers:
        if len(footers) == 1 and INTRO in intros[0].text.lower():
            return False
        raise ValueError("В акте некорректно оформлена строка о судье, ведущем спор")
    signatures = []
    for node in doc.element.body:
        text = "".join(n.text or "" for n in node.iter(qn("w:t")))
        if re.search(r"Судья\s*\[415\]", text, re.I):
            signatures.append(node)
    if len(signatures) != 1:
        raise ValueError("В первоначальном акте не найдена единственная подпись судьи для взаимозамены")
    generator._regex_sub_in_paragraphs(
        intros, re.compile(r"\bознакомившись\b", re.I), INTRO,
    )
    generator._replace_placeholder_in_doc(doc, "[415]", "[416]")
    node = OxmlElement("w:p")
    paragraph = Paragraph(node, doc._body)
    paragraph.paragraph_format.space_before = Pt(6)
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(FOOTER + "[415].")
    run.bold = True
    run.font.name = "Times New Roman"
    run.font.size = Pt(11)
    signatures[0].addprevious(node)
    return True


def finalize_judge_substitution(doc, data):
    """Возвращает выделение строки после общих замен, пересобирающих текст абзаца."""
    fields = data.get("fields") or {}
    flag = str(data.get("judgeSubstitutionEnabled") or fields.get("judgeSubstitutionEnabled") or "").lower()
    if flag != "true" or data.get("_judge_substitution_initial") is not True:
        return
    for paragraph in doc.paragraphs:
        if paragraph.text.strip().startswith(FOOTER):
            paragraph.paragraph_format.keep_with_next = True
            for run in paragraph.runs:
                run.bold = True
                run.font.name = "Times New Roman"
                run.font.size = Pt(11)
