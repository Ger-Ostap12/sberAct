# -*- coding: utf-8 -*-
"""Морфологические хелперы для склонения ФИО (общие для всех падежей).

Порт устойчивых приёмов из обезличивателя (anonymizer_project/generators/fio_gen.py):
- предпочтение Surn-разбора pymorphy (фамилии-омонимы вроде «Тарасин» иначе
  парсятся как Name и склоняются неверно);
- передача рода в inflect — критично для женских фамилий (Кузнецова -> Кузнецовой);
- ручной суффиксный fallback для фамилий, которые pymorphy не склоняет.

Функции принимают `morph` (pymorphy3.MorphAnalyzer) аргументом — модуль не держит
состояния и не импортирует pymorphy напрямую (мягкая зависимость в analyzer).
"""
from __future__ import annotations

import re
from typing import Optional

# Падежи pymorphy: gent=род., datv=дат., ablt=твор., accs=вин., loct=предл.
_KNOWN_SURNAME_SUFFIXES = ("ов", "ев", "ёв", "ин", "ын", "ий", "ый", "ский", "цкий")

# Базовая форма фамилии (муж., им.п.) -> окончание для целевого падежа.
# Ключ — пара (мужской_суффикс, падеж, род). Значение — окончание после усечения суффикса.
_SURNAME_ENDINGS = {
    # -ов/-ев/-ёв
    "ов": {"gent": {"masc": "ова", "femn": "овой"}, "datv": {"masc": "ову", "femn": "овой"},
           "ablt": {"masc": "овым", "femn": "овой"}, "accs": {"masc": "ова", "femn": "ову"},
           "loct": {"masc": "ове", "femn": "овой"}},
    "ев": {"gent": {"masc": "ева", "femn": "евой"}, "datv": {"masc": "еву", "femn": "евой"},
           "ablt": {"masc": "евым", "femn": "евой"}, "accs": {"masc": "ева", "femn": "еву"},
           "loct": {"masc": "еве", "femn": "евой"}},
    "ёв": {"gent": {"masc": "ёва", "femn": "ёвой"}, "datv": {"masc": "ёву", "femn": "ёвой"},
           "ablt": {"masc": "ёвым", "femn": "ёвой"}, "accs": {"masc": "ёва", "femn": "ёву"},
           "loct": {"masc": "ёве", "femn": "ёвой"}},
    # -ин/-ын
    "ин": {"gent": {"masc": "ина", "femn": "иной"}, "datv": {"masc": "ину", "femn": "иной"},
           "ablt": {"masc": "иным", "femn": "иной"}, "accs": {"masc": "ина", "femn": "ину"},
           "loct": {"masc": "ине", "femn": "иной"}},
    "ын": {"gent": {"masc": "ына", "femn": "ыной"}, "datv": {"masc": "ыну", "femn": "ыной"},
           "ablt": {"masc": "ыным", "femn": "ыной"}, "accs": {"masc": "ына", "femn": "ыну"},
           "loct": {"masc": "ыне", "femn": "ыной"}},
}
# Прилагательные фамилии (-ий/-ый/-ский/-цкий), только мужской род; женский -ая/-ой.
_ADJ_SURNAME = {
    "ский": {"masc": {"gent": "ского", "datv": "скому", "ablt": "ским", "accs": "ского", "loct": "ском"},
             "femn": {"gent": "ской", "datv": "ской", "ablt": "ской", "accs": "скую", "loct": "ской"}},
    "цкий": {"masc": {"gent": "цкого", "datv": "цкому", "ablt": "цким", "accs": "цкого", "loct": "цком"},
             "femn": {"gent": "цкой", "datv": "цкой", "ablt": "цкой", "accs": "цкую", "loct": "цкой"}},
    "ий":   {"masc": {"gent": "ого", "datv": "ому", "ablt": "им", "accs": "ого", "loct": "ом"}},
    "ый":   {"masc": {"gent": "ого", "datv": "ому", "ablt": "ым", "accs": "ого", "loct": "ом"}},
}


def match_original_case(original: str, new_value: str) -> str:
    """Сохранить регистр исходного слова (КАПС/Title/lower)."""
    if original.isupper():
        return new_value.upper()
    if original.istitle():
        return new_value.capitalize()
    return new_value


