# -*- coding: utf-8 -*-
"""Назначение РОЛИ найденному значению по ближайшему якорю (§S.2.C, шаг C2).

Сканеры (`value_scanners`) отвечают на вопрос «что это по форме»: ИНН, ОГРН,
сумма, дата. Здесь отвечают на второй вопрос — «ЧЬЁ это»: должника, кредитора,
управляющего, третьего лица.

Движок не новый. Он уже работает в `semantic_classifier.classify_debtor_name`
для имён должников: взять ближайший СЛЕВА якорь роли, отбросить кандидата, если
к нему ближе якорь ДРУГОЙ роли. Здесь то же правило обобщено с одной роли на
реестр ролей и с имён — на любые значения.

⚠️ ГЛАВНЫЙ РИСК НАЗВАН ПРЯМО: назначение роли по близости — это место, где ИНН
кредитора уезжает должнику. Поэтому:

  * слой ТЕНЕВОЙ, продовые значения не подменяет;
  * при неоднозначности он ВОЗДЕРЖИВАЕТСЯ, а не угадывает — воздержание видно в
    отчёте, ошибка молча портит акт (то же правило, что в процедуре-оси);
  * решение о промоушене принимается ПО ПОЛЮ и только по теневому отчёту.

Якоря лежат ДАННЫМИ (`ROLE_ANCHORS`): добавление роли — строка в реестре, а не
правка логики.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Pattern, Tuple

from value_scanners import Found

# Роли и их якоря. Формулировки взяты из уже работающих якорей
# `semantic_classifier` — расхождение между двумя списками означало бы, что
# один слой считает лицо должником, а другой нет.
ROLE_ANCHORS: Dict[str, str] = {
    "debtor": r"(?:Должник|Ответчик(?:и|а|у|ом|е)?|Заёмщик|Заемщик)",
    # «Банк» здесь НЕ ЯКОРЬ — см. EXCLUSION_ANCHORS ниже.
    "creditor": r"(?:Кредитор|Взыскател\w*|Истец|Заявител\w*)",
    "manager": r"(?:финансов\w+|арбитражн\w+|конкурсн\w+|временн\w+)\s+управляющ\w*",
    "thirdParty": r"(?:Треть\w+\s+лиц\w*|Заинтересованн\w+\s+лиц\w*)",
    "representative": r"(?:Представител\w*|по\s+доверенности)",
    "court": r"(?:Арбитражный\s+суд|Суд\b|Судья)",
}

# Ограничения ФОРМЫ, зависящие от роли. Якорь говорит «чьё», форма — «может ли
# это вообще принадлежать такому лицу».
#
# Единственная запись пока одна, но она закрывает измеренную ловушку (§S.8):
# арбитражный управляющий — ФИЗЛИЦО, его ИНН ВСЕГДА 12 знаков. Рядом со словом
# «управляющий» стоит и десятизначный ИНН — но он принадлежит СРО («из числа
# членов Ассоциации … ИНН …»). На корпусе признак отсёк 16 ложных из 21.
# Теневой отчёт показал ровно это: по якорю «арбитражных управляющих» слой брал
# 6167065084 (СРО) вместо 615519848330 (человек).
ROLE_VALUE_LENGTH: Dict[Tuple[str, str], int] = {
    ("manager", "inn"): 12,
}

# Признаки ЧУЖОГО значения: если такой маркер ближе к находке, чем любой якорь
# роли, слой ВОЗДЕРЖИВАЕТСЯ. Роль отсюда не выводится — только запрет.
#
# Замерено на корпусе, оба варианта проверены прогоном:
#   * «Банк» КАК ЯКОРЬ КРЕДИТОРА — на заявлениях «Форте» слой брал ИНН «ББР
#     Банк» (банк из ЧУЖОГО дела в мотивировке) вместо заявителя АО «ТБАНК»;
#   * «Банк» УБРАН СОВСЕМ — стало хуже: ИНН банков (7702070139 ВТБ,
#     7707372408) провалились к следующему якорю слева и достались ДОЛЖНИКУ.
#     Расхождений по `inn` 6 -> 10. Это и есть «ИНН кредитора уехал должнику».
#
# Отсюда третий вариант: слово из названия организации не даёт роли, но
# перекрывает чужой якорь. Тот же приём, что `_OTHER_ROLE_ANCHOR_RE` в
# `semantic_classifier`, где ближайший якорь иной роли отбраковывает кандидата.
#
# ⚠️ Левая граница `\b` обязательна: без неё «Банк» совпадает ВНУТРИ «Сбербанк»,
# и воздержание срабатывает ровно там, где роль определена верно.
EXCLUSION_ANCHORS: str = (
    r"\b(?:Банк\b|саморегулируем\w+\s+организац\w+|Ассоциаци\w+|"
    r"депозит\w*|получател\w*\s+платежа)"
)

# Дальше этого расстояния якорь считается чужим: в заявлении между блоками
# сторон лежат абзацы мотивировки, и «ближайший слева» без потолка притянул бы
# роль через полстраницы. Замер разлёта на 13 053 символа (§S.3.1) — ровно про
# то, чем кончается отсутствие верхней границы.
MAX_ANCHOR_DISTANCE = 400


@dataclass(frozen=True)
class Assigned:
    """Находка с назначенной ролью.

    `distance` — расстояние до якоря; чем оно больше, тем слабее основание.
    Наружу отдаётся намеренно: спорные случаи должны быть ВИДНЫ в отчёте, а не
    молча проглочены (тот же приём, что уровень запроса в `doc_structure`).
    """

    found: Found
    role: str
    anchor: str
    distance: int


_COMPILED: Dict[str, Pattern[str]] = {}


def _anchor_re(role: str) -> Pattern[str]:
    if role not in _COMPILED:
        _COMPILED[role] = re.compile(ROLE_ANCHORS[role], re.IGNORECASE)
    return _COMPILED[role]


@lru_cache(maxsize=1)
def _exclusion_re() -> Pattern[str]:
    return re.compile(EXCLUSION_ANCHORS, re.IGNORECASE)


def _nearest_preceding(pattern: Pattern[str], text: str,
                       pos: int) -> Optional[Tuple[int, str]]:
    """Ближайшее слева совпадение: (позиция, совпавший текст) или None.

    Перебор идёт от начала строки — так же, как в `semantic_classifier`. Для
    документа в сотню килобайт это заметно, поэтому вызывающий ограничивает
    окно, а не полагается на скорость.
    """
    best: Optional[Tuple[int, str]] = None
    for m in pattern.finditer(text, 0, pos):
        best = (m.start(), m.group(0))
    return best


def _length_fits(role: str, found: Found) -> bool:
    """Проходит ли значение по длине для этой роли (см. `ROLE_VALUE_LENGTH`)."""
    required = ROLE_VALUE_LENGTH.get((role, found.kind))
    if required is None:
        return True
    return len(re.sub(r"\D", "", found.value)) == required


def assign_role(text: str, found: Found,
                roles: Optional[Iterable[str]] = None) -> Optional[Assigned]:
    """Роль одной находки: ближайший слева якорь, если он не перекрыт чужим.

    Возвращает None (ВОЗДЕРЖАНИЕ) когда:
      * слева нет ни одного якоря;
      * ближайший якорь дальше `MAX_ANCHOR_DISTANCE`.

    Воздержание — законный и желательный исход. Пустое поле видно и чинится;
    поле, заполненное чужим ИНН, не видно никому до суда.
    """
    candidates: List[Tuple[int, str, str]] = []
    for role in (roles or ROLE_ANCHORS):
        hit = _nearest_preceding(_anchor_re(role), text, found.start)
        if hit is None:
            continue
        if not _length_fits(role, found):
            continue  # форма не та — значение не может принадлежать этой роли
        candidates.append((hit[0], role, hit[1]))
    if not candidates:
        return None

    anchor_pos, role, anchor_text = max(candidates, key=lambda c: c[0])
    distance = found.start - anchor_pos
    if distance > MAX_ANCHOR_DISTANCE:
        return None

    # Маркер чужого значения ближе якоря роли — воздерживаемся.
    exclusion = _nearest_preceding(_exclusion_re(), text, found.start)
    if exclusion is not None and exclusion[0] > anchor_pos:
        return None

    return Assigned(found=found, role=role, anchor=anchor_text, distance=distance)


def assign_all(text: str, founds: Iterable[Found],
               roles: Optional[Iterable[str]] = None) -> List[Assigned]:
    """Роли для потока находок; безролевые отбрасываются."""
    out: List[Assigned] = []
    for f in founds:
        a = assign_role(text, f, roles=roles)
        if a is not None:
            out.append(a)
    return out


def best_by_role(assigned: Iterable[Assigned]) -> Dict[Tuple[str, str], Assigned]:
    """Лучшая находка на пару (роль, тип): ближайшая к своему якорю.

    Ближайшая, а не первая по тексту: в шапке заявления реквизиты идут подряд,
    и «первый ИНН после слова Должник» — это он и есть, тогда как «первый ИНН в
    документе» принадлежит кому угодно.
    """
    best: Dict[Tuple[str, str], Assigned] = {}
    for a in assigned:
        key = (a.role, a.found.kind)
        current = best.get(key)
        if current is None or a.distance < current.distance:
            best[key] = a
    return best


def role_field_name(role: str, kind: str) -> str:
    """Имя продового поля для пары (роль, тип): debtor+inn -> debtorInn.

    Нужно только отчёту — чтобы сверять теневое значение с продовым по имени.
    Подмены продовых полей этот слой не делает.
    """
    if role == "debtor" and kind == "inn":
        return "inn"  # исторически ИНН должника лежит в поле без префикса
    return role + kind[0].upper() + kind[1:]
