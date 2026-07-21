"""Реестр налоговых органов (ФНС): выверенный юр-адрес по имени органа.

Источник — сгенерированный `fns_data.py` (из выгрузки ФНС). Модуль строит по нему
индексы и по имени налогового органа (в т.ч. в форме, собранной анализатором —
«ФНС России в лице Межрайонной ИФНС России № N по <регион>») возвращает адрес.

ПОЧЕМУ так, а не сравнение строк напрямую: в заявлении и в справочнике имя органа
пишется по-разному — падеж («в лице Межрайонн_ой_» vs справочник «Межрайонн_ая_»),
пробелы вокруг «№», скобочные пометки региона в справочнике. Поэтому матчим по
устойчивому ключу `(номер инспекции, стем-региона)` / `(УФНС, стем-региона)` /
`ФНС-центр`, а регион приводим к канону со стемингом падежных окончаний.

Загрузка ленивая и graceful: нет данных — функции возвращают None, пайплайн
продолжает работать на regex-фолбэке.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Гео-тип региона → канон. Ключи — начала слов (падежи схлопываются на \w*).
_GEO_CANON = (
    (re.compile(r"\bавтономн\w*\s+окру\w+"), "ао"),
    (re.compile(r"\bобласт\w*"), "обл"),
    (re.compile(r"\bреспублик\w*"), "респ"),
    (re.compile(r"\bкра[йяюеё]\w*"), "край"),
    (re.compile(r"\bокру\w+"), "ао"),
)
# Падежные окончания прилагательного-топонима: «ростовск_ой/ая/ому…» → «ростовск».
_ADJ_END = re.compile(r"(ск)(ая|ой|ий|ому|ом|ую|ого|ые|ыми|их|им)\b")


def _region_key(region: str) -> str:
    """Регион → устойчивый ключ, инвариантный к падежу/скобкам/гео-типу.

    «Ростовской области» и «Ростовская область» → «ростовск обл»;
    «Республике Башкортостан» → «респ башкортостан». Скобочные пометки
    справочника («(перекод. 2004 …)») вырезаются."""
    r = (region or "").lower().replace("ё", "е")
    r = re.sub(r"\([^)]*\)", " ", r)          # убрать скобочные пометки справочника
    r = re.sub(r"[«»\"']", " ", r)
    r = re.sub(r"\s+", " ", r).strip(" .,-")
    for rx, canon in _GEO_CANON:
        r = rx.sub(canon, r)
    r = _ADJ_END.sub(r"\1", r)
    return re.sub(r"\s+", " ", r).strip()

_KEY_CENTER: Tuple = ("center",)

# Тип населённого пункта в компоненте адреса справочника («Ростов-на-Дону г», «Вохма п»).
_LOCALITY = re.compile(r"^(.+?)\s+(?:г|гор|пгт|рп|п|с|д|х|ст-ца|аул)\.?$", re.IGNORECASE)


def _region_base_and_key(region_tail: str) -> Tuple[str, bool]:
    """«Ростовской области в Тарасовском районе» → ключ базового региона
    «ростовск обл» + флаг is_base=False (это ТОРМ). Базовая форма («Ростовской
    области») → is_base=True. Локус «в <город/район>» отсекаем — он различается
    городом, а не регионом, поэтому все ТОРМ одного номера кладём под один ключ."""
    parts = re.split(r"\s+в\s+", region_tail, maxsplit=1)
    return _region_key(parts[0]), (len(parts) == 1)


def _locality(address: str) -> str:
    """Город/нас.пункт из адреса справочника (для дизамбигуации по подсказке)."""
    for comp in address.split(","):
        m = _LOCALITY.match(comp.strip())
        if m:
            return m.group(1).strip().lower().replace("ё", "е")
    return ""


@lru_cache(maxsize=1)
def _index() -> Dict[Tuple, list]:
    try:
        from fns_data import FNS_DATA
    except Exception as exc:  # нет данных — работаем на regex-фолбэке
        logger.warning(f"Реестр ФНС недоступен (fns_data не импортирован): {exc}")
        return {}
    idx: Dict[Tuple, list] = {}

    def _add(key: Tuple, rec: dict, is_base: bool) -> None:
        bucket = idx.setdefault(key, [])
        for i, (r, b) in enumerate(bucket):
            if r["ADDRESS"] == rec["ADDRESS"]:
                if is_base and not b:
                    bucket[i] = (r, True)
                return
        bucket.append((rec, is_base))

    for rec in FNS_DATA:
        naimk = (rec.get("NAIMK") or "").strip()
        if not rec.get("ADDRESS"):
            continue
        low = naimk.lower()
        if low == "фнс россии":
            _add(_KEY_CENTER, rec, True)
            continue
        # Инспекция с номером: «… № N по <регион>[ в <город/район>]» (МИ и ИФНС, в т.ч.
        # ТОРМ с префиксом «Территориально-обособленное … Межрайонной ИФНС …»).
        m = re.search(r"№\s*(\d+)\s+по\s+(.+)$", naimk)
        if m and ("межрайонн" in low or "ифнс" in low):
            reg_key, is_base = _region_base_and_key(m.group(2))
            _add(("mi", m.group(1), reg_key), rec, is_base)
            continue
        # Управление по субъекту: «УФНС/Управление … по <регион>».
        if low.startswith("уфнс") or low.startswith("управлени"):
            m = re.search(r"\bпо\s+(.+)$", naimk)
            if m:
                reg_key, is_base = _region_base_and_key(m.group(1))
                _add(("uf", reg_key), rec, is_base)
    return idx


def _pick(bucket: list, hint: str) -> Optional[str]:
    """Из кандидатов одного ключа выбрать адрес: по городу/индексу из подсказки-шапки,
    иначе — базовую запись (без локуса «в <районе>»), иначе — первую."""
    if not bucket:
        return None
    if len(bucket) == 1:
        return bucket[0][0]["ADDRESS"]
    hint_norm = re.sub(r"\s+", " ", (hint or "").lower().replace("ё", "е"))
    if hint_norm:
        # Сильный сигнал — совпал 6-значный индекс инспекции.
        for rec, _ in bucket:
            m = re.match(r"\s*(\d{6})", rec["ADDRESS"])
            if m and m.group(1) in hint_norm:
                return rec["ADDRESS"]
        # Иначе — по городу из адреса, если он назван в шапке.
        for rec, _ in bucket:
            city = _locality(rec["ADDRESS"])
            if city and len(city) >= 4 and city in hint_norm:
                return rec["ADDRESS"]
    # Подсказка не помогла — базовая запись (плоское «№ N по <регион>»).
    for rec, is_base in bucket:
        if is_base:
            return rec["ADDRESS"]
    return bucket[0][0]["ADDRESS"]


def resolve_address(name: str, hint: Optional[str] = None) -> Optional[str]:
    """Юр-адрес налогового органа по его имени (в т.ч. в форме, собранной
    анализатором) + подсказка-шапка `hint` для выбора среди ТОРМ одного номера.
    Возвращает выверенный ADDRESS из справочника или None."""
    if not name:
        return None
    idx = _index()
    if not idx:
        return None
    low = name.lower().replace("ё", "е")
    # Инспекция с номером — приоритетнее (самый конкретный ключ).
    m = re.search(r"№\s*(\d+)\s+по\s+(.+?)\s*$", name)
    if m:
        reg_key, _ = _region_base_and_key(m.group(2))
        addr = _pick(idx.get(("mi", m.group(1), reg_key), []), hint or "")
        if addr:
            return addr
    # Управление по субъекту.
    if "уфнс" in low or "управлени" in low:
        m = re.search(r"\bпо\s+(.+?)\s*$", name)
        if m:
            reg_key, _ = _region_base_and_key(m.group(1))
            addr = _pick(idx.get(("uf", reg_key), []), hint or "")
            if addr:
                return addr
    # Центральный аппарат ФНС (без инспекции/управления).
    if re.fullmatch(r"\s*фнс россии\s*", low):
        addr = _pick(idx.get(_KEY_CENTER, []), hint or "")
        if addr:
            return addr
    return None
