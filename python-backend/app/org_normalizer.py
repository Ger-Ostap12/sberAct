# -*- coding: utf-8 -*-
"""Нормализация наименований организаций и защитные фильтры юридического текста.

Порт устойчивых функций из обезличивателя (anonymizer_project):
- norm_org_key / base_org_name — канонизация названий ЮЛ (раскрытие полных
  правовых форм, снятие кавычек, отсечение хвоста «-Банк/России»);
- looks_like_law_ref — отличить ссылку на закон (№ 353-ФЗ) от номера договора;
- date_in_law_context — дата стоит в ссылке на ФЗ/постановление Пленума.

Все функции — чистые (без состояния), импортируются как `from org_normalizer import ...`.
"""
from __future__ import annotations

import re

# Удаление всех видов кавычек (только chr(), без литералов Unicode в исходнике).
_QUOTE_TABLE = str.maketrans(
    "", "",
    "".join(chr(c) for c in (0xAB, 0xBB, 0x201C, 0x201D, 0x2018, 0x2019, 0x22, 0x27)),
)

# Полные наименования правовых форм -> аббревиатура. Порядок важен:
# более специфичные паттерны идут первыми.
_ORG_FULL_FORMS = (
    (re.compile(r"публич\w+\s+акционер\w+\s+обществ\w+", re.I), "пао"),
    (re.compile(r"открыт\w+\s+акционер\w+\s+обществ\w+", re.I), "оао"),
    (re.compile(r"закрыт\w+\s+акционер\w+\s+обществ\w+", re.I), "зао"),
    (re.compile(r"непублич\w+\s+акционер\w+\s+обществ\w+", re.I), "ао"),
    (re.compile(r"акционер\w+\s+обществ\w+", re.I), "ао"),
    (re.compile(r"обществ\w+\s+с\s+ограниченн\w+\s+ответственность\w*", re.I), "ооо"),
    (re.compile(r"обществ\w+\s+с\s+дополнительн\w+\s+ответственность\w*", re.I), "одо"),
)

_ABBREV_RE = r"ооо|ао|пао|зао|оао|нао|акб|кб|мкк|мфо|пко|ип"


def norm_org_key(value: str) -> str:
    """Канонический ключ организации: '<форма>:<базовое имя>' либо '<базовое имя>'.

    Примеры:
        'ООО «КОЛОР»'                                   -> 'ооо:колор'
        'Общество с ограниченной ответственностью «КОЛОР»' -> 'ооо:колор'
        'ПАО Сбербанк'                                  -> 'пао:сбербанк'
        'Публичное акционерное общество «Сбербанк России»' -> 'пао:сбербанк'
    """
    if not value:
        return ""
    m = re.search(r"[«\"](.*?)[»\"]", value)
    if m:
        name = m.group(1).lower().strip()
        name = re.sub(
            r"[-\s]+(?:банк|банка|банки|банку|банком|банке|России)\s*$",
            "", name, flags=re.I,
        ).strip()
        prefix = value[:m.start()].strip().lower()
        abbrev = _detect_abbrev(prefix)
        return f"{abbrev}:{name}" if abbrev else name

    s = value.lower().translate(_QUOTE_TABLE)
    s = re.sub(r"\s+в\s+лице\b.*", "", s, flags=re.I)
    abbrev = _detect_abbrev(s)
    for pattern, _ in _ORG_FULL_FORMS:
        s = pattern.sub("", s)
    s = re.sub(rf"^(?:{_ABBREV_RE})\s+", "", s, flags=re.I)
    s = re.sub(r"[-\s]+банк\w*\s*$", "", s, flags=re.I).strip()
    base = re.sub(r"\s+", " ", s).strip()
    return f"{abbrev}:{base}" if abbrev else base


def base_org_name(value: str) -> str:
    """Только базовое имя организации без правовой формы (для матча по реестру).

    'Общество с ограниченной ответственностью «КОЛОР»' -> 'колор'
    'ПАО «Сбербанк России»'                            -> 'сбербанк'
    """
    key = norm_org_key(value)
    return key.split(":", 1)[1] if ":" in key else key


def _detect_abbrev(prefix: str) -> str | None:
    """Определить аббревиатуру правовой формы по тексту-префиксу.

    Сначала полные формы («Публичное акционерное общество»), затем — аббревиатура
    в НАЧАЛЕ префикса (так «АО ПКО ...» даёт правовую форму 'ао', а не уточнение 'пко').
    """
    for pattern, abbr in _ORG_FULL_FORMS:
        if pattern.search(prefix):
            return abbr
    m = re.match(rf"\s*({_ABBREV_RE})\b", prefix, re.I)
    if m:
        return m.group(1).lower()
    return None


# --- Фича C: номер договора vs ссылка на закон ---------------------------------
_LAW_REF_RE = re.compile(r"^\s*№?\s*\d{1,5}-(?:ФЗ|ФКЗ|КЗ)\b", re.I)


def looks_like_law_ref(value: str) -> bool:
    """True, если значение — ссылка на закон (№ 353-ФЗ), а не номер договора."""
    if not value:
        return False
    return bool(_LAW_REF_RE.match(value))


# --- Фича D: дата в контексте ссылки на закон ----------------------------------
_LAW_DATE_CONTEXT_RE = re.compile(r"\b(?:ФЗ|ФКЗ|КЗ|постановлен(?:ие|ия)|пленума?|пленум)\b", re.I)


def date_in_law_context(text: str, start: int, end: int, window: int = 40) -> bool:
    """True, если дата на позиции [start:end] стоит рядом со ссылкой на закон/Пленум.

    Используется, чтобы не принимать дату нормативного акта (ФЗ от 26.10.2002)
    за дату договора/решения суда.
    """
    if not text:
        return False
    near = text[max(0, start - window): end + window // 2]
    return bool(_LAW_DATE_CONTEXT_RE.search(near))
