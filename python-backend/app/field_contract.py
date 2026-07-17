# -*- coding: utf-8 -*-
"""Контракт поля: что в поле ДОЛЖНО лежать, и что делать, если лежит чужое.

Зачем. Извлечение собрано из паттернов, каждое поле извлекается независимо и не
знает про остальных. Из-за этого «Арбитражный суд Ростовской области» спокойно
живёт одновременно в `courtName` и в денежном `loanDebt` — мы сами его туда
положили и не заметили, а документ при этом получает `confidence = 0.95`.
Контракт — последний рубеж: поле обязано быть тем, чем объявлено.

Правило Андрея (§K.1): **пусто лучше чужого значения в акте** — ЧУЖОЕ вычищаем и
помечаем, чтобы юрист видел, что поле требует ввода, а не подсовываем мусор в акт.

⚠️ Исключение — реквизиты (ИНН/ОГРН/ОГРНИП): их только ПОМЕЧАЕМ, не чистим
(решение Андрея). Провал контрольной суммы на OCR-скане обычно значит «свой
реквизит с побитой цифрой», а не «чужой»: в `A53-9758-2026_20260318_Zajavlenie.docx`
ИНН `612102429513` стоит под меткой должника трижды подряд. Править одну цифру
глазами дешевле, чем набирать двенадцать заново. Чужой реквизит поймает слой
владения текстом — для этого контрольная сумма не нужна.

Слои проверки:
1. ТИП — деньги это число, ИНН/ОГРН проходят контрольную сумму ФНС, адрес похож
   на адрес. Валидаторы переиспользуем (`requisites_validation`), не пишем заново.
2. ВЛАДЕНИЕ ТЕКСТОМ (дешёвая версия span ownership) — если значение поля дословно
   совпадает со значением ДРУГОГО поля несовместимого типа, значит мы уже отдали
   этот текст законному владельцу, а сюда он попал по ошибке. Никаких списков
   запрещённых слов: система знает, что текст чужой, потому что знает, чей он.

Модуль без побочных эффектов, кроме единственной функции `apply_contract`, которая
явно правит переданный словарь (по образцу `_sanitize_address_fields`).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from requisites_validation import is_valid_inn, is_valid_ogrn, is_valid_ogrnip

# --- типы полей -------------------------------------------------------------
# Реестр, а не магические строки в логике (требование CLAUDE.md). Поля, которых
# здесь нет, НЕ проверяются: молчать безопаснее, чем чистить непонятое.
MONEY = "money"
INN = "inn"
OGRN = "ogrn"
OGRNIP = "ogrnip"
ADDRESS = "address"
ORG = "org"
COURT = "court"

_FNS_QUEUE_MONEY_SUFFIXES = (
    "Total",
    "Arrears",
    "Penalties",
    "Forfeit",
    "Ndfl",
    "Insurance",
    "LoanDebt",
    "LoanDuty",
    "Commission",
)

FIELD_TYPES: Dict[str, str] = {
    # деньги
    "totalDebt": MONEY,
    "debtAmount": MONEY,
    "requirementsSum": MONEY,
    "principalDebt": MONEY,
    "principalDebt13": MONEY,
    "loanDebt": MONEY,
    "interest": MONEY,
    "interest14": MONEY,
    "forfeit": MONEY,
    "forfeit15": MONEY,
    "penalties": MONEY,
    "penalty0071": MONEY,
    "stateDuty": MONEY,
    "stateDuty16": MONEY,
    "loanStateDuty17": MONEY,
    "obligationsTotalDebt": MONEY,
    "creditAmount": MONEY,
    "bankCommission": MONEY,
    "other35": MONEY,
    "currentInterest36": MONEY,
    "currentInterestOverdue37": MONEY,
    "ipCollateralClaimAmount": MONEY,
    "priorAmount": MONEY,
    "priorStateDuty": MONEY,
    "mortgagePrincipalAmount11": MONEY,
    "mortgageInterestAmount12": MONEY,
    "mortgagePeriodAmount10": MONEY,
    "mortgageCreditAmount111": MONEY,
    "mortgageCollateralValue1224": MONEY,
    "mortgageStartingPrice1225": MONEY,
    # реквизиты
    "inn": INN,
    "companyInn": INN,
    "creditorInn": INN,
    "managerInn": INN,
    "thirdPartyInn": INN,
    "ogrn": OGRN,
    "creditorOgrn": OGRN,
    "ogrnip": OGRNIP,
    # адреса
    "applicantAddress": ADDRESS,
    "creditorAddress": ADDRESS,
    "debtorAddress": ADDRESS,
    "managerAddress": ADDRESS,
    "thirdPartyAddress": ADDRESS,
    "address": ADDRESS,
    # организации и суд
    "creditorName": ORG,
    "sroName": ORG,
    "courtName": COURT,
}
for _q in (1, 2, 3):
    for _suffix in _FNS_QUEUE_MONEY_SUFFIXES:
        FIELD_TYPES[f"fnsQ{_q}{_suffix}"] = MONEY

# Даты СОЗНАТЕЛЬНО не в реестре: `contractDate`/`birthDate` легитимно
# многозначные («21.09.2023, 30.03.2023» для нескольких договоров/должников), а
# единственная стабильно неверная дата — `applicationDate` — решением Андрея не
# чинится как мёртвое поле (handoff §K.5). Проверять нечего, а риск ложняков есть.

# --- примитивы --------------------------------------------------------------
# Денежное значение: разряды пробелами/неразрывными, копейки через запятую/точку.
_MONEY_RE = re.compile(r"^\d[\d\s  ]*(?:[.,]\d{1,2})?$")
_LETTERS_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
# Почтовый индекс — адресный компонент. В имени организации ему не место
# («ПАО Сбербанк России в лице Юго-Западного банка 344068»).
_TRAILING_INDEX_RE = re.compile(r"[\s,]+\d{6}\s*$")
# Признаки адреса: хотя бы один компонент обязан присутствовать. Позитивная
# грамматика вместо чёрного списка запрещённых слов — «ПАО Сбер» отсекается не
# потому, что «ПАО» в списке плохих, а потому, что адресом не является.
_ADDR_MARKERS_RE = re.compile(
    r"\b\d{6}\b"  # индекс
    r"|\bобл(?:асть|асти|\.)"  # область
    r"|\b(?:респ|край|krai)\w*"  # республика/край
    r"|\bр-?н\b|\bрайон\w*"  # район
    r"|\b(?:г|гор|город)\b\.?\s*[А-ЯЁ]"  # город
    r"|\b(?:с|село|ст|станица|х|хутор|пос|посёлок|поселок|мкр|тер)\b\.?\s*[А-ЯЁ]"
    r"|\b(?:ул|улица|пр-?кт|проспект|пер|переулок|шоссе|б-р|бульвар|наб|набережная)\b\.?"
    r"|\b(?:д|дом|влд|стр|корп|к|кв|оф|офис|пом|ком|литер)\b\.?\s*\d"
    r"|\bа/я\s*\d",  # абонентский ящик
    re.IGNORECASE,
)

# Типы, которые мы только ПОМЕЧАЕМ, но не чистим (см. шапку модуля): битый
# реквизит полезнее пустого поля, юрист правит цифру по исходнику.
_FLAG_ONLY_TYPES = (INN, OGRN, OGRNIP)

# Пары типов, которые НЕ могут делить один и тот же текст. Слева — поле-жертва
# (чистим его), справа — законный владелец. Порядок важен: чистим только жертву.
_INCOMPATIBLE: Tuple[Tuple[str, str], ...] = (
    (MONEY, COURT),
    (MONEY, ORG),
    (MONEY, ADDRESS),
    (ADDRESS, ORG),
    (ADDRESS, COURT),
)


class Issue:
    """Одна претензия контракта к значению поля (для `fieldIssues` и логов).

    `cleared` — вычистили поле или только пометили: фронту это нужно, чтобы
    отличить «поле пустое, введи» от «значение подозрительное, проверь».
    """

    __slots__ = ("field", "reason", "value", "cleared")

    def __init__(self, field: str, reason: str, value: Any, cleared: bool = True):
        self.field = field
        self.reason = reason
        self.value = value
        self.cleared = cleared

    def as_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "reason": self.reason, "value": str(self.value)[:200], "cleared": self.cleared}

    def __repr__(self) -> str:  # для читаемых падений тестов
        return f"Issue({self.field!r}, {self.reason!r}, {str(self.value)[:40]!r})"


def _parts(value: str) -> List[str]:
    """Значение может быть многозначным («ИНН1, ИНН2» для нескольких должников)."""
    return [p.strip() for p in str(value).split(",") if p.strip()]


def check_value(field: str, value: Any) -> Optional[str]:
    """Претензия к значению поля или None, если всё в порядке. Чистая функция."""
    ftype = FIELD_TYPES.get(field)
    if not ftype:
        return None
    text = str(value or "").strip()
    if not text:
        return None

    if ftype == MONEY:
        # Буквы в сумме — это чужой текст: суд, адрес, кусок прозы.
        if _LETTERS_RE.search(text):
            return "в денежном поле текст, а не сумма"
        if not _MONEY_RE.match(text):
            return "значение не похоже на денежную сумму"
        return None

    if ftype in (INN, OGRN, OGRNIP):
        validator = {INN: is_valid_inn, OGRN: is_valid_ogrn, OGRNIP: is_valid_ogrnip}[ftype]
        parts = _parts(text)
        # Чистим, только если НИ ОДНО значение не проходит контрольную сумму:
        # при частичном совпадении вероятнее многозначное поле, чем мусор.
        if parts and not any(validator(p) for p in parts):
            return f"{ftype.upper()} не проходит контрольную сумму"
        return None

    if ftype == ADDRESS:
        if not _ADDR_MARKERS_RE.search(text):
            return "значение не содержит ни одного адресного признака"
        return None

    return None


def check_cross_field(fields: Dict[str, Any]) -> List[Issue]:
    """Владение текстом: поле-жертва присвоило значение чужой сущности.

    Дешёвая версия span ownership: сравниваем не позиции в тексте, а сами
    значения — они уже собраны в одном словаре. Ловит `loanDebt` == `courtName`
    и `applicantAddress` ⊂ `creditorName`. Чистая функция.
    """
    issues: List[Issue] = []
    for victim_type, owner_type in _INCOMPATIBLE:
        victims = [f for f, t in FIELD_TYPES.items() if t == victim_type and fields.get(f)]
        owners = [f for f, t in FIELD_TYPES.items() if t == owner_type and fields.get(f)]
        for victim in victims:
            vraw = str(fields.get(victim) or "").strip()
            if len(vraw) < 4:  # слишком коротко, совпадение было бы случайным
                continue
            vnorm = _norm_for_compare(vraw)
            for owner in owners:
                onorm = _norm_for_compare(str(fields.get(owner) or ""))
                if len(onorm) < 4:
                    continue
                if vnorm == onorm or vnorm.startswith(onorm) or onorm.startswith(vnorm):
                    issues.append(Issue(victim, f"значение принадлежит полю «{owner}», а не этому", vraw))
                    break
    return issues


def _norm_for_compare(value: str) -> str:
    """Сравнение значений без оглядки на регистр и лишние пробелы/переносы."""
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def clean_org_tail(value: str) -> str:
    """Хвост-индекс в имени организации: «… Юго-Западного банка 344068» → без индекса.

    Позитивное правило: индекс — адресный компонент, в наименовании его быть не
    может. Чистая функция.
    """
    return _TRAILING_INDEX_RE.sub("", str(value or "")).strip(" ,;-")


def apply_contract(fields: Dict[str, Any]) -> List[Issue]:
    """Привести поля в соответствие контракту. ЯВНО правит переданный словарь.

    Возвращает список претензий — вызывающий кладёт их в top-level `fieldIssues`
    (в fields не кладём: они бы уехали в editedFields фронта и в golden).
    """
    issues: List[Issue] = []

    # 1. Хвосты в именах организаций — до проверок типов: обрезанное имя может
    #    оказаться валидным, и претензии не будет.
    for field, ftype in FIELD_TYPES.items():
        if ftype != ORG or not fields.get(field):
            continue
        cleaned = clean_org_tail(fields[field])
        if cleaned and cleaned != fields[field]:
            issues.append(Issue(field, "убран адресный хвост (почтовый индекс) из наименования", fields[field]))
            fields[field] = cleaned

    # 2. Владение текстом — до проверки типов: конфликт объясняет причину точнее,
    #    чем «в денежном поле текст».
    for issue in check_cross_field(fields):
        issues.append(issue)
        fields.pop(issue.field, None)

    # 3. Типы.
    for field in list(fields.keys()):
        reason = check_value(field, fields.get(field))
        if not reason:
            continue
        flag_only = FIELD_TYPES.get(field) in _FLAG_ONLY_TYPES
        issues.append(Issue(field, reason, fields[field], cleared=not flag_only))
        if not flag_only:
            fields.pop(field, None)

    return issues


def find_issues(fields: Dict[str, Any]) -> List[Issue]:
    """Претензии к словарю БЕЗ правки — для инвариантов между шагами каскада."""
    issues = [Issue(i.field, i.reason, i.value) for i in check_cross_field(fields)]
    for field, value in fields.items():
        reason = check_value(field, value)
        if reason and FIELD_TYPES.get(field) not in _FLAG_ONLY_TYPES:
            issues.append(Issue(field, reason, value))
    return issues


def check_entries(
    entries: List[Dict[str, Any]], name_field: str = "name", address_field: str = "address"
) -> List[Issue]:
    """Контракт для записей `debtors[]`/`thirdParties[]`/`heirs[]`.

    Они строятся ОТДЕЛЬНЫМ путём, мимо `fields` — ловушка §J.3: правка только
    fields оставляет тот же мусор в `debtors[0].address`. ЯВНО правит записи.
    """
    issues: List[Issue] = []
    for i, entry in enumerate(entries or []):
        if not isinstance(entry, dict):
            continue
        address = entry.get(address_field)
        if address and check_value("applicantAddress", address):
            issues.append(
                Issue(
                    f"{name_field}[{i}].{address_field}", "значение не содержит ни одного адресного признака", address
                )
            )
            entry[address_field] = ""
    return issues
