# -*- coding: utf-8 -*-
"""Второстепенный NLP-слой на Natasha: подчистка/добивание значений, которые
основной regex не смог извлечь целиком.

Роль модуля — ВСПОМОГАТЕЛЬНАЯ. Ядро разбора остаётся на детерминированных
label-anchored регулярках; Natasha подключается только как fallback:
- адрес обрезан/не найден → `complete_address` достраивает по окну роли;
- организация не дотянута → `find_org` (NER ORG) внутри окна роли;
- дата обязательства не распознана → `find_date` (DatesExtractor) последним слоем.

Всё работает по ОКНУ, которое уже ограничила метка роли (чей это адрес/имя),
и возвращает VERBATIM-срез исходного текста (никакой нормализации Natasha —
«текст как в документе»), поэтому роль/позицию определяет вызывающий код, а не NER.

Инициализация ленивая и graceful: если пакет/модель недоступны (или окружение
сломано — напр. отсутствует `pkg_resources`), функции возвращают None, и пайплайн
продолжает работать на regex. Модели pymorphy2 при этом греметь deprecation-warning —
подавляем, чтобы не засорять лог.
"""
from __future__ import annotations

import logging
import re
import warnings
from typing import Optional

logger = logging.getLogger(__name__)

# Кэш ленивых синглтонов. None — ещё не пробовали; False — попытка провалилась.
_YARGY = None   # (MorphVocab, AddrExtractor, DatesExtractor)
_NER = None     # (Segmenter, NewsNERTagger)


def _ensure_yargy():
    """MorphVocab + yargy-экстракторы (Addr/Dates). Тянут pymorphy2 → pkg_resources."""
    global _YARGY
    if _YARGY is not None:
        return _YARGY
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from natasha import MorphVocab, AddrExtractor, DatesExtractor
            mv = MorphVocab()
            _YARGY = (mv, AddrExtractor(mv), DatesExtractor(mv))
    except Exception as exc:  # пакет/окружение недоступны — работаем без NLP
        logger.warning(f"Natasha yargy-экстракторы недоступны, работаем на regex: {exc}")
        _YARGY = False
    return _YARGY


def _ensure_ner():
    """Segmenter + NewsNERTagger для ORG/PER. NER не зависит от pkg_resources."""
    global _NER
    if _NER is not None:
        return _NER
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from natasha import Segmenter, NewsEmbedding, NewsNERTagger
            _NER = (Segmenter(), NewsNERTagger(NewsEmbedding()))
    except Exception as exc:
        logger.warning(f"Natasha NER недоступен, работаем на regex: {exc}")
        _NER = False
    return _NER


def complete_address(window: str) -> Optional[str]:
    """Собирает непрерывный адрес из окна и возвращает VERBATIM-срез окна.

    AddrExtractor возвращает адрес ПОКОМПОНЕНТНО (индекс/регион/город/улица/дом/кв),
    поэтому берём первый «прогон» подряд идущих компонентов (разрыв между ними —
    только разделители «, » длиной ≤ порога) и режем исходное окно от начала первого
    до конца последнего компонента. Так сохраняем ровно тот текст, что в документе
    (включая нестандартные хвосты между распознанными частями).

    Возвращает None, если Natasha недоступна или адрес не найден.
    """
    if not window or not window.strip():
        return None
    y = _ensure_yargy()
    if not y:
        return None
    _mv, addr, _dates = y
    try:
        matches = sorted(addr(window), key=lambda m: m.start)
    except Exception as exc:
        logger.warning(f"Сбой AddrExtractor: {exc}")
        return None
    if not matches:
        return None
    # Первый непрерывный прогон компонентов: разрыв допускаем не больше «, » + пробелы.
    _GAP = 4
    run_start = matches[0].start
    run_stop = matches[0].stop
    run_len = 1
    for m in matches[1:]:
        if m.start - run_stop <= _GAP:
            run_stop = m.stop
            run_len += 1
        else:
            break
    result = window[run_start:run_stop].strip().rstrip(" ,;.")
    # Осмысленный адрес — минимум с буквами (иначе это одинокий индекс/дом).
    if not re.search(r"[А-Яа-яЁё]{3}", result):
        return None
    # Отсекаем одиночный компонент-шум (AddrExtractor помечает адресом даже
    # одинокое существительное в род. падеже, напр. «Кирова»): требуем либо
    # ≥2 склеенных компонента, либо явный 6-значный индекс в результате.
    if run_len < 2 and not re.search(r"\b\d{6}\b", result):
        return None
    return result


def find_orgs(window: str) -> list:
    """Все организации (NER ORG) в окне — список VERBATIM-срезов в порядке появления.

    Пустой список, если Natasha недоступна или ORG не найдено. Фильтрацию/выбор
    нужного кандидата оставляем вызывающему коду (роль решает он, не NER)."""
    if not window or not window.strip():
        return []
    n = _ensure_ner()
    if not n:
        return []
    out = []
    try:
        from natasha import Doc
        segmenter, ner_tagger = n
        doc = Doc(window)
        doc.segment(segmenter)
        doc.tag_ner(ner_tagger)
        for span in doc.spans:
            if span.type == "ORG":
                val = re.sub(r"\s+", " ", window[span.start:span.stop]).strip().rstrip(" ,;")
                if len(val) >= 3:
                    out.append(val)
    except Exception as exc:
        logger.warning(f"Сбой Natasha NER ORG: {exc}")
    return out


def find_org(window: str) -> Optional[str]:
    """Первая организация (NER ORG) в окне — VERBATIM-срез. None, если нет/недоступно."""
    orgs = find_orgs(window)
    return orgs[0] if orgs else None


def find_date(window: str) -> Optional[str]:
    """Первая дата (DatesExtractor) в окне — VERBATIM-срез. None, если нет/недоступно."""
    if not window or not window.strip():
        return None
    y = _ensure_yargy()
    if not y:
        return None
    _mv, _addr, dates = y
    try:
        matches = sorted(dates(window), key=lambda m: m.start)
    except Exception as exc:
        logger.warning(f"Сбой DatesExtractor: {exc}")
        return None
    for m in matches:
        val = window[m.start:m.stop].strip()
        if re.search(r"\d", val):
            return val
    return None
