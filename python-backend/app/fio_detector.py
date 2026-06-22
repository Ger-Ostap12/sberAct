"""Извлечение ФИО должника/ответчика — гибрид: позиционный regex + Natasha-фолбэк.

Контекст: в заявлениях имя должника лежит сразу после заголовка блока
("Ответчик:", "Ответчики:", "Должник:") отдельной строкой, перед "Дата рождения":

Позиционный разбор берёт имя детерминированно (включая КАПС-написание и
множественное "Ответчики"). Natasha NER подключается ТОЛЬКО как запасной вариант,
если позиционный разбор не нашёл имя, — на КАПС-именах и фамилиях-омонимах
NER ненадёжна, поэтому она вторична.
Оффлайн: natasha грузится лениво; при её отсутствии модуль продолжает работать
на одном regex (graceful fallback).
"""
import re
import logging

logger = logging.getLogger(__name__)

# Заголовки блока должника/ответчика (учитываем "Ответчики" мн. ч.).
_HEADER_RE = r"(?:Ответчик(?:и)?|Должник|Заёмщик|Заемщик)"

# Слова, которые не могут быть частью ФИО (если встретились в строке — это не имя).
_STOP_WORDS = {
    "ИНН", "ОГРН", "ОГРНИП", "КПП", "СНИЛС", "ПАСПОРТ", "ПАО", "ООО", "АО",
    "ЗАО", "ОАО", "БАНК", "МЕСТО", "ДАТА", "АДРЕС", "ТЕЛЕФОН", "EMAIL",
    "ОБЯЗАТЕЛЬСТВА", "ОБЯЗАТЕЛЬСТВО", "СУД", "ИСТЕЦ", "ПРЕДСТАВИТЕЛЬ",
    "РОЖДЕНИЯ", "НАХОЖДЕНИЯ", "РЕГИСТРАЦИИ", "ПОРУЧИТЕЛЬ", "КРЕДИТОР",
    "ОТДЕЛЕНИЕ", "ФИЛИАЛ", "СОГЛАСНО", "ДОГОВОР", "СЕРИЯ", "ВЫДАН",
}

# Токен ФИО: слово с заглавной (Titlecase ИЛИ КАПС), допускаем дефис.
_NAME_TOKEN_RE = re.compile(r"^[А-ЯЁ][А-ЯЁа-яё]*(?:-[А-ЯЁ][А-ЯЁа-яё]*)?$")
# Девичья фамилия в скобках: "(КУЛЕМЗИНА)".
_PAREN_TOKEN_RE = re.compile(r"^\([А-ЯЁ][А-ЯЁа-яё\-]*\)$")


def _looks_like_fio(line: str) -> bool:
    """Проверяет, что строка похожа на ФИО физлица (2–5 слов, без цифр/стоп-слов)."""
    line = line.strip().strip(",")
    if not line or any(ch.isdigit() for ch in line):
        return False
    tokens = line.split()
    if not (2 <= len(tokens) <= 5):
        return False
    upper_tokens = {re.sub(r"[^А-ЯЁ]", "", t.upper()) for t in tokens}
    if upper_tokens & _STOP_WORDS:
        return False
    for tok in tokens:
        if not (_NAME_TOKEN_RE.match(tok) or _PAREN_TOKEN_RE.match(tok)):
            return False
    return True


def is_person_name(value: str) -> bool:
    """Публичная проверка: похоже ли значение на ФИО физлица."""
    return _looks_like_fio(value or "")


def _normalize_fio(line: str) -> str:
    """Приводит ФИО к виду 'Фамилия Имя Отчество' (Titlecase, с сохранением скобок/дефисов)."""
    line = line.strip().strip(",")
    out = []
    for tok in line.split():
        if tok.startswith("("):
            inner = tok[1:-1]
            out.append("(" + _titlecase_word(inner) + ")")
        else:
            out.append(_titlecase_word(tok))
    return " ".join(out)


def _titlecase_word(word: str) -> str:
    """Каждую часть слова (через дефис) с заглавной, остальное строчными."""
    return "-".join(p.capitalize() for p in word.split("-"))


