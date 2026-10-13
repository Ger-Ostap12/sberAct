"""Падежи ФИО судьи и ведущего протокол: шаблон диктует падеж контекстом маркера."""

import logging
import re
from typing import Optional

from morph_utils import detect_gender, inflect_surname

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
    """Род по полному ФИО: отчество отвечает на этот вопрос без догадок."""
    if not full_name:
        return None
    return detect_gender(str(full_name).split())


def gender_from_surname(surname: str) -> Optional[str]:
    """Род по окончанию фамилии. Несклоняемые («Тарасенко», «Обама») — None."""
    low = (surname or "").lower()
    if low.endswith(_ЖЕНСКИЕ_ОКОНЧАНИЯ):
        return "femn"
    if low.endswith(_МУЖСКИЕ_ОКОНЧАНИЯ):
        return "masc"
    return None


def inflect_short_fio(value: str, case: str, gender: Optional[str] = None) -> str:
    """Склоняет фамилию в записи «Фамилия И.О.», инициалы не трогает."""
    if not value or case == "nomn":
        return value
    части = str(value).split()
    if not части or _ИНИЦИАЛ.match(части[0]):
        return value
    род = gender or gender_from_surname(части[0])
    if род is None:
        return value
    склонённая = inflect_surname(_get_morph(), части[0], case, род)
    return " ".join([склонённая] + части[1:])
