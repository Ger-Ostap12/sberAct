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
from typing import Any, Optional, Tuple

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
    "ИСКОВОЕ", "ЗАЯВЛЕНИЕ",
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


# Несовершеннолетний со-ответчик записывается как «<ФИО ребёнка> в лице законного
# представителя <ФИО представителя>». Такая строка не проходит _looks_like_fio
# (лишние слова-связки), поэтому распознаём её отдельным паттерном — вся строка
# целиком идёт в поле ФИО ответчика (по требованию: связка сохраняется как есть).
_NAME_SEQ_RE = r"[А-ЯЁ][А-ЯЁа-яё]*(?:-[А-ЯЁ][А-ЯЁа-яё]*)?(?:\s+[А-ЯЁ][А-ЯЁа-яё]*(?:-[А-ЯЁ][А-ЯЁа-яё]*)?){1,3}"
_LEGAL_REP_RE = re.compile(
    rf"^(?P<child>{_NAME_SEQ_RE})\s+[Вв]\s+лице\s+законного\s+представител\w*\s+"
    rf"(?P<guardian>{_NAME_SEQ_RE})\s*$"
)


def _represented_minor_name(line: str):
    """Если строка — «<ребёнок> в лице законного представителя <ФИО>», возвращает
    нормализованную строку целиком (обе части Titlecase); иначе None."""
    m = _LEGAL_REP_RE.match(line.strip().strip(","))
    if not m:
        return None
    child = _normalize_fio(m.group("child"))
    guardian = _normalize_fio(m.group("guardian"))
    return f"{child} в лице законного представителя {guardian}"


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

    for hdr in (r"(?:Ответчик(?:и)?|Должник)", r"(?:Заёмщик|Заемщик)"):
        for m in re.finditer(rf"{hdr}\s*:?[ \t]*\n*[ \t]*([^\n]+)", text, re.IGNORECASE):
            candidate = m.group(1).strip()
            # Срезаем канцелярский префикс строки «На № …» (поле бланка перед ФИО):
            # «На № Базов Георгий Николаевич» -> «Базов Георгий Николаевич».
            candidate = re.sub(r"^(?:На\s*№|№)\s*", "", candidate).strip()
            # Реквизиты, приписанные к имени в скобках, — не часть имени:
            # «Буниатян Алина Генриковна (дата рождения: 28.03.2001, СНИЛС …)».
            # Без этого обрезка ниже режет по первой ЦИФРЕ, оставляя
            # «… (дата рождения:», кандидат отклоняется, и ФИО достаёт
            # Natasha-фолбэк — уже БЕЗ ФАМИЛИИ.
            #
            # Скобку с РОЛЬЮ («ИП БАЗОВ ГЕОРГИЙ НИКОЛАЕВИЧ (ДОЛЖНИК)») трогать
            # нельзя: там позиционный разбор осознанно отказывается, и имя даёт
            # паттерн — в том виде и регистре, как в документе.
            candidate = re.sub(
                r"\s*\((?=[^)]*(?:дата\s+рождения|место\s+рождения|\bИНН\b|\bСНИЛС\b|"
                r"\bОГРН\w*|паспорт)).*$",
                "", candidate, flags=re.IGNORECASE,
            ).strip()
            candidate = re.split(
                r"\t|\s{2,}|\bИНН\b|\bСНИЛС\b|\bОГРН\w*|\d",
                candidate, maxsplit=1, flags=re.IGNORECASE,
            )[0].strip()
            if _looks_like_fio(candidate):
                name = _normalize_fio(candidate)
                logger.info(f"ФИО должника (позиционно): {name}")
                return name

    # Natasha-фолбэк по окну после первого заголовка блока.
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


