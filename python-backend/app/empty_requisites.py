"""Удаление незаполненных реквизитов по их маркерам до общей подстановки."""

import re
from difflib import SequenceMatcher

from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.text.paragraph import Paragraph

_OPTIONAL_MARKER_RE = re.compile(r"\[(?:3|4(?:\.1)?|41|990|991|140[4578]\.\d+|52\.\d+)\]")
_EMPTY_VALUES = {"", "none", "null", "не указано", "не указан", "не указана", "-", "—"}
_LABELS = {
    "inn": r"ИНН|идентификационн\w*\s+номер\w*\s+налогоплательщика",
    "ogrn": r"ОГРН(?:ИП)?|основн\w*\s+государственн\w*\s+регистрационн\w*\s+номер(?:\s+индивидуального\s+предпринимателя)?",
    "birth": r"(?:дата|год)\s+рожд(?:ения|\.?)|д\.\s*р\.",
    "series": r"сери[яи]",
    "number": r"номер|№",
}


def empty_value(value):
    text = str(value or "").strip().casefold()
    return text in _EMPTY_VALUES or bool(re.fullmatch(r"\*+", text))


def clean_requisite_text(text, missing, missing_ogrnip=False):
    """Сохраняет заполненные реквизиты и текст вне удаляемого компонента."""
    original = text
    if missing_ogrnip:
        text = re.sub(r"\bОГРНИП\s*:?\s*\[3\]", "", text, flags=re.IGNORECASE)
    for slot in re.findall(r"\[140[78]\.(\d+)\]", original):
        series, number = f"[1407.{slot}]", f"[1408.{slot}]"
        both = series in missing and number in missing
        pair = re.escape(series) + r"\s+" + re.escape(number)
        combined = r"серия\s+и\s+номер\s+документа,\s*удостоверяющего\s+личность\s+" + pair
        if both:
            text = re.sub(combined, "", text, flags=re.IGNORECASE)
            passport = (
                r"паспорт(?:\s+гражданина\s+(?:РФ|Российской\s+Федерации))?\s*[:,]?\s*"
                r"(?:серия\s*:?\s*)?"
                + re.escape(series)
                + r"\s*[,;]?\s*(?:(?:номер|№)\s*:?)?\s*"
                + re.escape(number)
                + r"(?:,\s*выдан\s+\*+(?:,\s*\*+)?(?:,\s*код\s+подразделения\s+\*+)?)?"
            )
            text = re.sub(passport, "", text, flags=re.IGNORECASE)
        elif series in missing or number in missing:
            remaining = number if series in missing else series
            label = "номер" if series in missing else "серия"
            text = re.sub(
                combined,
                label + " документа, удостоверяющего личность " + remaining,
                text,
                flags=re.IGNORECASE,
            )
    for marker in missing:
        token = re.escape(marker)
        text = re.sub(
            rf"(?<!\w)(?:{_LABELS['inn']}|{_LABELS['ogrn']}|{_LABELS['birth']}|"
            rf"{_LABELS['series']}|{_LABELS['number']})\s*[:№]?\s*{token}",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(token + r"\s*(?:(?:года?|г\.)\s*рожд(?:ения|\.)|г\.?\s*р\.)", "", text, flags=re.IGNORECASE)
        text = text.replace(marker, "")
    if text == original:
        return text
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"[ \t  ]*\(\s*[,;:]*\s*\)", "", text)
        text = re.sub(r"(\(|\[)\s*[,;:]\s*", r"\1", text)
        text = re.sub(r"[,;]\s*([)\]])", r"\1", text)
        text = re.sub(r",\s*;|;\s*,", ";", text)
        text = re.sub(r"([,;])\s*[,;]", r"\1", text)
    text = re.sub(r"[ \t  ]+([,.;:)])", r"\1", text)
    text = re.sub(r"(?<=\w)[ \t  ]{2,}(?=\w)", " ", text)
    return text


def remove_empty_requisites(doc, data, mapping, generator):
    values = {}
    for field, number in mapping.items():
        value = data.get(field)
        if not empty_value(value):
            values[number] = value
    roots = [doc.element.body]
    roots.extend(
        relation.target_part.element
        for relation in doc.part.rels.values()
        if not relation.is_external and relation.reltype in (RT.HEADER, RT.FOOTER)
    )
    paragraphs = (Paragraph(element, doc) for root in roots for element in root.iter(qn("w:p")))
    for paragraph in paragraphs:
        text = generator._paragraph_text(paragraph)
        missing = {marker for marker in _OPTIONAL_MARKER_RE.findall(text) if empty_value(values.get(marker[1:-1]))}
        missing_ogrnip = empty_value(data.get("ogrnip")) and bool(
            re.search(r"\bОГРНИП\s*:?\s*\[3\]", text, re.IGNORECASE)
        )
        if not missing and not missing_ogrnip:
            continue
        cleaned = clean_requisite_text(text, missing, missing_ogrnip=missing_ogrnip)
        for operation, start, end, new_start, new_end in reversed(
            SequenceMatcher(None, text, cleaned, autojunk=False).get_opcodes()
        ):
            if operation != "equal":
                generator._replace_span_in_paragraph(paragraph, start, end, cleaned[new_start:new_end])
