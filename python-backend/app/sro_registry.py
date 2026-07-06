# -*- coding: utf-8 -*-
"""Реестр СРО арбитражных управляющих: сопоставление упоминания организации из
текста заявления с каноничной записью справочника `sro_data.py` и выдача её
полного наименования (`NAIM_FULL`).

Зачем: в заявлениях СРО пишут по-разному — короткой аббревиатурой («ПАУ ЦФО»),
с кавычками-ёлочками («Ассоциация МСРО «Содействие»»), с хвостом ИНН/адреса. В акт
нужно каноничное полное имя. Матч — по нормализованному короткому имени (`NAIMK`)
и по отличительному токену в кавычках (напр. «Содействие», «ДЕЛО»), устойчиво к
кавычкам/регистру/ё-е/пунктуации. Чистая функция: строка → NAIM_FULL | None.
"""
import re
from typing import Dict, List, Optional

from sro_data import SRO_DATA


def _norm(s: str) -> str:
    """Каноничная форма для сравнения: нижний регистр, ё→е, кавычки/пунктуация → пробел."""
    if not s:
        return ""
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^0-9a-zа-я]+", " ", s)  # всё, кроме букв/цифр → пробел (кавычки, тире, точки)
    return re.sub(r"\s+", " ", s).strip()


# Предрасчёт нормализованного индекса (модуль грузится один раз).
_INDEX: List[Dict[str, str]] = [
    {"full": e["NAIM_FULL"], "naimk_n": _norm(e["NAIMK"]), "full_n": _norm(e["NAIM_FULL"])}
    for e in SRO_DATA
]

# «Служебные» слова — не считаем их отличительным токеном организации.
_STOP_TOKENS = {"сро", "ау", "пау", "мсро", "сау", "самро", "союз", "ассоциация", "организация"}


def _quoted_tokens(s: str) -> List[str]:
    """Отличительные наименования в кавычках («Содействие», "ДЕЛО»)."""
    return [t.strip() for t in re.findall(r"[«\"“„'']([^«»\"“”„'']+)[»\"”'']", s) if t.strip()]


def _word_in(token: str, hay: str) -> bool:
    return bool(re.search(r"\b" + re.escape(token) + r"\b", hay))


def resolve_sro(raw: Optional[str]) -> Optional[str]:
    """Возвращает NAIM_FULL записи СРО, наиболее соответствующей `raw`, или None.

    Слои (по убыванию строгости): точное совпадение NAIMK → NAIMK как подстрока
    (в любую сторону) → отличительный токен в кавычках присутствует в NAIMK/NAIM_FULL.
    При неоднозначности — максимум пересечения слов с NAIMK.
    """
    if not raw:
        return None
    rn = _norm(raw)
    if not rn:
        return None

    # 1) Точное совпадение по короткому имени.
    for e in _INDEX:
        if e["naimk_n"] and e["naimk_n"] == rn:
            return e["full"]

    # 2) NAIMK — подстрока raw или наоборот (снимает префикс «СРО », хвост ИНН/адреса).
    cand = [e for e in _INDEX if e["naimk_n"] and (e["naimk_n"] in rn or rn in e["naimk_n"])]
    if len(cand) == 1:
        return cand[0]["full"]

    # 3) Отличительный токен в кавычках (напр. «Содействие», «ДЕЛО»).
    toks = [t for t in (_norm(x) for x in _quoted_tokens(raw)) if len(t) >= 4 and t not in _STOP_TOKENS]
    if toks:
        tokmatch = [
            e for e in _INDEX
            if any(_word_in(t, e["naimk_n"]) or _word_in(t, e["full_n"]) for t in toks)
        ]
        pool = [e for e in tokmatch if e in cand] or tokmatch
        if len(pool) == 1:
            return pool[0]["full"]
        if pool:
            return max(pool, key=lambda e: len(set(e["naimk_n"].split()) & set(rn.split())))["full"]

    if cand:
        return max(cand, key=lambda e: len(set(e["naimk_n"].split()) & set(rn.split())))["full"]
    return None