def extract_debtor_name(text: str):
    """Возвращает ФИО должника/ответчика (Titlecase) или None.

    1) Позиционный разбор: первая «похожая на ФИО» строка после заголовка блока.
    2) Если не нашлось — Natasha NER по окну блока (запасной вариант).
    """
    if not text:
        return None

    # 1. Позиционный разбор: строка сразу после "Ответчик(и):/Должник:".
    for m in re.finditer(rf"{_HEADER_RE}\s*:?\s*\n+\s*([^\n]+)", text, re.IGNORECASE):
        candidate = m.group(1).strip()
        if _looks_like_fio(candidate):
            name = _normalize_fio(candidate)
            logger.info(f"ФИО должника (позиционно): {name}")
            return name

    # 2. Natasha-фолбэк по окну после первого заголовка блока.
    header_match = re.search(_HEADER_RE + r"\s*:?", text, re.IGNORECASE)
    if header_match:
        window = text[header_match.end(): header_match.end() + 300]
        name = _natasha_person(window)
        if name:
            logger.info(f"ФИО должника (Natasha-фолбэк): {name}")
            return name

    return None


def _debtor_block(text: str) -> str:
    """Возвращает запись ТОЛЬКО основного должника (от его имени до его адреса).

    Скоуп критичен: в блоке «Ответчики:» бывает несколько со-ответчиков, а ниже —
    представитель истца со своим СНИЛС/паспортом. Реквизиты основного должника
    (дата/место рождения, СНИЛС) лежат между его именем и его «Адрес регистрации»;
    данные следующих лиц (вторая «Дата рождения» и далее) сюда попадать не должны.
    """
    m = re.search(_HEADER_RE + r"\s*:", text, re.IGNORECASE)
    if not m:
        return ""
    rest = text[m.end():]

    # Конец записи основного должника: начало следующего лица или тела документа.
    # Берём позицию ВТОРОЙ «Дата рождения» (= следующий со-ответчик) и иные маркеры.
    stops = []
    births = [mm.start() for mm in re.finditer(r"Дата\s+рождения", rest, re.IGNORECASE)]
    if len(births) >= 2:
        stops.append(births[1])
    body = re.search(
        r"\n\s*(?:Цена\s+иска|Госпошлин|При\s+определении|ИСКОВОЕ|ЗАЯВЛЕНИЕ|ПРОСИТ|"
        r"Истец|Кредитор|Представитель|Третьи?\s+лиц|Согласно|Публичное\s+акционерное|"
        r"Требовани)",
        rest, re.IGNORECASE,
    )
    if body:
        stops.append(body.start())
    end = min(stops) if stops else min(len(rest), 600)
    return rest[:end]


def _find_birthdate(block: str):
    """Ищет дату рождения в двух форматах и возвращает 'ДД.ММ.ГГГГ' или None.

    Поддерживает:
      - «Дата рождения: 01.01.1990», «д.р. 01.01.1990», «д/р: 01.01.1990», «др» (префикс);
      - «01.01.1990 г.р.», «01.01.1990 г/р», «01.01.1990 гр», «01.01.1990 года рождения» (суффикс).
    Отсекает календарно невозможные даты.
    """
    # Префиксные формы: «Дата рождения», «д.р.», «д/р», «др».
    m = re.search(
        r"(?:Дата\s+рождения|\bд\s*[./]?\s*р\s*\.?)[:\s]*(\d{1,2})[.,](\d{1,2})[.,](\d{4})",
        block, re.IGNORECASE,
    )
    if not m:
        # Суффиксные формы: «… г.р.», «… г/р», «… гр», «… года рождения».
        m = re.search(
            r"(\d{1,2})[.,](\d{1,2})[.,](\d{4})\s*(?:г\s*[./]?\s*р\s*\.?|года?\s+рождения)",
            block, re.IGNORECASE,
        )
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
        return f"{day:02d}.{month:02d}.{year}"
    return None


def extract_debtor_details(text: str) -> dict:
    """Извлекает реквизиты должника-физлица из его блока: дата/место рождения, СНИЛС.

    Возвращает словарь только с найденными полями (ключи: birthDate, birthPlace, snils).
    Пустые значения не добавляются, чтобы не перетирать данные из других источников.
    """
    block = _debtor_block(text)
    if not block:
        return {}
    details = {}

    bd = _find_birthdate(block)
    if bd:
        details["birthDate"] = bd

    m = re.search(r"Место\s+рождения[:\s]*([^\n]+)", block, re.IGNORECASE)
    if m:
        place = m.group(1).strip().rstrip(",;")
        if place:
            details["birthPlace"] = place

    m = re.search(r"СНИЛС[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2})", block, re.IGNORECASE)
    if m:
        details["snils"] = m.group(1).strip()

    # ИНН должника — строго из его записи (иначе жадный поиск берёт ИНН банка-истца).
    inn_cands = [re.sub(r"\D", "", c) for c in re.findall(r"ИНН[:\s]*([0-9\s]{10,12})", block, re.IGNORECASE)]
    inn_cands = [c for c in inn_cands if 10 <= len(c) <= 12]
    if inn_cands:
        from requisites_validation import is_valid_inn
        details["inn"] = next((c for c in inn_cands if is_valid_inn(c)), inn_cands[0])

    return details


