"""Общие правила рода и склонения ФИО для анализатора и генератора."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

# Падежи pymorphy: gent=род., datv=дат., ablt=твор., accs=вин., loct=предл.
_KNOWN_SURNAME_SUFFIXES = ("ов", "ев", "ёв", "ин", "ын", "ий", "ый", "ский", "цкий")

# Базовая форма фамилии (муж., им.п.) -> окончание для целевого падежа.
# Ключ — пара (мужской_суффикс, падеж, род). Значение — окончание после усечения суффикса.
_SURNAME_ENDINGS = {
    # -ов/-ев/-ёв
    "ов": {
        "gent": {"masc": "ова", "femn": "овой"},
        "datv": {"masc": "ову", "femn": "овой"},
        "ablt": {"masc": "овым", "femn": "овой"},
        "accs": {"masc": "ова", "femn": "ову"},
        "loct": {"masc": "ове", "femn": "овой"},
    },
    "ев": {
        "gent": {"masc": "ева", "femn": "евой"},
        "datv": {"masc": "еву", "femn": "евой"},
        "ablt": {"masc": "евым", "femn": "евой"},
        "accs": {"masc": "ева", "femn": "еву"},
        "loct": {"masc": "еве", "femn": "евой"},
    },
    "ёв": {
        "gent": {"masc": "ёва", "femn": "ёвой"},
        "datv": {"masc": "ёву", "femn": "ёвой"},
        "ablt": {"masc": "ёвым", "femn": "ёвой"},
        "accs": {"masc": "ёва", "femn": "ёву"},
        "loct": {"masc": "ёве", "femn": "ёвой"},
    },
    # -ин/-ын
    "ин": {
        "gent": {"masc": "ина", "femn": "иной"},
        "datv": {"masc": "ину", "femn": "иной"},
        "ablt": {"masc": "иным", "femn": "иной"},
        "accs": {"masc": "ина", "femn": "ину"},
        "loct": {"masc": "ине", "femn": "иной"},
    },
    "ын": {
        "gent": {"masc": "ына", "femn": "ыной"},
        "datv": {"masc": "ыну", "femn": "ыной"},
        "ablt": {"masc": "ыным", "femn": "ыной"},
        "accs": {"masc": "ына", "femn": "ыну"},
        "loct": {"masc": "ыне", "femn": "ыной"},
    },
}
# Прилагательные фамилии (-ий/-ый/-ский/-цкий), только мужской род; женский -ая/-ой.
_ADJ_SURNAME = {
    "ский": {
        "masc": {"gent": "ского", "datv": "скому", "ablt": "ским", "accs": "ского", "loct": "ском"},
        "femn": {"gent": "ской", "datv": "ской", "ablt": "ской", "accs": "скую", "loct": "ской"},
    },
    "цкий": {
        "masc": {"gent": "цкого", "datv": "цкому", "ablt": "цким", "accs": "цкого", "loct": "цком"},
        "femn": {"gent": "цкой", "datv": "цкой", "ablt": "цкой", "accs": "цкую", "loct": "цкой"},
    },
    "ий": {"masc": {"gent": "ого", "datv": "ому", "ablt": "им", "accs": "ого", "loct": "ом"}},
    "ый": {"masc": {"gent": "ого", "datv": "ому", "ablt": "ым", "accs": "ого", "loct": "ом"}},
}


def match_original_case(original: str, new_value: str) -> str:
    """Сохранить регистр исходного слова (КАПС/Title/lower)."""
    if original.isupper():
        return new_value.upper()
    if original.istitle():
        return new_value.capitalize()
    return new_value


# Иностранные имена, для которых словарь даёт разбор другого слова.
_INDECLINABLE_NAMES = {
    "ваче": "masc",
    "андре": "masc",
    "гарри": "masc",
    "генри": "masc",
    "гаяне": "femn",
    "нелли": "femn",
    "этери": "femn",
}
_INITIALS_RE = re.compile(r"^(?:[А-ЯЁ]\.){1,3}$")
_NAME_PARTICLES = {"оглы", "улы", "кызы"}


@lru_cache(maxsize=1)
def get_name_morph():
    """Общий ленивый словарь; отсутствие зависимости не прерывает генерацию."""
    try:
        from pymorphy3 import MorphAnalyzer

        return MorphAnalyzer()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Словарь ФИО недоступен: %s", exc)
        return None


def _nominative_parses(morph, token):
    if morph is None:
        return []
    return [p for p in morph.parse(token) if "nomn" in p.tag and "sing" in p.tag and "plur" not in p.tag]


def detect_gender(tokens: list[str], morph=None) -> Optional[str]:
    """Род по отчеству, известному имени и однозначной форме фамилии."""
    low = [t.lower().strip(".") for t in tokens if t.strip(".")]
    if len(low) >= 3:
        if low[-1].endswith(("вич", "ич")) or low[-1] in {"оглы", "улы"}:
            return "masc"
        if low[-1].endswith(("вна", "чна")) or low[-1] == "кызы":
            return "femn"
    if len(low) < 2:
        return None
    if low[1] in _INDECLINABLE_NAMES:
        return _INDECLINABLE_NAMES[low[1]]
    morph = morph if morph is not None else get_name_morph()
    names = [p for part in low[1].split("-") for p in _nominative_parses(morph, part) if p.is_known and "Name" in p.tag]
    genders = {p.tag.gender for p in names if p.tag.gender in {"masc", "femn"}}
    if len(genders) == 1:
        return genders.pop()
    if names:
        return None
    if low[0].endswith(("ова", "ева", "ёва", "ина", "ына", "ская", "цкая")):
        return "femn"
    if low[0].endswith(("ов", "ев", "ёв", "ин", "ын", "ский", "цкий", "ый")):
        return "masc"
    return None


def _manual_surname(surname: str, case: str, gender: Optional[str]) -> Optional[str]:
    """Ручное склонение фамилии по суффиксу. None — если правило не подошло."""
    low = surname.lower()
    # Прилагательные фамилии
    for suf in ("ский", "цкий", "ий", "ый"):
        if low.endswith(suf):
            g = gender or "masc"
            table = _ADJ_SURNAME[suf].get(g) or _ADJ_SURNAME[suf].get("masc")
            if table and case in table:
                return surname[: -len(suf)] + table[case]
            return None
    # -ов/-ев/-ёв/-ин/-ын
    for suf in ("ов", "ев", "ёв", "ин", "ын"):
        if low.endswith(suf):
            g = gender or "masc"
            ending = _SURNAME_ENDINGS[suf][case][g]
            return surname[: -len(suf)] + ending
    return None


_PERSONAL_TAGS = ("Name", "Patr", "Surn")

# Токен ФИО: слово с заглавной (или инициал), допускается двойная часть через дефис.
_FIO_TOKEN_RE = re.compile(r"^[А-ЯЁ][А-Яа-яЁё]*(?:-[А-ЯЁ][А-Яа-яЁё]*)*\.?$")


def looks_like_fio(tokens: list[str]) -> bool:
    """Форма отдельного ФИО; проза и названия организаций обрабатываются отдельно."""
    return 2 <= len(tokens) <= 4 and all(_FIO_TOKEN_RE.match(t) for t in tokens)


def _given_name_parse(morph, token: str, gender: Optional[str]):
    """Не превращаем неизвестное имя в падежную форму созвучного слова."""
    if token.lower() in _INDECLINABLE_NAMES or token.lower() in _NAME_PARTICLES:
        return None
    nominatives = [p for p in _nominative_parses(morph, token) if not gender or p.tag.gender in {gender, None}]
    personal = [p for p in nominatives if any(role in p.tag for role in _PERSONAL_TAGS)]
    candidates = personal or [p for p in nominatives if p.tag.POS == "NOUN"]
    genders = {p.tag.gender for p in candidates if p.tag.gender in {"masc", "femn"}}
    if not gender and len(genders) > 1:
        return None
    return next(iter(candidates), None)


def inflect_given_name(morph, token: str, case: str, gender: Optional[str], strict: bool = True) -> str:
    """Просклонять имя или отчество. Неопознанное слово возвращается как есть.

    `strict=False` — прежнее поведение (первый разбор по весу). Нужно для строк,
    которые ФИО не являются: см. looks_like_fio.
    """
    if not token or case == "nomn" or morph is None:
        return token
    if "-" in token:
        return "-".join(inflect_given_name(morph, часть, case, gender, strict) for часть in token.split("-"))

    if strict:
        разбор = _given_name_parse(morph, token, gender)
    else:
        разборы = morph.parse(token)
        разбор = разборы[0] if разборы else None
    if разбор is None:
        if strict and gender == "masc" and re.fullmatch(r"[А-Яа-яЁё]+[бвгджзклмнпрстфхцчшщ]", token):
            if all("UNKN" in p.tag for p in morph.parse(token)):
                endings = {"gent": "а", "datv": "у", "accs": "а", "ablt": "ом", "loct": "е"}
                return token + endings.get(case, "")
        return token
    граммемы = {case, "sing"} if strict else {case}
    if case == "accs" and ("anim" in разбор.tag or not strict):
        граммемы.add("anim")
    склонённое = разбор.inflect(граммемы)
    if not склонённое or (strict and "plur" in склонённое.tag):
        return token
    return match_original_case(token, склонённое.word)


def inflect_surname(morph, surname: str, case: str, gender: Optional[str]) -> str:
    """Фамилия в единственном числе с учётом пола и словарного типа склонения."""
    if not surname or case == "nomn":
        return surname

    # Двойная фамилия через дефис — склоняем каждую часть отдельно.
    if "-" in surname:
        return "-".join(inflect_surname(morph, part, case, gender) for part in surname.split("-"))

    manual = _manual_surname(surname, case, gender)
    if manual is not None:
        return match_original_case(surname, manual)

    if gender == "femn" and surname[-1].lower() not in "ая":
        return surname

    if morph is None:
        return surname

    raw = morph.parse(surname)
    personal_nom = [
        p
        for p in raw
        if "Surn" in p.tag and "nomn" in p.tag and "sing" in p.tag and (not gender or p.tag.gender == gender)
    ]
    if not personal_nom and gender:
        oblique = [p for p in raw if p.is_known and "Surn" in p.tag and "sing" in p.tag and p.tag.gender == gender]
        bases = {p.normal_form for p in oblique}
        if len(bases) == 1 and surname.lower() not in bases:
            base = match_original_case(surname, bases.pop())
            return inflect_surname(morph, base, case, gender)
    if surname.lower().endswith(("ко", "их", "ых", "о", "е", "ё", "и", "у", "ю", "э")):
        return surname
    parses = [
        p
        for p in _nominative_parses(morph, surname)
        if not gender or p.tag.gender in {gender, None} or (surname[-1].lower() in "ая" and p.tag.POS == "NOUN")
    ]
    personal = [p for p in parses if "Surn" in p.tag]
    parses = personal or parses
    if not gender and len({p.tag.gender for p in parses if p.tag.gender}) > 1:
        return surname
    grammemes = {case, "sing"}
    if gender:
        grammemes.add(gender)
    if case == "accs":
        grammemes.add("anim")
    for parsed in parses:
        # Фамилии-существительные «Песня», «Галета» сохраняют свой тип склонения.
        target = {case, "sing"} if "Surn" not in parsed.tag and surname[-1].lower() in "ая" else grammemes
        inflected = parsed.inflect(target)
        if inflected and "plur" not in inflected.tag:
            return match_original_case(surname, inflected.word)
    return surname


_REPRESENTED_PERSON_RE = re.compile(r"^(.+?)\s+(в\s+лице\s+законного\s+представителя)\s+(.+)$", re.IGNORECASE)


def is_recognized_person(morph, value: str) -> bool:
    """Морфологическое подтверждение отделяет ФИО от похожей на него прозы."""
    represented = _REPRESENTED_PERSON_RE.fullmatch(value)
    if represented:
        return is_recognized_person(morph, represented.group(1)) and is_recognized_person(morph, represented.group(3))
    tokens = value.split()
    if not looks_like_fio(tokens):
        return False
    if len(tokens) > 1 and tokens[1].lower() in _INDECLINABLE_NAMES:
        return True
    if any("Name" in p.tag or "Patr" in p.tag for token in tokens[1:] for p in morph.parse(token)):
        return True
    return any("Surn" in p.tag and "sing" in p.tag for p in morph.parse(tokens[0]))


def inflect_full_name(morph, value: str, case: str, gender: Optional[str] = None) -> str:
    """Общий путь ФИО для анализа, генератора и должностных лиц."""
    represented = _REPRESENTED_PERSON_RE.fullmatch(value)
    if represented:
        child, link, guardian = represented.groups()
        guardian_is_genitive = morph is not None and any(
            "Patr" in p.tag and p.tag.case == "gent" and "sing" in p.tag for p in morph.parse(guardian.split()[-1])
        )
        guardian_text = guardian if guardian_is_genitive else inflect_full_name(morph, guardian, "gent")
        return inflect_full_name(morph, child, case) + " " + link.lower() + " " + guardian_text
    tokens = value.split()
    if not tokens or case == "nomn" or morph is None:
        return value
    gender = gender or detect_gender(tokens, morph)
    if gender is None:
        return value
    result = [inflect_surname(morph, tokens[0], case, gender)]
    for token in tokens[1:]:
        result.append(token if _INITIALS_RE.fullmatch(token) else inflect_given_name(morph, token, case, gender))
    return " ".join(result)


_DEBTOR_CASE_FIELDS = {
    "applicantNameGenitive": "gent",
    "applicantNameDative": "datv",
    "applicantNameInstrumental": "ablt",
    "applicantNameAccusative": "accs",
}
_PERSON_PREFIX_RE = re.compile(r"^(?:(?:глава\s+)?кфх\s+(?:ип\s+)?|ип\s+)", re.IGNORECASE)


def refresh_debtor_case_forms(fields: dict, morph) -> list[str]:
    """Пересчитываем падежи из исходного ФИО, не из чужого сырого захвата."""
    from org_normalizer import is_org_name

    if str(fields.get("entityType") or "").lower() == "legal":
        return []
    source = str(fields.get("applicantName") or "").strip()
    names = [_PERSON_PREFIX_RE.sub("", n.strip()) for n in source.split(",")]
    if not names or any(
        is_org_name(n) or not (looks_like_fio(n.split()) or _REPRESENTED_PERSON_RE.fullmatch(n)) for n in names
    ):
        return []
    if morph is not None and not all(is_recognized_person(morph, n) for n in names):
        return [f"ФИО «{source}» не подтверждено словарём; проверьте исходное имя и падежи."]
    warnings = []
    if morph is None:
        warnings.append("Словарь склонения ФИО недоступен; проверьте падежи должника.")
    for name in names:
        represented = _REPRESENTED_PERSON_RE.fullmatch(name)
        person = represented.group(1) if represented else name
        if morph is not None and detect_gender(person.split(), morph) is None:
            warnings.append(f"Не удалось однозначно определить род ФИО «{name}»; проверьте падежи.")
    for field, case in _DEBTOR_CASE_FIELDS.items():
        old_prefix = _PERSON_PREFIX_RE.match(str(fields.get(field) or ""))
        prefix = old_prefix.group() if old_prefix and _PERSON_PREFIX_RE.match(source) else ""
        fields[field] = prefix + ", ".join(inflect_full_name(morph, n, case) for n in names)
    if str(fields.get("mortgageDebtorName") or "").strip() == source:
        fields["mortgageDebtorNameDative"] = fields["applicantNameDative"]
    return warnings
