# -*- coding: utf-8 -*-
"""Сканеры значений по ТИПУ, без опоры на метку (§S.2.C, шаг C1).

Инверсия задачи. Сегодня извлечение звучит как «найди значение после метки»,
поэтому незнакомая метка = потерянное поле, а каждый новый банк добавляет
регулярку. Здесь наоборот: сначала находим в тексте всё, что ПО ФОРМЕ является
ИНН, ОГРН, СНИЛС, суммой, датой, — а роль назначаем отдельным шагом (C2).

Основание простое и проверяемое: **новый банк меняет формулировку метки, но
никогда не меняет форму ИНН**. Там, где у реквизита есть контрольная сумма, он
самоидентифицируется — метка нужна только чтобы понять, ЧЕЙ он.

Слой теневой: ничего не подменяет, сверяется отчётом `tools/value_shadow.py`.

Что здесь НЕ делается намеренно:
  * не назначаются роли — это C2, и именно там живёт риск «ИНН кредитора уехал
    должнику»;
  * не нормализуются значения под формат поля — сканер отдаёт то, что нашёл,
    вместе с позицией, чтобы сверка была честной.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Pattern, Tuple

from requisites_validation import (
    is_valid_inn,
    is_valid_kpp,
    is_valid_ogrn,
    is_valid_ogrnip,
)


@dataclass(frozen=True)
class Found:
    """Одна находка сканера.

    `valid` — прошло ли значение проверку по существу (контрольная сумма для
    ИНН/ОГРН, формат для СНИЛС). Находки с `valid=False` НЕ выбрасываются: они
    нужны отчёту, чтобы отличить «в документе опечатка» от «сканер слеп».
    """

    kind: str
    value: str
    start: int
    end: int
    valid: bool = True


# --- Формы реквизитов --------------------------------------------------------
#
# Границы `(?<!\d)` / `(?!\d)` обязательны везде, где ищем цифры фиксированной
# длины: без них двенадцатизначный ИНН отдаст «первые десять» и пройдёт проверку
# как ИНН юрлица (тот же дефект чинили в паспорте — §S.9).

_INN_RE = re.compile(r"(?<!\d)(\d{12}|\d{10})(?!\d)")
_OGRN_RE = re.compile(r"(?<!\d)(\d{15}|\d{13})(?!\d)")
_KPP_RE = re.compile(r"(?<!\w)(\d{4}[\dA-ZА-Я]{2}\d{3})(?!\w)")
_SNILS_RE = re.compile(r"(?<!\d)(\d{3}[- ]?\d{3}[- ]?\d{3}[- ]?\d{2})(?!\d)")

# Деньги: обязательна дробная часть ИЛИ валюта — иначе номер дела и год
# становятся суммами. Разделитель разрядов — пробел (в т.ч. неразрывный).
_MONEY_RE = re.compile(
    r"""(?<![\d,.])
        (\d{1,3}(?:[\s ]\d{3})+ | \d+)      # целая часть
        (?:[.,](\d{2}))?                          # копейки
        \s*(?:руб|₽)                              # валюта обязательна
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?!\d)")

# Номер дела: А40-123456/2024, в т.ч. с латинской «A» — OCR их путает.
_CASE_RE = re.compile(r"(?<![\w-])([АA]\d{1,2}[-–]\d{1,7}\s?/\s?\d{4})(?![\w-])")

# Кадастровый номер: 61:44:0000000:12345, число блоков фиксировано.
_CADASTRAL_RE = re.compile(r"(?<![\d:])(\d{2}:\d{2}:\d{6,7}:\d{1,10})(?![\d:])")

# VIN: 17 знаков, латиница без I, O, Q — по стандарту.
_VIN_RE = re.compile(r"(?<![A-HJ-NPR-Z0-9])([A-HJ-NPR-Z0-9]{17})(?![A-HJ-NPR-Z0-9])")

# ФИО: три слова с заглавной. Скоуп `(?-i:...)` нужен, потому что регистр здесь
# и есть признак — при IGNORECASE выражение поймало бы любые три слова.
_FIO_RE = re.compile(
    r"(?<![А-ЯЁA-Z])(?-i:[А-ЯЁ][А-ЯЁа-яё-]+(?:\s+[А-ЯЁ][А-ЯЁа-яё-]+){2})(?![а-яё])"
)

# Адрес: якорь — почтовый индекс, дальше до конца строки или до метки.
_ADDRESS_RE = re.compile(r"(?<!\d)(\d{6},?\s[^\n]{5,200})")

_SNILS_FMT_RE = re.compile(r"^\d{3}-\d{3}-\d{3} \d{2}$")


def _snils_valid(value: str) -> bool:
    """СНИЛС: 11 цифр + контрольное число.

    Контрольная сумма считается только для номеров больше 001-001-998:
    меньшие выданы до её введения и проверке не подлежат.
    """
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        return False
    body, check = digits[:9], int(digits[9:])
    if int(body) <= 1001998:
        return True
    total = sum(int(d) * (9 - i) for i, d in enumerate(body))
    if total in (100, 101):
        total = 0
    elif total > 101:
        total = total % 101
        if total in (100, 101):
            total = 0
    return total == check