# Мягкий перенос абзаца: узкая шапка (колонка в 30-45 символов) рвёт значение
# посреди фразы, и признак разрыва — ПРОБЕЛ в конце строки. Жёсткий разрыв (новое
# поле с новой строки) пробелом не оканчивается. Запрет на строку-метку
# («Паспорт:», «ИНН:») и потолок в 3 строки страхуют от случайного пробела.
_SOFT_WRAP = (
    r"(?:[^\n]*[ \t]\n(?![ \t]*[А-ЯЁA-Z][^\n:]{1,30}:)){0,3}"
)

# «Место рождения» и обиходное «уроженец(ка)» — одна и та же метка.
_BIRTHPLACE_LABEL = r"(?:Место\s+рождения|Урожен(?:ец(?:\s*\(ка\))?|ка))"

# Место рождения перечисляется В ОДНОЙ СТРОКЕ с остальными реквизитами
# («… место рождения: гор. Новочеркасск …, СНИЛС …, ИНН …, адрес …»), поэтому
# значение обязано кончаться на первом же следующем реквизите, а не на конце
# строки — иначе в поле уезжает вся запись должника.
_BIRTHPLACE_STOP_RE = re.compile(
    r"[,;]?\s*(?:СНИЛС|ИНН|ОГРНИП|ОГРН|КПП|Паспорт|Адрес|Дата\s+рождения|"
    r"Место\s+жительства|Место\s+регистрации|Тел)\b",
    re.IGNORECASE,
)


def _clean_birthplace(value: str) -> str:
    """Обрезает место рождения по первому реквизиту и снимает хвостовую пунктуацию."""
    place = re.sub(r"\s+", " ", value).strip()
    place = _BIRTHPLACE_STOP_RE.split(place, maxsplit=1)[0]
    return place.strip().rstrip(",;)").strip()


# Паспорт пишут ДЕСЯТКОМ способов, и каждый — в своём заявлении корпуса.
# Прежний паттерн понимал 8 написаний из 12 и спотыкался на четырёх:
#   «Паспорт: серия 60 24, №940297»   — запятая между серией и номером;
#   «паспорт: серия: 60 14 номер: 691850» — двоеточие после «серия»;
#   «паспорт: серия 60 23.№278902»    — точка вместо пробела;
#   «Паспорт: серия 60 05 № 561 928»  — пробел ВНУТРИ номера.
# Главной потерей была, однако, не форма записи, а ПРОВОДКА: разбор паспорта
# жил только в одной ветке, в `fields` и в карточку должника не попадал вовсе.
# `(?<!\d)`/`(?!\d)` не дают откусить кусок более длинного числа: без них
# «ИНН 612504512780» разобрался бы как серия 6125 номер 045127.
_PASSPORT_RE = re.compile(
    r"паспорт\w*(?:\s+данн\w+)?\s*:?\s*(?:серия\s*:?\s*)?"
    r"(?<!\d)(\d{2}\s?\d{2})\s*[.,;]?\s*(?:№|N|номер\s*:?)?\s*(\d{3}\s?\d{3})(?!\d)",
    re.IGNORECASE,
)


def find_passport(text: str):
    """Серия и номер паспорта из записи должника или None."""
    m = _PASSPORT_RE.search(text or "")
    if not m:
        return None
    return re.sub(r"\s", "", m.group(1)), re.sub(r"\s", "", m.group(2))


def _find_birthdate(block: str):
    """Ищет дату рождения в двух форматах и возвращает 'ДД.ММ.ГГГГ' или None.

    Поддерживает:
      - «Дата рождения: 01.01.1990», «д.р. 01.01.1990», «д/р: 01.01.1990», «др» (префикс);
      - «01.01.1990 г.р.», «01.01.1990 г/р», «01.01.1990 гр», «01.01.1990 года рождения»,
        «01.01.1990 года р.» (суффикс).
    Отсекает календарно невозможные даты.
    """
    # Префиксные формы: «Дата рождения», «д.р.», «д/р», «др».
    m = re.search(
        r"(?:Дата\s+рождения|\bд\s*[./]?\s*р\s*\.?)[:\s]*(\d{1,2})[.,](\d{1,2})[.,](\d{4})",
        block, re.IGNORECASE,
    )
    if not m:
        # Суффиксные формы: «… г.р.», «… г/р», «… гр», «… года рождения».
        # «года р.»: точка после «р» обязательна — иначе выражение цеплялось бы за
        # «… 2025 года районный суд» и подобные хвосты.
        m = re.search(
            r"(\d{1,2})[.,](\d{1,2})[.,](\d{4})\s*"
            r"(?:г\s*[./]?\s*р\s*\.?|года?\s+рождения|года?\s+р\s*\.)",
            block, re.IGNORECASE,
        )
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
        return f"{day:02d}.{month:02d}.{year}"
    return None