def _full_respondents_block(text: str) -> str:
    """Весь блок ответчиков/должников (все со-ответчики) — до следующего раздела."""
    m = re.search(_HEADER_RE + r"\s*:", text, re.IGNORECASE)
    if not m:
        return ""
    rest = text[m.end():]
    stop = re.search(
        r"\n\s*(?:Цена\s+иска|Госпошлин|При\s+определении|ИСКОВОЕ|ЗАЯВЛЕНИЕ|ПРОСИТ|"
        r"Истец|Кредитор|Представитель|Третьи?\s+лиц|Финансов\w+\s+управляющ|"
        r"Согласно|Публичное\s+акционерное|Требовани)",
        rest, re.IGNORECASE,
    )
    return rest[: stop.start()] if stop else rest[:2000]


# Маркер даты рождения сразу после строки-ФИО (= начало записи лица).
_BIRTH_MARKER_RE = re.compile(
    r"(?:Дата\s+рождения|\bд\s*[./]?\s*р\b|\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*(?:г\s*[./]?\s*р|года?\s+рождения))",
    re.IGNORECASE,
)


def _strip_address_label(addr: str) -> str:
    """Срезает ведущую метку адреса («Адрес регистрации: …» → «…»)."""
    return re.sub(
        r"^\s*(?:Адрес(?:\s+регистрации|\s+проживания|\s+места\s+жительства)?|"
        r"Место\s+(?:жительства|регистрации|нахождения)|"
        r"Зарегистрирован\w*(?:\s+по\s+адресу)?)\s*[:\-]?\s*",
        "", addr, flags=re.IGNORECASE,
    ).strip()


def _parse_debtor_record(rec_text: str):
    """Разбирает запись одного должника: name, birthDate, birthPlace, snils, inn, address."""
    lines = [l.strip() for l in rec_text.split("\n") if l.strip()]
    if not lines or not _looks_like_fio(lines[0]):
        return None
    d = {"name": _normalize_fio(lines[0])}

    bd = _find_birthdate(rec_text)
    if bd:
        d["birthDate"] = bd

    m = re.search(r"Место\s+рождения[:\s]*([^\n]+)", rec_text, re.IGNORECASE)
    if m:
        place = m.group(1).strip().rstrip(",;")
        if place:
            d["birthPlace"] = place

    m = re.search(r"СНИЛС[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2})", rec_text, re.IGNORECASE)
    if m:
        d["snils"] = m.group(1).strip()

    inn_cands = [re.sub(r"\D", "", c) for c in re.findall(r"ИНН[:\s]*([0-9\s]{10,12})", rec_text, re.IGNORECASE)]
    inn_cands = [c for c in inn_cands if 10 <= len(c) <= 12]
    if inn_cands:
        from requisites_validation import is_valid_inn
        d["inn"] = next((c for c in inn_cands if is_valid_inn(c)), inn_cands[0])

    # Адрес регистрации: строка-метка + возможное продолжение до конца записи.
    addr_m = re.search(
        r"(?:Адрес\s+регистрации|Адрес\s+проживания|Адрес\s+места\s+жительства|"
        r"Место\s+жительства|Адрес)[:\s]*([\s\S]+)$",
        rec_text, re.IGNORECASE,
    )
    if addr_m:
        addr = re.sub(r"\s*\n\s*", " ", addr_m.group(1)).strip()
        # Обрезаем хвост, если в адрес попали последующие метки (телефон и т.п.).
        addr = re.split(r"\s*(?:Контактный\s+телефон|Телефон|E-?mail|СНИЛС|ИНН)[:\s]", addr, 1, re.IGNORECASE)[0]
        addr = _strip_address_label(addr).strip().rstrip(",;")
        if addr and len(addr) >= 8:
            d["address"] = addr

    return d