def detect_gender(tokens: list[str]) -> Optional[str]:
    """Определить род по отчеству/имени. Возвращает 'masc'/'femn' или None.

    Приоритет — отчество (последний токен из >=3): -вич -> masc, -вна/-чна -> femn.
    Затем имя (второй токен) по типичным женским окончаниям.
    """
    low = [t.lower().strip(".") for t in tokens if t.strip(".")]
    if not low:
        return None
    if len(low) >= 3:
        patr = low[-1]
        if patr.endswith(("вич", "ич")):
            return "masc"
        if patr.endswith(("вна", "чна", "ична")):
            return "femn"
    if len(low) >= 2:
        name = low[1]
        if name.endswith(("вич", "ич")):
            return "masc"
        if name.endswith(("а", "я", "яна", "ина", "ия", "ея")):
            return "femn"
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
    """Строка действительно ФИО, а не проза и не название организации.

    По старому латентному дефекту в склонение ФИО попадают и другие строки:
    название юрлица («ООО «форт Пром Стил ГМБХ»») и целые куски прозы
    («… в лице законного представителя …»). Их падежи мусорны и без нас;
    менять там один мусор на другой — не починка, а шум в golden. Поэтому
    строгий разбор имени включаем только на форме «2-4 слова с заглавной».
    """
    return 2 <= len(tokens) <= 4 and all(_FIO_TOKEN_RE.match(t) for t in tokens)


def _given_name_parse(morph, token: str, gender: Optional[str]):
    """Выбрать разбор для склонения имени/отчества. None — склонять нечем.

    Отбор осознанный, а не «первый по весу»: у редкого имени первым идёт
    ошибочный разбор, и слово уезжает в чужую парадигму. «Совдаш» pymorphy
    читает как родительный МНОЖЕСТВЕННОГО и даёт «Совдашам», «Сальвиназ» —
    так же. Сами документы такие имена не склоняют.

    Правила по убыванию силы:
      1) множественное число отбрасываем всегда — ФИО не бывает во мн.ч.;
      2) есть личные разборы (имя/отчество/фамилия) — берём личный в
         именительном единственном, согласный с известным родом; если
         подходящего нет, значит слово опознано неверно и склонять нельзя;
      3) личных разборов нет — слово попало в ФИО не как имя (хвост прозы
         вроде «Сообщение»). Поведение прежнее: первый разбор в ед.ч.
    """
    разборы = morph.parse(token)
    единственные = [p for p in разборы if "plur" not in str(p.tag)]
    if any(any(t in str(p.tag) for t in _PERSONAL_TAGS) for p in разборы):
        for разбор in единственные:
            тег = str(разбор.tag)
            if not any(t in тег for t in _PERSONAL_TAGS) or "nomn" not in тег:
                continue
            # Род известен из отчества: разбор другого рода спорит с фактом
            # и даёт мужскую форму женского имени.
            if gender and gender not in тег:
                continue
            return разбор
        return None
    return единственные[0] if единственные else None


def inflect_given_name(morph, token: str, case: str, gender: Optional[str],
                       strict: bool = True) -> str:
    """Просклонять имя или отчество. Неопознанное слово возвращается как есть.

    `strict=False` — прежнее поведение (первый разбор по весу). Нужно для строк,
    которые ФИО не являются: см. looks_like_fio.
    """
    if not token or case == "nomn" or morph is None:
        return token
    if "-" in token:
        return "-".join(
            inflect_given_name(morph, часть, case, gender, strict) for часть in token.split("-"))

    if strict:
        разбор = _given_name_parse(morph, token, gender)
    else:
        разборы = morph.parse(token)
        разбор = разборы[0] if разборы else None
    if разбор is None:
        return token
    граммемы = {case, "anim"} if case == "accs" else {case}
    склонённое = разбор.inflect(граммемы) or разбор.inflect({case})
    if not склонённое:
        return token
    return match_original_case(token, склонённое.word)


def inflect_surname(morph, surname: str, case: str, gender: Optional[str]) -> str:
    """Просклонять фамилию в падеж `case` с учётом рода.

    Стратегия:
      1) ручные правила для типовых русских суффиксов (надёжнее pymorphy по роду);
      2) иначе — pymorphy с предпочтением Surn-разбора и передачей рода;
      3) при неудаче — исходная фамилия (несклоняемые: Шевченко, Дюма и т.п.).
    Регистр исходного слова сохраняется.
    """
    if not surname or case == "nomn":
        return surname

    # Двойная фамилия через дефис — склоняем каждую часть отдельно.
    if "-" in surname:
        return "-".join(inflect_surname(morph, part, case, gender) for part in surname.split("-"))

    manual = _manual_surname(surname, case, gender)
    if manual is not None:
        return match_original_case(surname, manual)

    if morph is None:
        return surname

    parses = morph.parse(surname)
    parsed = next((p for p in parses if "Surn" in str(p.tag)), parses[0])
    grammemes = {case}
    if gender:
        grammemes.add(gender)
    if case == "accs":
        # Винительный одушевлённый: для фамилий совпадает с родительным (кого?).
        grammemes.add("anim")
    inflected = parsed.inflect(grammemes) or parsed.inflect({case})
    if not inflected:
        for p in parses:
            inflected = p.inflect(grammemes) or p.inflect({case})
            if inflected:
                break
    if inflected and inflected.word.lower() != surname.lower():
        return match_original_case(surname, inflected.word)
    return surname