# ИНН РОВНО десять или двенадцать цифр подряд, без цифры следом.
#
# Класс [0-9\s]{10,12} глотал пробел и первую цифру почтового индекса со
# следующей строки: «ИНН 6162059094 344002, Ростовская область…» давало
# «61620590943». Двенадцать проверяем раньше десяти — у гражданина ИНН длиннее.
_INN_STRICT_RE = re.compile(r"ИНН[:\s\u2116]*(\d{12}|\d{10})(?!\d)", re.IGNORECASE)
# Запасной, терпимый к разрывам вёрстки («61 62 05 90 94»).
_INN_LOOSE_RE = re.compile(r"ИНН[:\s]*([0-9\s]{10,12})", re.IGNORECASE)


def _inn_candidates(text: str) -> list:
    """Кандидаты в ИНН из записи стороны: сначала строгие, потом терпимые."""
    строгие = _INN_STRICT_RE.findall(text or "")
    if строгие:
        return строгие
    цифры = [re.sub(r"\D", "", c) for c in _INN_LOOSE_RE.findall(text or "")]
    return [c for c in цифры if 10 <= len(c) <= 12]


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

    m = re.search(_BIRTHPLACE_LABEL + r"[:\s]*(" + _SOFT_WRAP + r"[^\n]+)",
                  block, re.IGNORECASE)
    if m:
        place = _clean_birthplace(m.group(1))
        if place:
            details["birthPlace"] = place

    m = re.search(r"СНИЛС[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2})", block, re.IGNORECASE)
    if m:
        details["snils"] = m.group(1).strip()

    pp = find_passport(block)
    if pp:
        details["passportSeries"], details["passportNumber"] = pp

    # ИНН должника — строго из его записи (иначе жадный поиск берёт ИНН банка-истца).
    inn_cands = _inn_candidates(block)
    if inn_cands:
        from requisites_validation import is_valid_inn
        details["inn"] = next((c for c in inn_cands if is_valid_inn(c)), inn_cands[0])

    # ОГРН/ОГРНИП должника — тоже строго из его записи.
    ogrn_m = re.search(r"ОГРНИП[:\s]*([0-9\s]{15})|ОГРН[:\s]*([0-9\s]{13})", block, re.IGNORECASE)
    if ogrn_m:
        ogrn_val = re.sub(r"\D", "", ogrn_m.group(1) or ogrn_m.group(2) or "")
        if len(ogrn_val) in (13, 15):
            details["ogrn"] = ogrn_val

    return details


def _full_respondents_block(text: str) -> str:
    """Весь блок ответчиков/должников (все со-ответчики) — до следующего раздела."""
    m = re.search(_HEADER_RE + r"\s*:", text, re.IGNORECASE)
    if not m:
        return ""
    rest = text[m.end():]
    stop = re.search(
        r"\n\s*(?:Цена\s+иска|Госпошлин|При\s+определении|ИСКОВОЕ|ЗАЯВЛЕНИЕ|ПРОСИТ|"
        # «Треть[иеё]\w* лиц» покрывает и «Третьи лица:», и «Третье лицо:» (иначе блок
        # ответчика заглатывал третьих лиц и брал их валидный ИНН).
        r"Истец|Кредитор|Представитель|Треть[иеё]\w*\s+лиц|Финансов\w+\s+управляющ|"
        r"Согласно|Публичное\s+акционерное|Требовани)",
        rest, re.IGNORECASE,
    )
    return rest[: stop.start()] if stop else rest[:2000]


