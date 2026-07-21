# -*- coding: utf-8 -*-
"""Shadow-слой семантической классификации типа документа (эмбеддинги).

Роль модуля — ДИАГНОСТИЧЕСКАЯ, не рабочая. По плану (`new_asnaliz`, фаза 1):
слой считает свой ответ ПАРАЛЛЕЛЬНО с `classify_mixin.classify_document` и
ни на что не влияет, пока явно не включён `SBERACT_SEMANTIC_SHADOW` — эталонные
фразы см. `semantic_reference_phrases.py`, точка вызова — `document_analyzer.
analyze_from_text` рядом с `classify_document`.

Инициализация ленивая и graceful, по образцу `nlp_natasha.py`: нет пакета/
модели — работаем как раньше, `classify_semantic` возвращает `(None, 0.0, "")`.
Модель офлайн: путь ЛОКАЛЬНЫЙ (см. `_MODEL_DIR`), сеть не трогаем даже случайно
(`local_files_only=True`).
"""
from __future__ import annotations

import logging
import os
import re
import sys
from typing import TYPE_CHECKING, Optional, cast

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = os.environ.get("SBERACT_SEMANTIC_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models", _MODEL_NAME)

# Кэш ленивых синглтонов. None — ещё не пробовали; False — попытка провалилась.
_MODEL = None
# Эталонные эмбеддинги считаются один раз за процесс (не на каждый вызов).
_REFERENCE_EMBEDDINGS = None  # dict[label -> ndarray (n_phrases, dim)]

# Простой сплиттер предложений: точка/!/?/перенос строки. НЕ тянем Natasha/razdel
# ради этой задачи — это независимый гибрид-слой (см. docstring выше).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

DEFAULT_THRESHOLD = 0.55


_PRAYER_VERB = r"(?:прошу|просим|просит|просят|ходатайству(?:ю|ем|ет))(?![а-яёА-ЯЁ])"
_PRAYER_START_RE = re.compile(_PRAYER_VERB + r"(?:\s+суд\w*)?\s*:?", re.IGNORECASE)
# Конец просительной части — типовые следующие разделы заявления.
_PRAYER_END_RE = re.compile(
    r"\n\s*(?:Приложени|Перечень\s+прилагаем|Подпись|С\s+уважением)", re.IGNORECASE
)


def _extract_prayer_window(text: str) -> str:
    """Текст просительной части («ПРОШУ:» … до «Приложения»/подписи).

    Пустая строка, если якорь не найден — вызывающий код тогда работает без
    presence-теста (как если бы семантический слой был недоступен).
    """
    if not text:
        return ""
    m = _PRAYER_START_RE.search(text)
    if not m:
        return ""
    window = text[m.end():]
    end = _PRAYER_END_RE.search(window)
    if end:
        window = window[:end.start()]
    return window


def _ensure_model_files():
    """Собирает большие бинарники модели (`model.safetensors`) из кусков
    `<файл>.parts/`, если сам файл ещё не собран — так модель распространяется
    через git (GitHub режет файлы >100 МБ, см. `tools/split_model.py`), а на
    диске после первой сборки лежит уже целый файл. Без побочных эффектов,
    если модель установлена как обычно (parts-папки нет) — тихо не делает ничего.
    """
    if not os.path.isdir(_MODEL_DIR):
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
        from split_model import assemble

        for name in os.listdir(_MODEL_DIR):
            if name.endswith(".parts"):
                target = os.path.join(_MODEL_DIR, name[: -len(".parts")])
                assemble(target)
    except Exception as exc:
        logger.warning(f"Не удалось собрать файлы модели из кусков: {exc}")