def extract_debtors(text: str) -> list:
    """Извлекает список должников из блока «Ответчики:/Должник:».

    Запись лица начинается со строки-ФИО, за которой (в пределах двух непустых строк)
    идёт маркер даты рождения. Возвращает список словарей с реквизитами каждого
    должника. Для одиночного должника — список из одного элемента.
    """
    block = _full_respondents_block(text)
    if not block:
        return []
    lines = block.split("\n")

    # Индексы строк-ФИО, начинающих запись (за ФИО следует дата рождения).
    starts = []
    nonempty_after = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or not _looks_like_fio(s):
            continue
        # Смотрим следующие до двух непустых строк на маркер даты рождения.
        window = []
        for j in range(i + 1, min(i + 4, len(lines))):
            t = lines[j].strip()
            if t:
                window.append(t)
            if len(window) >= 2:
                break
        if any(_BIRTH_MARKER_RE.search(w) for w in window):
            starts.append(i)

    records = []
    if starts:
        for k, idx in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else len(lines)
            records.append("\n".join(lines[idx:end]))
    else:
        # Фолбэк: одиночный должник без явной даты рождения (ИП/ЮЛ) —
        # первая строка-ФИО до конца блока.
        for i, line in enumerate(lines):
            if _looks_like_fio(line.strip()):
                records.append("\n".join(lines[i:]))
                break

    debtors = []
    for rec in records:
        parsed = _parse_debtor_record(rec)
        if parsed:
            debtors.append(parsed)
    return debtors


def extract_third_party_details(text: str) -> dict:
    """Извлекает реквизиты ПЕРВОГО третьего лица: ИНН, дата рождения, СНИЛС.

    Возвращает словарь с ключами thirdPartyInn / thirdPartyBirthDate / thirdPartySnils
    (только найденные). Скоуп — запись первого третьего лица, до следующего лица
    или блока «Финансовый управляющий».
    """
    m = re.search(r"Треть[ие]\s+лиц\w*\s*:|Третье\s+лицо\s*:", text, re.IGNORECASE)
    if not m:
        return {}
    rest = text[m.end():]
    stop = re.search(
        r"\n\s*(?:ООО|АО|ПАО|ЗАО|ОАО|Финансов\w+\s+управляющ|Временн\w+\s+управляющ|"
        r"Кредитор|Истец|ПРОСИТ|ЗАЯВЛЕНИЕ|Согласно)",
        rest, re.IGNORECASE,
    )
    block = rest[: stop.start()] if stop else rest[:400]

    details = {}
    inn_candidates = [re.sub(r"\D", "", c) for c in re.findall(r"ИНН[:\s]*([0-9\s]{10,12})", block, re.IGNORECASE)]
    inn_candidates = [c for c in inn_candidates if 10 <= len(c) <= 12]
    if inn_candidates:
        from requisites_validation import is_valid_inn
        details["thirdPartyInn"] = next((c for c in inn_candidates if is_valid_inn(c)), inn_candidates[0])

    bd = _find_birthdate(block)
    if bd:
        details["thirdPartyBirthDate"] = bd

    sm = re.search(r"СНИЛС[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2})", block, re.IGNORECASE)
    if sm:
        details["thirdPartySnils"] = sm.group(1).strip()

    return details


# --- Natasha (ленивая инициализация, graceful при отсутствии) ---
_NATASHA = None  # кэш кортежа (segmenter, ner_tagger) или False при неудаче


def _ensure_natasha():
    global _NATASHA
    if _NATASHA is not None:
        return _NATASHA
    try:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger
        _NATASHA = (Segmenter(), NewsNERTagger(NewsEmbedding()))
    except Exception as exc:  # пакет/модель недоступны — работаем без NER
        logger.warning(f"Natasha недоступна, ФИО только по regex: {exc}")
        _NATASHA = False
    return _NATASHA


def _natasha_person(window: str):
    """Возвращает первое лицо (PER) из окна текста через Natasha или None."""
    nat = _ensure_natasha()
    if not nat:
        return None
    try:
        from natasha import Doc
        segmenter, ner_tagger = nat
        doc = Doc(window)
        doc.segment(segmenter)
        doc.tag_ner(ner_tagger)
        for span in doc.spans:
            if span.type == "PER" and _looks_like_fio(span.text):
                return _normalize_fio(span.text)
    except Exception as exc:
        logger.warning(f"Сбой Natasha NER: {exc}")
    return None