# Маркер даты рождения сразу после строки-ФИО (= начало записи лица).
_BIRTH_MARKER_RE = re.compile(
    r"(?:Дата\s+рождения|\bд\s*[./]?\s*р\b|\d{1,2}[.,]\d{1,2}[.,]\d{4}\s*(?:г\s*[./]?\s*р|года?\s+рождения))",
    re.IGNORECASE,
)

# Подписи СОБСТВЕННЫХ полей лица — второй признак начала записи.
#
# Дата рождения одна в этой роли не справляется: у должника её может не быть, и
# тогда запись не открывается — предыдущая карточка заглатывает его имя в свой
# адрес, своей карточки он лишается, а все следующие съезжают на одного.
# Замер на 10 должниках, у восьмого нет даты рождения: 9 карточек вместо 10 и
# перепутанные поля у четверых.
#
# Берём только те подписи, что принадлежат САМОМУ лицу. «Дата государственной
# регистрации», «Размер требований» и «Госпошлина» сюда не входят: это поля
# кредитора и дела, они открыли бы запись на пустом месте.
_PARTY_FIELD_KEYS = ("inn", "ogrn", "ogrnip", "snils", "passport",
                     "birthDate", "birthPlace", "address")


def _party_field_marker_re():
    """Regex подписи собственного поля лица. Строится из реестра меток один раз."""
    global _PARTY_FIELD_MARKER_RE
    if _PARTY_FIELD_MARKER_RE is None:
        from label_synonyms import FIELD_LABELS, labels_alternation
        labels = sorted(
            {lbl for key in _PARTY_FIELD_KEYS for lbl in FIELD_LABELS[key]},
            key=len, reverse=True,
        )
        _PARTY_FIELD_MARKER_RE = re.compile(
            r"^\s*(?:" + labels_alternation(labels) + r")\s*:", re.IGNORECASE)
    return _PARTY_FIELD_MARKER_RE


_PARTY_FIELD_MARKER_RE = None


def _strip_address_label(addr: str) -> str:
    """Срезает ведущую метку адреса («Адрес регистрации: …» «…»)."""
    return re.sub(
        r"^\s*(?:Адрес(?:\s+регистрации|\s+проживания|\s+места\s+жительства)?|"
        r"Место\s+(?:жительства|регистрации|нахождения)|"
        r"Зарегистрирован\w*(?:\s+по\s+адресу)?)\s*[:\-]?\s*",
        "", addr, flags=re.IGNORECASE,
    ).strip()


def _parse_debtor_record(rec_text: str):
    """Разбирает запись одного должника: name, birthDate, birthPlace, snils, inn, address."""
    lines = [l.strip() for l in rec_text.split("\n") if l.strip()]
    if not lines:
        return None
    rep_name = _represented_minor_name(lines[0])
    if rep_name:
        d = {"name": rep_name}
    elif _looks_like_fio(lines[0]):
        d = {"name": _normalize_fio(lines[0])}
    else:
        return None

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

    pp = find_passport(rec_text)
    if pp:
        d["passportSeries"], d["passportNumber"] = pp

    inn_cands = _inn_candidates(rec_text)
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
        # Обрезаем хвост, если в адрес попали последующие метки (телефон/почта/реквизиты).
        addr = re.split(
            r"\s*(?:Контактн\w*\s+тел\w*\.?|Телефон|Тел\.?|E-?mail|Эл\.?\s*почт\w*|"
            # «Иной (известный) адрес проживания» — вторичный адрес, в основной не тянем.
            r"Ин[оы]\w*\s+(?:известн\w+\s+)?адрес|"
            r"СНИЛС|ИНН|ОГРН\w*|Паспорт|Дата\s+рождения)[:\s.]",
            addr, maxsplit=1, flags=re.IGNORECASE,
        )[0]
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
        if not s or not (_looks_like_fio(s) or _represented_minor_name(s)):
            continue
        # Смотрим следующие до двух непустых строк на маркер даты рождения.
        window = []
        for j in range(i + 1, min(i + 4, len(lines))):
            t = lines[j].strip()
            if t:
                window.append(t)
            if len(window) >= 2:
                break
        if any(_BIRTH_MARKER_RE.search(w) or _party_field_marker_re().match(w)
               for w in window):
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