def _ensure_model():
    """SentenceTransformer, загруженный ЛОКАЛЬНО (офлайн). False — недоступна.

    Офлайн-гарантия — сам факт загрузки по локальному ПУТИ (не repo id), сеть
    не трогается. `HF_HUB_OFFLINE` — дополнительная страховка на случай, если
    библиотека всё же попытается сходить в HuggingFace Hub (напр. проверить
    обновление конфига).
    """
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        if not os.path.isdir(_MODEL_DIR):
            logger.warning(
                f"Модель эмбеддингов не найдена локально ({_MODEL_DIR}), "
                f"семантический shadow-слой отключён"
            )
            _MODEL = False
            return _MODEL
        _ensure_model_files()
        _MODEL = SentenceTransformer(_MODEL_DIR)
    except Exception as exc:  # пакет/модель недоступны — работаем без слоя
        logger.warning(f"Семантический классификатор недоступен: {exc}")
        _MODEL = False
    return _MODEL


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(text or "")
    return [p.strip() for p in parts if p and p.strip()]

_CLAUSE_SPLIT_RE = re.compile(r"(?:^|\n)\s*\d{1,2}[.\)]\s+", re.MULTILINE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n{1,2}")
_MIN_CLAUSE_LEN = 20


def _split_prayer_clauses(window: str) -> list[str]:
    """Пункты просительной части: нумерация → абзацы → предложения (по
    убыванию надёжности). Не все заявления нумеруют пункты — часть пишет
    просительную часть сплошным текстом абзацами (без «1.»/«2.»); в этом
    случае абзац — надёжнее разбитого по точкам предложения (сохраняет цельный
    смысл пункта, не режется на реквизитных и денежных сокращениях)."""
    numbered = [p.strip() for p in _CLAUSE_SPLIT_RE.split(window or "") if p and p.strip()]
    numbered = [p for p in numbered if len(p) >= _MIN_CLAUSE_LEN]
    if len(numbered) >= 2:
        return numbered

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(window or "") if p and p.strip()]
    paragraphs = [p for p in paragraphs if len(p) >= _MIN_CLAUSE_LEN]
    if len(paragraphs) >= 2:
        return paragraphs

    return [s for s in _split_sentences(window) if len(s) >= _MIN_CLAUSE_LEN]

_REQUISITE_PARENS_RE = re.compile(r"\([^()]*(?:ИНН|ОГРН)[^()]*\)", re.IGNORECASE)


def _mask_requisites(text: str) -> str:
    return _REQUISITE_PARENS_RE.sub(" ", text or "")


_NAME_TOKEN_RE = re.compile(r"[А-ЯЁа-яё]{3,}")


def _mask_debtor_name(sentence: str, debtor_name: str) -> str:
    """Вырезает упоминания должника по имени из клаузы перед эмбеддингом.

    Реальное ФИО в клаузе («Признать Ким Клим несостоятельным (банкротом)»)
    сильно дилютит эмбеддинг относительно эталона («Признать гражданина
    несостоятельным (банкротом)») — найдено на реальном документе (score
    0.51 против эталона у обычного ФИО из 2 слов, 0.47 у ФИО из 3 слов —
    ниже PROCEDURE_CLAUSE_THRESHOLD=0.58, клауза считалась НЕ найденной).
    Тот же приём, что `_mask_requisites` для ИНН/ОГРН: убираем шум, который
    несёт не смысл клаузы, а конкретику документа.

    Срез токена (не всё слово) — потому что в клаузе имя часто в падеже,
    отличном от именительного (`debtorName` нормализован в номинатив), «съедаем»
    последние 2 символа как допустимое окончание словоформы.
    """
    if not debtor_name:
        return sentence
    for token in _NAME_TOKEN_RE.findall(debtor_name):
        stem = token[:max(3, len(token) - 2)]
        sentence = re.sub(re.escape(stem) + r"\w*", " ", sentence, flags=re.IGNORECASE)
    return sentence