def _scan(pattern: Pattern[str], text: str, kind: str,
          validator: Optional[Callable[[str], bool]] = None,
          group: int = 1) -> List[Found]:
    out: List[Found] = []
    for m in pattern.finditer(text):
        value = m.group(group) if m.groups() else m.group(0)
        out.append(Found(
            kind=kind, value=value.strip(), start=m.start(group if m.groups() else 0),
            end=m.end(group if m.groups() else 0),
            valid=validator(value) if validator else True,
        ))
    return out


def scan_inn(text: str) -> List[Found]:
    """ИНН: 10 или 12 цифр с валидной контрольной суммой.

    Длина здесь несёт смысл роли, и это единственный надёжный разделяющий
    признак, который у нас есть: 12 знаков — физлицо (должник-гражданин,
    арбитражный управляющий), 10 — организация (банк, СРО, должник-ЮЛ).
    На корпусе он отсёк 16 ложных ИНН управляющего из 21 (§S.8).
    """
    return _scan(_INN_RE, text, "inn", is_valid_inn)


def scan_ogrn(text: str) -> List[Found]:
    """ОГРН (13) и ОГРНИП (15) — различаются длиной и делителем контрольной суммы."""
    out: List[Found] = []
    for f in _scan(_OGRN_RE, text, "ogrn"):
        digits = re.sub(r"\D", "", f.value)
        kind = "ogrnip" if len(digits) == 15 else "ogrn"
        valid = is_valid_ogrnip(f.value) if kind == "ogrnip" else is_valid_ogrn(f.value)
        out.append(Found(kind, f.value, f.start, f.end, valid))
    return out


def scan_kpp(text: str) -> List[Found]:
    return _scan(_KPP_RE, text, "kpp", is_valid_kpp)


def scan_snils(text: str) -> List[Found]:
    return _scan(_SNILS_RE, text, "snils", _snils_valid)


def scan_money(text: str) -> List[Found]:
    """Суммы. Валюта обязательна — без неё номер дела и год станут деньгами."""
    out: List[Found] = []
    for m in _MONEY_RE.finditer(text):
        out.append(Found("money", m.group(0).strip(), m.start(), m.end()))
    return out


def scan_date(text: str) -> List[Found]:
    """Даты в числовом виде; валидность — календарная, а не только формат."""
    out: List[Found] = []
    for m in _DATE_RE.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        valid = 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100
        out.append(Found("date", m.group(0), m.start(), m.end(), valid))
    return out


def scan_case_number(text: str) -> List[Found]:
    return _scan(_CASE_RE, text, "caseNumber")


def scan_fio(text: str) -> List[Found]:
    """Кандидаты в ФИО по форме. Это НЕ значит, что каждый из них — человек.

    Отбраковка чужого («Ассоциация Саморегулируемая Организация») — задача
    назначения ролей и `is_person_name`, а не формы.
    """
    out: List[Found] = []
    for m in _FIO_RE.finditer(text):
        out.append(Found("fio", m.group(0).strip(), m.start(), m.end()))
    return out


def scan_address(text: str) -> List[Found]:
    return _scan(_ADDRESS_RE, text, "address")


def scan_cadastral(text: str) -> List[Found]:
    return _scan(_CADASTRAL_RE, text, "cadastral")


def scan_vin(text: str) -> List[Found]:
    """VIN. Форма слабая (17 знаков), поэтому без контекста ложные срабатывания
    неизбежны — отсев по близости к слову «идентификационный»/«VIN» делает C2."""
    return _scan(_VIN_RE, text, "vin")


SCANNERS: Dict[str, Callable[[str], List[Found]]] = {
    "inn": scan_inn,
    "ogrn": scan_ogrn,
    "kpp": scan_kpp,
    "snils": scan_snils,
    "money": scan_money,
    "date": scan_date,
    "caseNumber": scan_case_number,
    "fio": scan_fio,
    "address": scan_address,
    "cadastral": scan_cadastral,
    "vin": scan_vin,
}


def scan_all(text: str, kinds: Optional[Iterable[str]] = None) -> List[Found]:
    """Все находки, отсортированные по позиции в тексте.

    Порядок по позиции — не косметика: назначение ролей (C2) ищет ближайший
    слева якорь, и ему нужен упорядоченный поток находок.
    """
    selected = list(kinds) if kinds else list(SCANNERS)
    out: List[Found] = []
    for kind in selected:
        scanner = SCANNERS.get(kind)
        if scanner:
            out.extend(scanner(text))
    return sorted(out, key=lambda f: (f.start, f.kind))


def valid_only(found: Iterable[Found]) -> List[Found]:
    """Только прошедшие проверку по существу."""
    return [f for f in found if f.valid]


def by_kind(found: Iterable[Found]) -> Dict[str, List[Found]]:
    out: Dict[str, List[Found]] = {}
    for f in found:
        out.setdefault(f.kind, []).append(f)
    return out


def dedupe(found: Iterable[Found]) -> List[Found]:
    """Одинаковые значения одного типа из одной позиции — одна находка."""
    seen: set[Tuple[str, str, int]] = set()
    out: List[Found] = []
    for f in found:
        key = (f.kind, re.sub(r"\s", "", f.value), f.start)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