_ORG_PREFIX_RE = re.compile(
    r"^(?:ИП|ООО|АО|ПАО|ЗАО|ОАО|Общество|Публичное|"
    # Казённые/бюджетные учреждения (напр. ФГКУ «Росвоенипотека» — третье лицо
    # по военной ипотеке): «Федеральное государственное казенное учреждение …».
    r"ФГКУ|ФГБУ|ФГУП|ГКУ|МКУ|МБУ|Федеральн\w+|Государственн\w+|Учреждени\w+|Управлени\w+)\b",
    re.IGNORECASE,
)


def _third_parties_block(text: str) -> str:
    """Весь блок третьих лиц — до управляющего/тела документа."""
    m = re.search(r"Треть[ие]\s+лиц\w*\s*:|Третье\s+лицо\s*:", text, re.IGNORECASE)
    if not m:
        return ""
    rest = text[m.end():]
    stop = re.search(
        r"\n\s*(?:Финансов\w+\s+управляющ|Временн\w+\s+управляющ|Конкурсн\w+\s+управляющ|Дело\s*№|ПРОШУ|ПРОСИТ|"
        r"Кредитор|Истец|Согласно|"
        # Тело искового: «Публичное акционерное общество "Сбербанк России"» (кавычки
        # прямые ИЛИ ёлочки), а также поля-бланка после блока третьих лиц.
        r"Публичное\s+акционерное\s+общество\s+[\"«]|Цена\s+иска|Госпошлин|При\s+определени|"
        r"ИСКОВОЕ|ЗАЯВЛЕНИЕ|$)",
        rest, re.IGNORECASE,
    )
    return rest[: stop.start()] if stop else rest[:800]


def _is_party_start(line: str) -> bool:
    """Строка начинает запись третьего лица: ФИО физлица или организация (ИП/ООО/…)."""
    s = line.strip()
    if not s:
        return False
    return bool(_ORG_PREFIX_RE.match(s)) or _looks_like_fio(s)


def _parse_party_record(rec_text: str):
    """Разбирает запись третьего лица: name, birthDate, address, inn, snils."""
    lines = [l.strip() for l in rec_text.split("\n") if l.strip()]
    if not lines or not _is_party_start(lines[0]):
        return None
    d = {"name": lines[0].rstrip(",;")}

    bd = _find_birthdate(rec_text)
    if bd:
        d["birthDate"] = bd

    m = re.search(r"СНИЛС[:\s]*(\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2})", rec_text, re.IGNORECASE)
    if m:
        d["snils"] = m.group(1).strip()

    # «ИНН 7704…» или совмещённая метка «ИНН/КПП 7704159488/771401001» (учреждения).
    inn_cands = [re.sub(r"\D", "", c) for c in re.findall(r"ИНН(?:\s*/\s*КПП)?[:\s]*([0-9\s]{10,12})", rec_text, re.IGNORECASE)]
    inn_cands = [c for c in inn_cands if 10 <= len(c) <= 12]
    if inn_cands:
        from requisites_validation import is_valid_inn
        d["inn"] = next((c for c in inn_cands if is_valid_inn(c)), inn_cands[0])

    ogrn_m = re.search(r"ОГРНИП[:\s]*([0-9\s]{15})|ОГРН[:\s]*([0-9\s]{13})", rec_text, re.IGNORECASE)
    if ogrn_m:
        ogrn_val = re.sub(r"\D", "", ogrn_m.group(1) or ogrn_m.group(2) or "")
        if len(ogrn_val) in (13, 15):
            d["ogrn"] = ogrn_val

    addr_m = re.search(
        r"(?:Адрес\s+регистрации|Адрес\s+проживания|Адрес\s+места\s+жительства|"
        r"Место\s+жительства|Адрес)[:\s]*([\s\S]+)$",
        rec_text, re.IGNORECASE,
    )
    if addr_m:
        addr = re.sub(r"\s*\n\s*", " ", addr_m.group(1)).strip()
        addr = re.split(
            r"\s*(?:Контактн\w*\s+тел\w*\.?|Телефон|Тел\.?|E-?mail|СНИЛС|ИНН|ОГРН\w*|Паспорт|Дата\s+рождения)[:\s.]",
            addr, maxsplit=1, flags=re.IGNORECASE,
        )[0]
        addr = _strip_address_label(addr).strip().rstrip(",;")
        if addr and len(addr) >= 8:
            d["address"] = addr

    return d