def _ensure_reference_embeddings(model, candidates: dict[str, list[str]]):
    """Эмбеддинги эталонных фраз — считаются один раз на процесс и кешируются.

    Ключ кеша — id(candidates), достаточно для единственного реестра
    `SEMANTIC_DOCUMENT_TYPES` (реестры фраз не пересоздаются на каждый вызов).
    """
    global _REFERENCE_EMBEDDINGS
    if _REFERENCE_EMBEDDINGS is not None and _REFERENCE_EMBEDDINGS.get("_source_id") == id(candidates):
        return _REFERENCE_EMBEDDINGS
    labels: list[str] = []
    phrases: list[str] = []
    spans: list[tuple[int, int]] = []
    for label, label_phrases in candidates.items():
        start = len(phrases)
        phrases.extend(label_phrases)
        spans.append((start, len(phrases)))
        labels.append(label)
    embeddings = cast("np.ndarray", model.encode(phrases, convert_to_numpy=True, normalize_embeddings=True,
                               show_progress_bar=False))
    _REFERENCE_EMBEDDINGS = {
        "_source_id": id(candidates),
        "labels": labels,
        "spans": spans,
        "embeddings": embeddings,
    }
    return _REFERENCE_EMBEDDINGS


def _per_label_max_similarity(
    model, sentences: list[str], candidates: dict[str, list[str]]
) -> Optional[dict]:
    """Для каждого `label` в `candidates` — (score, sentence_idx) максимума
    сходства среди `sentences`. None при сбое модели/энкодинга."""
    try:
        import numpy as np

        ref = _ensure_reference_embeddings(model, candidates)
        # Батч-encode ВСЕХ предложений за один вызов модели — без этого бюджет
        # 0.3-0.5 с/документ (план §1.1) не выдержать на CPU.
        sent_embeddings = cast("np.ndarray", model.encode(sentences, convert_to_numpy=True, normalize_embeddings=True,
                                        show_progress_bar=False))
        # Эмбеддинги нормализованы -> косинусная близость = скалярное произведение.
        sims = sent_embeddings @ ref["embeddings"].T  # (n_sentences, n_ref_phrases)

        result = {}
        for label, (start, stop) in zip(ref["labels"], ref["spans"]):
            label_sims = sims[:, start:stop]
            if label_sims.size == 0:
                continue
            local_idx = int(np.argmax(label_sims))
            sent_idx, _phrase_idx = divmod(local_idx, label_sims.shape[1])
            result[label] = (float(label_sims[sent_idx, _phrase_idx]), sent_idx)
        return result
    except Exception as exc:
        logger.warning(f"Сбой семантического классификатора: {exc}")
        return None


