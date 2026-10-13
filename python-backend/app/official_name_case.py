"""Падежи ФИО судьи и ведущего протокол: шаблон диктует падеж контекстом маркера."""

import logging
import re
from typing import Optional

from morph_utils import detect_gender, inflect_given_name, inflect_surname

try:
    from pymorphy3 import MorphAnalyzer as _MorphAnalyzerCls
except ImportError:  # pragma: no cover
    _MorphAnalyzerCls = None

logger = logging.getLogger(__name__)

_морф = None


def _get_morph():
    """Ленивая загрузка pymorphy3: нужна только фамилиям вне типовых суффиксов."""
    global _морф
    if _морф is None and _MorphAnalyzerCls is not None:
        try:
            _морф = _MorphAnalyzerCls()
        except Exception as exc:
            logger.warning("pymorphy3 не загружен: %s", exc)
    return _морф

# Падеж задаёт слово перед маркером. У судьи это «судьи»/«судьёй»/«Судья»,
# у ведущего протокол — «секретарем»/«помощником» либо «при секретаре».
_СУДЬЯ_ПАДЕЖИ = (
    (re.compile(r"судь[её]й\b", re.IGNORECASE), "ablt"),
    (re.compile(r"судьи\b", re.IGNORECASE), "gent"),
    (re.compile(r"судья\b", re.IGNORECASE), "nomn"),
)
_ВЕДУЩИЙ_ПАДЕЖИ = (
    (re.compile(r"при\s+(?:секретаре|помощнике)\b", re.IGNORECASE), "loct"),
    (re.compile(r"(?:секретар[её]м|помощником)\b", re.IGNORECASE), "ablt"),
)

# Женские фамилии опознаются по окончанию; у остальных род не угадываем.
_ЖЕНСКИЕ_ОКОНЧАНИЯ = ("ова", "ева", "ёва", "ина", "ына", "ская", "цкая", "ая", "яя")
_МУЖСКИЕ_ОКОНЧАНИЯ = ("ов", "ев", "ёв", "ин", "ын", "ский", "цкий", "ий", "ый")

_ИНИЦИАЛ = re.compile(r"^[А-ЯЁ]\.?$")


def _последний(текст: str, образец: re.Pattern) -> int:
    позиция = -1
    for m in образец.finditer(текст):
        позиция = m.start()
    return позиция


def _падеж(левый_контекст: str, правила) -> Optional[str]:
    лучший, где = None, -1
    for образец, падеж in правила:
        поз = _последний(левый_контекст, образец)
        if поз > где:
            лучший, где = падеж, поз
    return лучший


def judge_case(left_context: str) -> str:
    """Падеж ФИО судьи по тексту перед маркером. По умолчанию именительный."""
    return _падеж(left_context or "", _СУДЬЯ_ПАДЕЖИ) or "nomn"


def clerk_case(left_context: str) -> str:
    """Падеж ФИО ведущего протокол. По умолчанию творительный — самая частая форма."""
    return _падеж(left_context or "", _ВЕДУЩИЙ_ПАДЕЖИ) or "ablt"


def gender_from_full_name(full_name: str) -> Optional[str]:
    """Род по полному ФИО: отчество отвечает на этот вопрос без догадок.

    Сокращённая запись не годится: в «Жигало А.» инициал «А» разбирается как
    женское имя, и мужчина становится женщиной.
    """
    if not full_name:
        return None
    части = str(full_name).split()
    if any(_ИНИЦИАЛ.match(часть) for часть in части):
        return None
    return detect_gender(части)


def gender_from_surname(surname: str) -> Optional[str]:
    """Род по окончанию фамилии. Несклоняемые («Тарасенко», «Обама») — None."""
    low = (surname or "").lower()
    if low.endswith(_ЖЕНСКИЕ_ОКОНЧАНИЯ):
        return "femn"
    if low.endswith(_МУЖСКИЕ_ОКОНЧАНИЯ):
        return "masc"
    return None


def gender_of_person(value: str) -> Optional[str]:
    """Род человека: сначала по отчеству, затем по окончанию фамилии."""
    if not value:
        return None
    части = str(value).split()
    return gender_from_full_name(value) or (gender_from_surname(части[0]) if части else None)


def inflect_person_name(value: str, case: str, gender: Optional[str] = None) -> str:
    """Склоняет ФИО: фамилию как фамилию, имя и отчество как имена.

    Запись бывает и сокращённой («Иванов И.И.»), и полной («Иванов Иван
    Иванович») — инициалы остаются как есть, слова склоняются.
    """
    if not value or case == "nomn":
        return value
    части = str(value).split()
    if not части or _ИНИЦИАЛ.match(части[0]):
        return value
    род = gender or gender_of_person(value)
    if род is None:
        return value
    morph = _get_morph()
    итог = [inflect_surname(morph, части[0], case, род)]
    for часть in части[1:]:
        итог.append(часть if _ИНИЦИАЛ.match(часть)
                    else inflect_given_name(morph, часть, case, род))
    return " ".join(итог)