def extract_third_parties(text: str) -> list:
    """Извлекает список третьих лиц (физлица и организации) из блока «Третьи лица:».

    Запись начинается со строки-ФИО или организации (ИП/ООО/АО/ПАО/…) и идёт до
    следующей такой строки. Возвращает список словарей с реквизитами каждого лица.
    """
    block = _third_parties_block(text)
    if not block:
        return []
    out = []
    # Каждая метка «Третье лицо:» начинает новое лицо. При нормализации переносов
    # метка склеивается с наименованием на след. строке («Третье лицо: Управление…»),
    # из-за чего второе лицо не опознаётся как старт — поэтому режем блок ПО метке,
    # а внутри сегмента добираем несколько лиц под одной меткой «Третьи лица:».
    for seg in re.split(r"Треть[еи]\s+лиц\w*\s*:", block):
        lines = seg.split("\n")
        starts = [i for i, l in enumerate(lines) if _is_party_start(l)]
        for k, idx in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else len(lines)
            parsed = _parse_party_record("\n".join(lines[idx:end]))
            if parsed:
                out.append(parsed)
    return out

_HEIR_LABEL_RE = re.compile(
    r"^[ \t]*Наследник(?:и|а)?(?:\s+должника)?\s*:[ \t]*", re.IGNORECASE | re.MULTILINE
)
# Метки шапки, на которых запись наследника заканчивается (следующее поле бланка).
_HEIR_STOP_RE = re.compile(
    r"^[ \t]*(?:Должник|Заявитель|Кредитор|Истец|Ответчик|Треть[ие]\s+лиц|Третье\s+лицо|"
    r"Нотариус|Государственн\w*\s+пошлин|Общий\s+размер|Сумма\s+требован|Дело\s*№|"
    r"Арбитражный\s+суд|ЗАЯВЛЕНИЕ|ПРОШУ|ПРОСИТ|Финансов\w+\s+управляющ|Согласно)",
    re.IGNORECASE | re.MULTILINE,
)

_HEIR_FIO_RE = re.compile(
    r"^\s*([А-ЯЁ][А-ЯЁа-яё]+(?:-[А-ЯЁ][А-ЯЁа-яё]+)?(?:\s+[А-ЯЁ][А-ЯЁа-яё]+){1,2})\b"
)


def _heir_block(text: str, start: int) -> str:
    """Запись наследника: от метки до следующей метки шапки (или 400 символов)."""
    rest = text[start:]
    stop = _HEIR_STOP_RE.search(rest)
    return rest[: stop.start()] if stop else rest[:400]