def classify_semantic(
    text: str,
    candidates: dict[str, list[str]],
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[Optional[str], float, str]:
    """Ближайший по смыслу тип документа среди `candidates` (nearest-neighbor
    по ВСЕМУ тексту — годится для грубой прикидки темы документа, но не для
    различения «пункт есть/нет пункта», см. `detect_procedure_clauses`).

    Возвращает (label, score, sentence) — `sentence` это предложение документа,
    давшее максимальное сходство (для ручного разбора расхождений). При
    недоступной модели или отсутствии совпадения выше `threshold` — (None, 0.0, "").
    """
    if not text or not text.strip() or not candidates:
        return None, 0.0, ""
    model = _ensure_model()
    if not model:
        return None, 0.0, ""

    sentences = _split_sentences(text)
    if not sentences:
        return None, 0.0, ""

    per_label = _per_label_max_similarity(model, sentences, candidates)
    if per_label is None:
        return None, 0.0, ""

    best_label: Optional[str] = None
    best_score = -1.0
    best_sentence_idx = -1
    for label, (score, sent_idx) in per_label.items():
        if score > best_score:
            best_score = score
            best_label = label
            best_sentence_idx = sent_idx

    if best_label is None or best_score < threshold:
        return None, best_score if best_score > 0 else 0.0, ""
    return best_label, best_score, sentences[best_sentence_idx]


def detect_procedure_clauses(
    text: str,
    clause_phrases: dict[str, list[str]],
    threshold: float,
    debtor_name: str = "",
) -> dict[str, tuple[bool, float, str]]:
    """Presence-тест: для КАЖДОГО типа пункта (`declare_bankrupt`/
    `introduce_procedure`/`include_in_registry` — см.
    `semantic_reference_phrases.PROCEDURE_CLAUSES`) — есть ли в просительной
    части предложение похожего смысла, НЕЗАВИСИМО от остальных типов.

    В отличие от `classify_semantic` (один «победивший» тип на весь документ),
    здесь каждый пункт проверяется отдельно — инициирующее заявление обычно
    содержит И «признать банкротом», И «включить в реестр» одновременно, и
    только совместное наличие/отсутствие пунктов различает РТК от
    инициирования (см. docstring `PROCEDURE_CLAUSES`).

    Возвращает {label: (найден_ли, score, предложение)}. Пустой словарь при
    недоступной модели или отсутствии просительной части в тексте.

    Пункт засчитывается найденным, только если лучшее предложение похоже на
    ПОЛОЖИТЕЛЬНЫЙ эталон БОЛЬШЕ, чем на любой из `PROCEDURE_NEGATIVE_CLAUSES`
    (жанровые «ложные друзья» — типовые оговорки про неявку представителя и
    т.п., см. `semantic_reference_phrases`) — без этого такие оговорки
    перевешивают настоящий пункт просьбы (частый класс ошибок на замере).
    """
    window = _extract_prayer_window(text)
    if not window:
        return {}
    model = _ensure_model()
    if not model:
        return {}
    sentences = _split_prayer_clauses(window)
    if not sentences:
        return {}

    masked_sentences = [_mask_debtor_name(_mask_requisites(s), debtor_name) for s in sentences]

    per_label = _per_label_max_similarity(model, masked_sentences, clause_phrases)
    if per_label is None:
        return {}

    from semantic_reference_phrases import PROCEDURE_NEGATIVE_CLAUSES

    try:
        import numpy as np

        neg_embeddings = cast("np.ndarray", model.encode(PROCEDURE_NEGATIVE_CLAUSES, convert_to_numpy=True,
                                       normalize_embeddings=True, show_progress_bar=False))
        sent_embeddings = cast("np.ndarray", model.encode(masked_sentences, convert_to_numpy=True,
                                        normalize_embeddings=True, show_progress_bar=False))
        # Максимум сходства с «ложными друзьями» ДЛЯ КАЖДОГО предложения —
        # сравнивается с положительным score того же предложения ниже.
        neg_score_per_sentence = (sent_embeddings @ neg_embeddings.T).max(axis=1)
    except Exception as exc:
        logger.warning(f"Сбой негативных эталонов процедуры: {exc}")
        neg_score_per_sentence = None

    result = {}
    for label, (score, sent_idx) in per_label.items():
        beats_negative = (
            neg_score_per_sentence is None
            or score > float(neg_score_per_sentence[sent_idx])
        )
        result[label] = (score >= threshold and beats_negative, score, sentences[sent_idx])
    return result

_DEBTOR_ANCHOR_RE = re.compile(r"(?:Должник|Ответчик(?:и)?)\b", re.IGNORECASE)
# Якоря прочих ролей: если такой ближе к кандидату, чем «Должник», кандидат
# принадлежит другому лицу (кредитор/управляющий/представитель) — отбрасываем.
_OTHER_ROLE_ANCHOR_RE = re.compile(
    r"(?:Кредитор|Взыскател|Истец|Заявител|"
    r"(?:финансов\w+|арбитражн\w+|конкурсн\w+)\s+управляющ|Представител)",
    re.IGNORECASE,
)

# Кандидаты-организации: аббревиатура/полная форма + название в кавычках.
_ORG_CAND_RE = re.compile(
    r"""(?:
        ООО|ПАО|ОАО|ЗАО|АО|НАО|ПК |
        Общество\s+с\s+ограниченной\s+ответственностью |
        Публичное\s+акционерное\s+общество |
        (?:Непубличное\s+)?Акционерное\s+общество |
        Производственный\s+кооператив
    )\s*[«"][^»"\n]{2,80}[»"]""",
    re.IGNORECASE | re.VERBOSE,
)

# Кандидаты-ИП: токен «ИП»/«Индивидуальный предприниматель» + фамилия(+инициалы/имя).
_IP_CAND_RE = re.compile(
    r"""(?:ИП|Индивидуальн\w+\s+предприниматель)\s+
        (?P<name>[А-ЯЁ][А-ЯЁа-яё\-]+
            (?:  \s+[А-ЯЁ][А-ЯЁа-яё\-]+(?:\s+[А-ЯЁ][А-ЯЁа-яё\-]+)?  # Имя (Отчество)
               | \s+[А-ЯЁ]\.\s*[А-ЯЁ]\.                            # инициалы И.И. (точки обязательны)
            )?)""",
    re.VERBOSE,
)

_DEBTOR_WINDOW_HEAD_CAP = 2500


def _extract_debtor_window(text: str) -> str:
    """Окно для харвеста кандидатов в должники: шапка (стороны) + просительная часть.

    Стороны перечислены в шапке (до «ПРОШУ»), а «Признать [должника] банкротом» —
    в просьбе; оба места полезны. Шапку режем по `_DEBTOR_WINDOW_HEAD_CAP`, чтобы
    в окно не втянулось тело документа (факты, реквизиты третьих лиц).
    """
    if not text:
        return ""
    m = _PRAYER_START_RE.search(text)
    head_end = min(m.start(), _DEBTOR_WINDOW_HEAD_CAP) if m else _DEBTOR_WINDOW_HEAD_CAP
    head = text[:head_end]
    prayer = _extract_prayer_window(text)
    return head + "\n" + prayer if prayer else head


def _nearest_preceding(anchor_re: "re.Pattern", window: str, pos: int) -> Optional[int]:
    """Позиция ближайшего к `pos` слева совпадения `anchor_re` (или None)."""
    best = None
    for m in anchor_re.finditer(window, 0, pos):
        best = m.start()
    return best


def _harvest_debtor_candidates(window: str) -> list[tuple[str, int, str]]:
    """Кандидаты (имя, позиция, вид) из окна: ЮЛ, ИП, ФЛ (Natasha)."""
    candidates: list[tuple[str, int, str]] = []
    for m in _ORG_CAND_RE.finditer(window):
        candidates.append((m.group(0).strip(), m.start(), "legal"))
    for m in _IP_CAND_RE.finditer(window):
        candidates.append(("ИП " + m.group("name").strip(), m.start(), "ip"))
    try:
        from fio_detector import natasha_person_spans

        for name, start in natasha_person_spans(window):
            # ФНС-бланк «На №» перед ФИО просачивается в конец спана
            # («Богачева Анна Михайловна На») — срезаем хвостовой канцелярит.
            name = re.sub(r"\s+На$", "", name).strip()
            candidates.append((name, start, "individual"))
    except Exception as exc:  # мягкая зависимость, как везде в проекте
        logger.warning(f"NER-харвест кандидатов недоступен: {exc}")
    return candidates


def classify_debtor_name(text: str) -> tuple[Optional[str], dict]:
    """Имя должника, найденное ВТОРЫМ способом (для сверки с regex `debtorName`).

    Из кандидатов окна берём того, чей ближайший слева якорь — «Должник/Ответчик»
    (и не перекрыт более близким якорём иной роли). Из нескольких — ближайшего к
    якорю. None (воздержаться), если ни один кандидат не привязан к якорю должника
    или окно/NER недоступны — воздержание лучше догадки (зеркалит процедуру-ось).

    Косинус-ранжировщик роли (заход 2) пробовали для спасения воздержаний и
    ЗАКРЫЛИ: на RTK/ФНС косинус систематически берёт финансового управляющего/
    представителя (а то и банк) вместо должника, причём с БОЛЬШЕЙ маржой, чем у
    верных — порогом не чинится (замер `tests/diag_debtor_abstain.py`, тот же
    класс провала, что тип лица в handoff §P.2). Настоящий корень воздержаний —
    дыра харвеста (капс в таблицах, инициалы в шапке), это regex/NER-задача.

    Возвращает (имя|None, meta) — meta несёт вид лица и дистанцию до якоря.
    """
    window = _extract_debtor_window(text)
    if not window:
        return None, {}
    best_name: Optional[str] = None
    best_kind = ""
    best_dist = 10 ** 9
    for name, pos, kind in _harvest_debtor_candidates(window):
        d_anchor = _nearest_preceding(_DEBTOR_ANCHOR_RE, window, pos)
        if d_anchor is None:
            continue
        o_anchor = _nearest_preceding(_OTHER_ROLE_ANCHOR_RE, window, pos)
        if o_anchor is not None and o_anchor > d_anchor:
            continue  # к кандидату ближе якорь иной роли — это не должник
        dist = pos - d_anchor
        if dist < best_dist:
            best_dist, best_name, best_kind = dist, name, kind
    if best_name is None:
        return None, {}
    return best_name, {"kind": best_kind, "dist": best_dist}


_LETTER_RE = re.compile(r"[А-ЯЁа-яёA-Za-z]")
# Признаки организации: правовая форма или кавычки — у физлица их не бывает.
_ORG_MARKER_RE = re.compile(
    r"[«»\"]|"
    r"\b(?:ООО|ОАО|ПАО|ЗАО|АО|НАО|ПК|КФХ|"
    r"Общество|Акционерн\w+|кооператив\w*|компани\w+|фирм\w+|банк\w*|"
    r"предприяти\w+|учреждени\w+|товариществ\w+|фонд\w*)\b",
    re.IGNORECASE,
)


def _initials(tokens: list[str]) -> str:
    """Инициалы из хвоста ФИО. Токен-инициалы «И.И.» → «ии» (обе буквы), обычное
    слово «Иван» → «и» (первая). Так «Иванов Иван Иванович» и «Иванов И.И.» дают
    одинаковую строку инициалов. Ё→Е, регистр снят.
    """
    out: list[str] = []
    for t in tokens:
        letters = _LETTER_RE.findall(t)
        if not letters:
            continue
        if "." in t and re.fullmatch(r"(?:[А-ЯЁа-яёA-Za-z]\.?){1,3}", t):
            out.extend(letters)  # «И.И.» — все буквы как отдельные инициалы
        else:
            out.append(letters[0])
    return "".join(c.lower().replace("ё", "е") for c in out)


# Ленивый pymorphy — общий с остальным проектом приём мягкой зависимости
# (`inflection_mixin._ensure_morph`): нет пакета — работаем без лемматизации.
_MORPH = None


def _lemma_surname(surname: str) -> str:
    """Фамилия в им. падеже (лемма). «Базова»(род.)→«базов» — иначе родительный
    из просьбы («Признать Базова…») ложно расходится с номинативом из шапки.
    Предпочитаем Surn-разбор (фамилии-омонимы иначе лемматизируются как имя).
    """
    global _MORPH
    if _MORPH is None:
        try:
            from pymorphy3 import MorphAnalyzer

            _MORPH = MorphAnalyzer()
        except Exception as exc:
            logger.warning(f"pymorphy3 недоступен, фамилия без лемматизации: {exc}")
            _MORPH = False
    if not _MORPH:
        return surname
    try:
        parses = _MORPH.parse(surname)
        best = next((p for p in parses if "Surn" in p.tag), parses[0] if parses else None)
        return best.normal_form if best else surname
    except Exception:
        return surname


def _person_key(name: str) -> str:
    """Ключ физлица: фамилия(лемма) + инициалы. Полное ФИО и инициалы дают один
    ключ («Иванов Иван Иванович» = «Иванов И.И.»); падежи фамилии сводятся к
    номинативу лемматизацией.
    """
    tokens = [t for t in re.split(r"\s+", name.strip()) if t]
    if not tokens:
        return ""
    surname = re.sub(r"[^а-яёa-z\-]", "", tokens[0].lower()).replace("ё", "е")
    surname = _lemma_surname(surname).replace("ё", "е")
    return f"{surname}.{_initials(tokens[1:])}"


def _debtor_key(name: str) -> str:
    """Каноничный ключ имени должника для сравнения regex↔семантика.

    Префикс вида лица (фл/ип/юл) — часть ключа: банк-ЮЛ vs должник-ФЛ обязаны
    разойтись. Вид определяем по маркерам организации (форма/кавычки), а не через
    `is_person_name` — тот отвергает «Иванов И.И.» из-за точек в токене. ЮЛ через
    `org_normalizer` (снимает форму/кавычки/регистр), ФЛ/ИП — через `_person_key`.
    """
    if not name:
        return ""
    if re.match(r"^\s*ИП\b", name, re.IGNORECASE):
        return "ип|" + _person_key(re.sub(r"^\s*ИП\s+", "", name, flags=re.IGNORECASE))
    if _ORG_MARKER_RE.search(name):
        from org_normalizer import norm_org_key

        return "юл|" + norm_org_key(name)
    return "фл|" + _person_key(name)


def _name_tokens(name: str) -> set[str]:
    """Множество значимых токенов имени (ё→е, регистр снят, инициалы/пунктуация
    отброшены) — для проверки «частичного извлечения»."""
    out = set()
    for t in re.split(r"\s+", (name or "").strip()):
        t = re.sub(r"[^а-яёa-z\-]", "", t.lower()).replace("ё", "е")
        if len(t) >= 2:  # отбрасываем одиночные инициалы/мусор
            out.add(t)
    return out


def debtor_names_match(regex_name: str, semantic_name: str) -> bool:
    """Совместимы ли имена regex и семантики (True = НЕ показывать баннер).

    Совместимы, если: (а) каноничные ключи равны; либо (б) один набор токенов —
    подмножество другого (одно лицо, просто одна сторона извлекла менее полно —
    напр. NER потерял фамилию-омоним «Песня» и вернул «Сергей Николаевич»). Это
    НЕ противоречие, а разная полнота; баннер поднимаем только на конфликте.
    """
    if not regex_name or not semantic_name:
        return True  # нечего сверять
    key_r, key_s = _debtor_key(regex_name), _debtor_key(semantic_name)
    if key_r == key_s:
        return True
    if key_r.split("|", 1)[0] != key_s.split("|", 1)[0]:
        return False
    a, b = _name_tokens(regex_name), _name_tokens(semantic_name)
    return bool(a) and bool(b) and (a <= b or b <= a)


def classify_procedure_family(text: str, debtor_name: str = "") -> tuple[Optional[str], dict]:
    """Семейство процедуры банкротства — «rtk» (только включение в реестр) или
    «initiation» (признание банкротом + введение процедуры) — по НАЛИЧИЮ
    пунктов, не по ближайшему смыслу (см. `detect_procedure_clauses`).

    Комбинирование зеркалит regex `classify_mixin._INIT_DECLARE_RE`/
    `_INIT_PROCEDURE_RE`: declare ИЛИ procedure → инициирование (даже если
    include_in_registry тоже есть — инициирующее заявление обычно просит и
    включить требование заявителя); только include_in_registry → rtk.

    `debtor_name` (уже извлечённое `extracted_fields["debtorName"]`) —
    маскируется в клаузах перед эмбеддингом (`_mask_debtor_name`), иначе
    реальное ФИО в «Признать [ФИО] несостоятельным (банкротом)» топит score
    ниже порога и клауза считается не найденной (реальный кейс, план
    `new_asnaliz`).

    Возвращает (family, детали_по_пунктам) — family это None, если просительная
    часть не найдена/модель недоступна/ни один пункт не набрал порог (документ,
    похоже, вообще не о процедуре банкротства — напр. mortgage_claim).
    """
    from semantic_reference_phrases import PROCEDURE_CLAUSES, PROCEDURE_CLAUSE_THRESHOLD

    clauses = detect_procedure_clauses(text, PROCEDURE_CLAUSES, PROCEDURE_CLAUSE_THRESHOLD, debtor_name)
    if not clauses:
        return None, clauses

    has_declare = clauses.get("declare_bankrupt", (False, 0.0, ""))[0]
    has_procedure = clauses.get("introduce_procedure", (False, 0.0, ""))[0]
    has_registry = clauses.get("include_in_registry", (False, 0.0, ""))[0]

    if has_declare or has_procedure:
        return "initiation", clauses
    if has_registry:
        return "rtk", clauses
    return None, clauses
