# -*- coding: utf-8 -*-
"""Реестр банков-кредиторов и сопоставление наименований.

Вынесено из document_analyzer без изменений логики.
"""
import re
from typing import Dict, Optional

from org_normalizer import base_org_name


CREDITOR_BANKS = [
    {
        "names": ["пао сбербанк", "сбербанк", "сбер банк", "публичное акционерное общество сбербанк"],
        "inn": "7707083893",
        "ogrn": "1027700132195",
        "address": "117997, г. Москва, ул. Вавилова, д. 19",
    },
    {
        "names": ["ао альфа-банк", "альфа-банк", "альфа банк", "акционерное общество альфа-банк", "ао «альфа-банк»"],
        "inn": "7728168971",
        "ogrn": "1027700067328",
        "address": "107078, г. Москва, ул. Каланчевская, д. 27",
    },
    {
        "names": ["втб", "пао втб", "втб банк", "банк втб"],
        "inn": "7702070139",
        "ogrn": "1027739609391",
        "address": "190000, г. Санкт-Петербург, ул. Большая Морская, д. 29",
    },
    {
        "names": ["газпромбанк", "пао газпромбанк", "ао газпромбанк"],
        "inn": "7744001497",
        "ogrn": "1027700167110",
        "address": "117420, г. Москва, ул. Наметкина, д. 16, корп. 1",
    },
    {
        "names": ["открытие", "пао банк открытие", "банк открытие"],
        "inn": "7706092528",
        "ogrn": "1027700040690",
        "address": "127006, г. Москва, ул. Долгоруковская, д. 32, стр. 1",
    },
    {
        "names": ["тинькофф", "тинькофф банк", "ао тинькофф банк", "т-банк"],
        "inn": "7710140679",
        "ogrn": "1027700130275",
        "address": "123060, г. Москва, 1-й Волоколамский проезд, д. 10, стр. 1",
    },
    {
        "names": ["росбанк", "ао росбанк", "банк росбанк"],
        "inn": "7736207543",
        "ogrn": "1027739460737",
        "address": "115184, г. Москва, ул. Малая Ордынка, д. 50",
    },
    {
        "names": ["райффайзенбанк", "ао райффайзенбанк"],
        "inn": "7744000302",
        "ogrn": "1027700159648",
        "address": "119049, г. Москва, ул. Тропарева, д. 12",
    },
    {
        "names": ["совкомбанк", "пао совкомбанк", "ао совкомбанк"],
        "inn": "7707082843",
        "ogrn": "1027700137116",
        "address": "156000, Костромская обл., г. Кострома, ул. Советская, д. 58",
    },
    {
        "names": ["юни кредит банк", "юникредит", "ао юни кредит банк"],
        "inn": "7750006482",
        "ogrn": "1027700057464",
        "address": "119034, г. Москва, Пречистенская наб., д. 9",
    },
]


def _normalize_creditor_name_for_match(name: str) -> str:
    """Нормализация названия кредитора для сопоставления с реестром."""
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"[«»\"\"\'\-–—]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _match_creditor_registry(creditor_name: str) -> Optional[Dict[str, str]]:
    """Ищет кредитора в реестре по названию. Возвращает dict с inn, ogrn, address или None.

    Матчит по двум нормализациям (аддитивно, без потери прежних совпадений):
      1) прежняя _normalize_creditor_name_for_match (lower + снятие кавычек/дефисов);
      2) base_org_name из org_normalizer — раскрывает полные правовые формы
         («Публичное акционерное общество «Сбербанк России»» -> «сбербанк»),
         поэтому полные/кавычечные варианты тоже попадают в реестр.
    """
    candidates = []
    norm = _normalize_creditor_name_for_match(creditor_name)
    if norm and len(norm) >= 3:
        candidates.append(norm)
    base = base_org_name(creditor_name)
    if base and len(base) >= 3 and base not in candidates:
        candidates.append(base)
    if not candidates:
        return None
    for bank in CREDITOR_BANKS:
        for alias in bank["names"]:
            for cand in candidates:
                if alias in cand or cand in alias:
                    return {"inn": bank["inn"], "ogrn": bank["ogrn"], "address": bank["address"]}
    return None