def _parse_heir_record(rec_text: str):
    """Разбирает запись наследника: name + address. Возвращает None, если ФИО не распознано."""
    rec = re.sub(r"\s*\n\s*", " ", rec_text).strip()
    m = _HEIR_FIO_RE.match(rec)
    if not m:
        return None
    name = _normalize_fio(m.group(1))
    if not is_person_name(name):
        return None
    d = {"name": name}

    addr = rec[m.end():].strip().lstrip(",;–—-").strip()
    addr = _strip_address_label(addr).strip()
    # Хвост прозы/следующего поля отрезаем по тем же меткам, что и у третьих лиц.
    addr = re.split(
        r"\s*(?:Контактн\w*\s+тел\w*\.?|Телефон|Тел\.?|E-?mail|СНИЛС|ИНН|ОГРН\w*|Паспорт|"
        r"Дата\s+рождения|Государственн\w*\s+пошлин|Общий\s+размер)[:\s.]",
        addr, maxsplit=1, flags=re.IGNORECASE,
    )[0]
    addr = addr.strip().rstrip(",;")
    if addr and len(addr) >= 8:
        d["address"] = addr
    return d


def extract_heirs(text: str) -> list:
    """Извлекает наследников умершего должника из шапки заявления.

    Наследников может быть несколько — каждый под своей меткой «Наследник:».
    Возвращает список словарей {name, address?}; пустой список — валидный
    результат (в заявлении наследник может быть не назван).
    """
    if not text:
        return []
    out = []
    seen = set()
    for m in _HEIR_LABEL_RE.finditer(text):
        parsed = _parse_heir_record(_heir_block(text, m.end()))
        if not parsed:
            continue
        key = parsed["name"].casefold()
        if key in seen:  # одно и то же лицо в шапке и в приложении к заявлению
            continue
        seen.add(key)
        out.append(parsed)
    return out


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
        r"\n\s*(?:ООО|АО|ПАО|ЗАО|ОАО|Финансов\w+\s+управляющ|Временн\w+\s+управляющ|Конкурсн\w+\s+управляющ|"
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



_NATASHA: Optional[Tuple[Any, Any]] = None  # кэш кортежа (segmenter, ner_tagger)
_NATASHA_LOAD_FAILED = False  # чтобы не повторять неудачную загрузку


def _ensure_natasha() -> Optional[Tuple[Any, Any]]:
    global _NATASHA, _NATASHA_LOAD_FAILED
    if _NATASHA is not None or _NATASHA_LOAD_FAILED:
        return _NATASHA
    try:
        from natasha import Segmenter, NewsEmbedding, NewsNERTagger
        _NATASHA = (Segmenter(), NewsNERTagger(NewsEmbedding()))
    except Exception as exc:  # пакет/модель недоступны — работаем без NER
        logger.warning(f"Natasha недоступна, ФИО только по regex: {exc}")
        _NATASHA_LOAD_FAILED = True
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
        for span in doc.spans or []:
            if span.type == "PER" and _looks_like_fio(span.text):
                return _normalize_fio(span.text)
    except Exception as exc:
        logger.warning(f"Сбой Natasha NER: {exc}")
    return None


def natasha_person_spans(window: str) -> list:
    """Все PER-спаны окна как (нормализованное_ФИО, позиция_начала).

    В отличие от `_natasha_person` (первое лицо), отдаёт все лица с позициями —
    нужно для ролевого скоринга кандидатов по близости к якорю «Должник/Ответчик»
    (второй независимый экстрактор в `semantic_classifier.classify_debtor_name`).
    Пустой список при недоступной Natasha (graceful).
    """
    nat = _ensure_natasha()
    if not nat:
        return []
    try:
        from natasha import Doc
        segmenter, ner_tagger = nat
        doc = Doc(window)
        doc.segment(segmenter)
        doc.tag_ner(ner_tagger)
        out = []
        for span in doc.spans or []:
            if span.type == "PER" and _looks_like_fio(span.text):
                out.append((_normalize_fio(span.text), span.start))
        return out
    except Exception as exc:
        logger.warning(f"Сбой Natasha NER (spans): {exc}")
        return []
