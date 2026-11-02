"""Разбор перенесённых названий в явно обозначенных блоках сторон."""

import re
from dataclasses import dataclass

from label_synonyms import (
    CREDITOR_HEADER_LABELS,
    DEBTOR_HEADER_LABELS,
    MANAGER_HEADER_LABELS,
    THIRD_PARTY_HEADER_LABELS,
    labels_alternation,
)
from org_normalizer import abbreviate_org_name, is_org_name


@dataclass(frozen=True)
class PartyNameCandidate:
    name: str
    source: str
    confidence: str = "high"


_PARTY_LABELS = (
    CREDITOR_HEADER_LABELS
    + DEBTOR_HEADER_LABELS
    + MANAGER_HEADER_LABELS
    + THIRD_PARTY_HEADER_LABELS
    + [
        "Ответчики",
        "Представитель",
        "Представитель взыскателя по доверенности",
        "Представитель истца",
        "Представитель кредитора",
        "Наследник",
        "Наследники",
    ]
)
_BOUNDARY_RE = re.compile(
    rf"^[ \t]*(?:{labels_alternation(_PARTY_LABELS)})[ \t]*:"
    r"|^[ \t]*(?:Представител\w*|Генеральный\s+директор|Директор|Руководител\w*|По делу|Заявление|Исковое заявление|ПРОШУ)\b",
    re.IGNORECASE | re.MULTILINE,
)
_REQUISITES_RE = re.compile(
    r"\b(?:ИНН|КПП|ОГРН\w*|СНИЛС|паспорт|адрес|телефон|тел\.|"
    r"юридическ\w*\s+адрес|почтов\w*|место\s+нахождения|"
    r"дата\s+(?:рождения|государственн\w*\s+регистрации)|"
    r"электронн\w*\s+почта|e-?mail|www\.)\b"
    r"|(?<!\d)\d{6}(?!\d)",
    re.IGNORECASE,
)
_LEGAL_FORM_ONLY_RE = re.compile(
    r"(?:ООО|АО|ПАО|НАО|ОАО|ЗАО|"
    r"общество\s+с\s+ограниченной\s+ответственностью|"
    r"(?:(?:не)?публичное\s+)?акционерное\s+общество)",
    re.IGNORECASE,
)


def labelled_blocks(text, labels):
    """Не переходим через соседнюю роль, даже если значение метки пусто."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    pattern = re.compile(
        rf"^[ \t]*(?P<label>{labels_alternation(labels)})[ \t]*:[ \t]*",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in pattern.finditer(text):
        block = text[match.end() :]
        boundary = _BOUNDARY_RE.search(block)
        if boundary:
            block = block[: boundary.start()]
        yield match.group("label"), block.strip()


def explicit_creditor_name(text):
    """Собирает название с переносами до реквизитов, сохраняя название в кавычках."""
    for label, block in labelled_blocks(text, CREDITOR_HEADER_LABELS):
        name = _REQUISITES_RE.split(block, maxsplit=1)[0].strip(" ,;\n")
        if not name or not is_org_name(name):
            continue
        name = re.sub(r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)", "-", name)
        name = re.sub(r"\s+", " ", name)
        short = re.search(
            r"\(\s*сокращ[её]н\w*\s+(?:наименование\s+)?(?P<name>[^)]+)\)",
            name,
            re.IGNORECASE,
        )
        if short and is_org_name(short.group("name")):
            name = short.group("name").strip()
        else:
            # Пояснения после названия не являются его частью; ОПФ сохраняется.
            paren = re.search(r"\s+\(([^)]*)\)", name)
            if paren and not _LEGAL_FORM_ONLY_RE.fullmatch(paren.group(1)):
                name = name[: paren.start()]
        # После закрытого названия остаётся только ОПФ, но не адрес без метки.
        quoted = re.search(r'[«"][^»"]+[»"]', name)
        if quoted:
            tail = name[quoted.end() :].strip()
            legal_form = re.fullmatch(r"\(([^)]*)\)", tail)
            if not (legal_form and _LEGAL_FORM_ONLY_RE.fullmatch(legal_form.group(1))):
                name = name[: quoted.end()]
        name = name.rstrip(" ,;(")
        if len(name) > 200 or _LEGAL_FORM_ONLY_RE.fullmatch(name.strip(" ,;")):
            continue
        # Без кавычек многострочная проза не должна становиться названием.
        if not any(q in name for q in '«»"') and len(name.split()) > 12:
            continue
        return PartyNameCandidate(name.strip(" ,;"), f"header:{label}")
    return None


def completes_creditor_name(current, candidate):
    """Дополняем только тот же префикс, а не заменяем установленного кредитора."""
    if not current:
        return True
    current = re.sub(r"\s+", " ", current).strip(" ,;")
    full = re.sub(r"\s+", " ", candidate).strip(" ,;")
    if _LEGAL_FORM_ONLY_RE.fullmatch(current):
        return True
    return full.casefold().startswith(current.casefold()) or abbreviate_org_name(full).casefold().startswith(
        abbreviate_org_name(current).casefold()
    )
