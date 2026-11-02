
"""Списки ответчиков обычной резолютивки заполняются из карточек заявления."""

import re


PASSPORT_PERSON = (
    r"\[1401\.\d+\]\s*\(серия и номер документа, удостоверяющего личность\s+"
    r"\[1407\.\d+\]\s+\[1408\.\d+\]\)"
)
PASSPORT_GROUP = re.compile(PASSPORT_PERSON + r"(?:,\s*" + PASSPORT_PERSON + r")*")


def fill_civil_parties(doc, data, generator):
    """Согласует одиночные и нумерованные маркеры с фактическим числом ответчиков."""
    fields = data.get("fields") or {}
    people = data.get("debtors") or fields.get("debtors") or []
    people = [person for person in people if isinstance(person, dict)
              and str(person.get("name") or "").strip()]
    if not people:
        return
    def names(case):
        return ", ".join(generator._decline_person_name(
            generator._capitalize_full_name(person["name"]), case) for person in people)
    details = []
    for person in people:
        name = generator._decline_person_name(generator._capitalize_full_name(person["name"]), "gent")
        series = str(person.get("passportSeries") or "******").strip()
        number = str(person.get("passportNumber") or "******").strip()
        details.append(f"{name} (серия и номер документа, удостоверяющего личность {series} {number})")
    replacements = (
        (re.compile(r"\[1402\.\d+\](?:,\s*\[1402\.\d+\])*|\[2\.2\]"), names("datv")),
        (re.compile(r"\[1409\.\d+\](?:,\s*\[1409\.\d+\])*|\[2\.3\]"), names("ablt")),
        (PASSPORT_GROUP, ", ".join(details)),
        (re.compile(r"\[2\.1\]"), names("gent")),
        (re.compile(r"\[4\]"), ", ".join(str(p.get("inn") or "******").strip() for p in people)),
    )
    for pattern, value in replacements:
        generator._regex_sub_in_paragraphs(doc.paragraphs, pattern, value)
