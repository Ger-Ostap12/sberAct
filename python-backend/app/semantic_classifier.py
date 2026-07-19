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
from typing import Optional

logger = logging.getLogger(__name__)

# Модель скачивается один раз заранее (см. handoff, план `new_asnaliz` §Фаза 3)
# и лежит локально — рантайм не обращается в HuggingFace Hub. Имя каталога —
# переменной окружения (сравнение моделей на измерительных скриптах, план
# §Фаза 2). ПРОВЕРЕНО: крупная mpnet-base (~1ГБ) дала на этой задаче ХУЖЕ
# (71% против 78%) при том же пороге — она систематически завышает score
# на всех парах (в т.ч. ложных), не различает лучше; порог 0.6 откалиброван
# под MiniLM. Дефолт — MiniLM, пока нет честного (не подогнанного под этот
# же 46-файловый корпус) способа перекалибровать порог под другую модель.
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

# Начало просительной части — полный набор глаголов-просьб, как в
# `document_analyzer._PRAYER_VERB` (posekционный предпросмотр уже решал эту
# задачу для того же текста — берём тот же список, а не изобретаем свой):
# прошу/просим/просит/просят, ходатайствую/ходатайствуем/ходатайствует.
# Двоеточие НЕ обязательно — «ПРОСИТ СУД\n1. признать…» (без «:») тоже
# встречается (найдено на реальном документе, план `new_asnaliz` §Фаза 2).
# Presence-тест пунктов (`detect_procedure_clauses`) ищет ТОЛЬКО в этом окне —
# иначе цитаты закона в теле документа («…процедуру реструктуризации
# применяют, если…») перевешивают настоящий пункт просьбы.
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
    embeddings = model.encode(phrases, convert_to_numpy=True, normalize_embeddings=True,
                               show_progress_bar=False)
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
        sent_embeddings = model.encode(sentences, convert_to_numpy=True, normalize_embeddings=True,
                                        show_progress_bar=False)
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
    # Маскируем реквизитные скобки ТОЛЬКО для эмбеддинга — предложение для
    # отображения (`sentences[sent_idx]` в результате) остаётся оригинальным.
    masked_sentences = [_mask_requisites(s) for s in sentences]

    per_label = _per_label_max_similarity(model, masked_sentences, clause_phrases)
    if per_label is None:
        return {}

    from semantic_reference_phrases import PROCEDURE_NEGATIVE_CLAUSES

    try:
        import numpy as np

        neg_embeddings = model.encode(PROCEDURE_NEGATIVE_CLAUSES, convert_to_numpy=True,
                                       normalize_embeddings=True, show_progress_bar=False)
        sent_embeddings = model.encode(masked_sentences, convert_to_numpy=True,
                                        normalize_embeddings=True, show_progress_bar=False)
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


def classify_procedure_family(text: str) -> tuple[Optional[str], dict]:
    """Семейство процедуры банкротства — «rtk» (только включение в реестр) или
    «initiation» (признание банкротом + введение процедуры) — по НАЛИЧИЮ
    пунктов, не по ближайшему смыслу (см. `detect_procedure_clauses`).

    Комбинирование зеркалит regex `classify_mixin._INIT_DECLARE_RE`/
    `_INIT_PROCEDURE_RE`: declare ИЛИ procedure → инициирование (даже если
    include_in_registry тоже есть — инициирующее заявление обычно просит и
    включить требование заявителя); только include_in_registry → rtk.

    Возвращает (family, детали_по_пунктам) — family это None, если просительная
    часть не найдена/модель недоступна/ни один пункт не набрал порог (документ,
    похоже, вообще не о процедуре банкротства — напр. mortgage_claim).
    """
    from semantic_reference_phrases import PROCEDURE_CLAUSES, PROCEDURE_CLAUSE_THRESHOLD

    clauses = detect_procedure_clauses(text, PROCEDURE_CLAUSES, PROCEDURE_CLAUSE_THRESHOLD)
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
