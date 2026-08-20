# -*- coding: utf-8 -*-
"""Бенчмарк LLM для схемы "должник по типу лица + управляющий" (Андрей,
2026-07-22). Отдельно от llm_bench_run.py — та схема была role-based
(должник/кредитор/управляющий с фиксированными полями), эта — ветвится по
entityType (individual/legal/ip/kfh), поэтому логика сверки другая.

Запуск (converter/.venv, там llama-cpp-python):
  cd converter && .venv/Scripts/python.exe ../python-backend/tests/llm_bench_run_fields.py \
      --model models/gemma-3-4b-it-Q4_K_M.gguf --prompt df_v1 --label gemma_df_v1
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_THIS = os.path.dirname(os.path.abspath(__file__))
DUMP_PATH = os.path.join(_THIS, "llm_bench_dump_debtorfields.json")

sys.path.insert(0, _THIS)
# Прод-логика живёт в app/llm/ — бенчмарк обязан измерять ИМЕННО тот код,
# который работает у пользователя, иначе его цифра качества декоративна.
sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
from llm.windows import (  # noqa: E402
    extract_parties_window, extract_financial_block,
)
from llm.parsing import (  # noqa: E402
    extract_json as _extract_json,
    extract_json_array as _extract_json_array,
    repair_json as _repair_json,
    check_leak as _check_leak,
    sanitize_mortgage as _sanitize_mortgage,
)
from llm.matching import (  # noqa: E402
    fuzzy_match as _fuzzy_match, core_name as _core_name, norm as _norm,
)
from llm_bench_prompts import (  # noqa: E402
    DF_PROMPTS, DF_V4_LEAK_MARKERS, DF_MORTGAGE_LEAK_MARKERS,
    build_df_v7_prompt, build_df_v8_prompt, build_df_mortgage_prompt,
    build_df_mortgage_collateral_prompt, build_df_mortgage_valuation_prompt,
)

sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
from requisites_validation import is_valid_inn, is_valid_ogrn_any  # noqa: E402
from sro_registry import resolve_sro  # noqa: E402

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_VALID_TYPES = {"individual", "legal", "ip", "kfh"}

# --- Ипотека: representatives отдельным изолированным вызовом, НЕ вместе с
#     остальной схемой (Андрей, план "LLM для ипотеки"). В общем окне (весь
#     документ, ~9000 симв.) модель систематически хватала название банка/
#     филиала вместо ФИО представителя (representatives.plaintiff — 1/8 на
#     df_mortgage_v1 И v2, три раунда текстовых правок не помогли). Изолировал
#     блок «Представитель истца:»…«Ответчик(и):» (короткий, ~150-250 симв.) и
#     прогнал ОТДЕЛЬНО тем же промптом — 8/8, по 2.5-4с на файл вместо
#     90-150с за весь документ. Значит проблема была не в сложности задачи, а
#     в шуме окружающего контекста — тот же класс фикса, что уже сработал для
#     СРО/manager (сужение, а не текстовый запрет).
_REP_BLOCK_RE = {
    "plaintiff": re.compile(
        r"Представитель\s+истца\s*:(.*?)(?:Ответчик|ИСКОВОЕ|Цена\s+иска|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    "defendant": re.compile(
        r"Представитель\s+ответчика\s*:(.*?)(?:Ответчик|Истец|ИСКОВОЕ|Цена\s+иска|$)",
        re.IGNORECASE | re.DOTALL,
    ),
}

_REP_ONLY_SYSTEM = (
    "Ниже — короткий фрагмент искового заявления, блок «Представитель "
    "{role_ru}». В нём сначала может идти название банка/его филиала или "
    "отделения (организация — НЕ ответ), а затем ФИО конкретного человека "
    "(Фамилия Имя Отчество) — это и есть представитель. Верни СТРОГО JSON "
    "без пояснений: {{\"name\": \"\"}} — только ФИО человека. Если ФИО "
    "человека в тексте нет вообще — {{\"name\": \"\"}}."
)
_REP_ROLE_RU = {"plaintiff": "истца", "defendant": "ответчика"}

# --- Компактный JSON через грамматику. Модель выдаёт JSON с отступами и
#     переносами строк, хотя few-shot однострочный: замерено 146 токенов на
#     файл (13с из 104с) уходит В ВОЗДУХ — на пробелы и markdown-обёртку.
#     Уговаривать текстом бессмысленно (пример уже компактный, модель его
#     игнорирует — она так обучена). Грамматика ограничивает САМ ВЫБОР
#     токена, то есть пробел физически не может быть выбран — это
#     детерминированный запрет, а не просьба.
_COMPACT_JSON_GBNF = (
    '\nroot   ::= object | array\nvalue  ::= object | array | string | number | "true" | "false" | "null"\nobject ::= "{" ( pair ( "," pair )* )? "}"\npair   ::= string ":" value\narray  ::= "[" ( value ( "," value )* )? "]"\nstring ::= "\\"" ( [^"\\\\] | "\\\\" ["\\\\/bfnrt] )* "\\""\nnumber ::= "-"? ( "0" | [1-9] [0-9]* ) ( "." [0-9]+ )? ( [eE] [-+]? [0-9]+ )?\n'
)

_COMPACT_GRAMMAR = None
# Включается из main; _timed_call вызывается из трёх мест без доступа к args.
_COMPACT_ON = False


def compact_grammar():
    """Ленивая сборка — грамматика нужна только если включён режим."""
    global _COMPACT_GRAMMAR
    if _COMPACT_GRAMMAR is None:
        from llama_cpp import LlamaGrammar
        _COMPACT_GRAMMAR = LlamaGrammar.from_string(_COMPACT_JSON_GBNF, verbose=False)
    return _COMPACT_GRAMMAR


# --- Этап 1 (оптимизация скорости): ЕДИНСТВЕННАЯ точка вызова LLM в файле.
#     Раньше вызовов было три (основной инлайном в main, _call_with_fewshot,
#     _fetch_representative) — замер токенов и split prefill/decode пришлось бы
#     дублировать трижды, и они бы разъехались. Накопитель метрик текущего
#     файла — модульный список, чтобы не тащить его через сигнатуры
#     _fetch_representative/_fetch_mortgage_properties.
_CALLS: list = []


def _timed_call(llm, msgs: list, max_tokens: int, tag: str, **extra) -> tuple:
    """Вызов LLM со стримингом. Стриминг нужен ровно ради одного: время до
    первого токена — это prefill, всё остальное — decode. Замер на корпусе:
    prefill 128.7с (63%), decode 76.2с (37%) при 204.9с на файл — то есть вход
    весит вдвое больше выхода, и главная цель — 94.9с prefill основного
    вызова. Цена стриминга: в чанках llama-cpp НЕ отдаёт
    usage (_convert_text_completion_chunks_to_chat отдаёт только delta), так
    что токены считаем сами — сгенерированные ретокенизацией ответа, промпт как
    остаток от llm.n_tokens (длина контекста после генерации).
    Возвращает (raw, meta); meta дополнительно кладётся в _CALLS."""
    t0 = time.perf_counter()
    t_first = None
    pieces: list = []
    error = ""
    try:
        if _COMPACT_ON:
            extra = dict(extra, grammar=compact_grammar())
        for chunk in llm.create_chat_completion(
                messages=msgs, temperature=0.0, max_tokens=max_tokens,
                stream=True, **extra):
            piece = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
            if piece:
                if t_first is None:
                    t_first = time.perf_counter()
                pieces.append(piece)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    t_end = time.perf_counter()
    raw = "".join(pieces)
    try:
        completion_tokens = len(
            llm.tokenize(raw.encode("utf-8"), add_bos=False, special=False))
    except Exception:
        completion_tokens = 0
    total_tokens = int(getattr(llm, "n_tokens", 0) or 0)
    t_split = t_first if t_first is not None else t_end
    meta = {
        "tag": tag,
        "prompt_tokens": max(0, total_tokens - completion_tokens),
        "completion_tokens": completion_tokens,
        "prefill_sec": round(t_split - t0, 3),
        "decode_sec": round(t_end - t_split, 3),
        "elapsed_sec": t_end - t0,
        "raw": raw,
    }
    if error:
        meta["error"] = error
    _CALLS.append(meta)
    return raw, meta


def _extract_rep_block(window: str, role: str) -> str:
    m = _REP_BLOCK_RE[role].search(window)
    return m.group(1).strip() if m else ""


def _fetch_representative(llm, window: str, role: str) -> tuple:
    """Изолированный вызов под ОДНУ роль представителя. Возвращает
    (name, elapsed_sec); ("", 0.0), если блока в тексте нет — не тратим
    вызов LLM на заведомо пустой блок."""
    block = _extract_rep_block(window, role)
    if not block:
        return "", 0.0
    system = _REP_ONLY_SYSTEM.format(role_ru=_REP_ROLE_RU[role])
    raw, meta = _timed_call(
        llm,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Текст:\n«{block}»"},
        ],
        100, f"rep_{role}",
    )
    elapsed = meta["elapsed_sec"]
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    name = ""
    if m:
        try:
            name = json.loads(m.group(0)).get("name", "") or ""
        except Exception:
            name = ""
    return name, elapsed


def _mp_type_keyword(s: str) -> str:
    """Тип объекта залога из описания — тот же принцип, что `_mp_type` в
    document_analyzer.py (переиспользуем логику локально, не тянем весь
    DocumentAnalyzer ради одной функции)."""
    n = (s or "").lower()
    if "участ" in n:
        return "участок"
    if "дом" in n:
        return "дом"
    if "квартир" in n:
        return "квартира"
    if "машино" in n:
        return "машиноместо"
    if "гараж" in n:
        return "гараж"
    if "помещ" in n:
        return "помещение"
    return ""


def _call_with_fewshot(llm, cfg: dict, user_text: str, max_tokens: int,
                       tag: str, expect: str = "object") -> tuple:
    """Один вызов с system+few-shot из build_df_mortgage_*_prompt. `expect`:
    "object" — распарсить {...} (_extract_json), "array" — распарсить [...]
    верхнего уровня (_extract_json_array) — нужно для collateral-схемы:
    модель на 2+ объектах игнорирует объектную обёртку {"properties": [...]}
    и возвращает голый массив (проверено эмпирически, df_mortgage_v5),
    поэтому схема сама просит массив, а не боремся с этим текстом. Возвращает
    (parsed_or_None, elapsed_sec)."""
    msgs = [{"role": "system", "content": cfg["system"]}]
    for u, a in cfg["fewshot"]:
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": f"Текст:\n«{user_text}»"})
    raw, meta = _timed_call(llm, msgs, max_tokens, tag)
    parsed = _extract_json_array(raw) if expect == "array" else _extract_json(raw)
    return parsed, meta["elapsed_sec"]


def _fetch_mortgage_properties(llm, collateral_block: str, valuation_block: str) -> tuple:
    """ДВА изолированных вызова — собственный якорь у каждого блока (см.
    _extract_collateral_block/_extract_valuation_block в
    llm_bench_phase1_dump.py, план §5: данные предмета ипотеки живут в двух
    далёких друг от друга местах документа) — плюс слияние по ТИПУ объекта:
    сумма/НПЦ из разбивки «в том числе <тип>» относится к КОНКРЕТНОМУ
    объекту, не общая для всех (та же логика, что document_analyzer._mp_type
    использует для сопоставления по regex-пути). Возвращает
    (properties: list[dict], elapsed_sec)."""
    elapsed = 0.0
    collateral_items: list = []
    if collateral_block:
        parsed, dt = _call_with_fewshot(
            llm, build_df_mortgage_collateral_prompt(), collateral_block, 500,
            "collateral", expect="array")
        elapsed += dt
        if isinstance(parsed, list):
            collateral_items = parsed

    breakdown: list = []
    npc_strategy, appraisal_report = "", ""
    if valuation_block:
        parsed, dt = _call_with_fewshot(
            llm, build_df_mortgage_valuation_prompt(), valuation_block, 400,
            "valuation")
        elapsed += dt
        if isinstance(parsed, dict):
            npc_strategy = parsed.get("npcStrategy", "") or ""
            appraisal_report = parsed.get("appraisalReport", "") or ""
            breakdown = parsed.get("breakdown") or []

    bd_by_type = {}
    for b in breakdown:
        if isinstance(b, dict):
            t = _mp_type_keyword(b.get("type", ""))
            if t:
                bd_by_type[t] = b

    merged = []
    for item in collateral_items:
        if not isinstance(item, dict):
            continue
        typ = _mp_type_keyword(item.get("description", ""))
        vb = bd_by_type.get(typ)
        if not vb and len(breakdown) == 1 and isinstance(breakdown[0], dict):
            vb = breakdown[0]  # единственная запись без разбивки — общий итог
        merged.append({
            "description": item.get("description", "") or "",
            "cadastralNumber": item.get("cadastralNumber", "") or "",
            "address": item.get("address", "") or "",
            "egrnRecord": item.get("egrnRecord", "") or "",
            "egrnRecordDate": item.get("egrnRecordDate", "") or "",
            "value": (vb or {}).get("value", "") or "",
            "startingPrice": (vb or {}).get("startingPrice", "") or "",
            "npcStrategy": npc_strategy,
            "appraisalReport": appraisal_report,
        })
    return merged, elapsed


def _fuzzy_match_sro(regex_val: str, llm_val: str) -> bool:
    """Сравнение через тот же реестр канонизации СРО, что использует
    прод-путь (sro_registry.resolve_sro) — иначе сокращение/аббревиатура
    ("Авангард" vs полное "НП «Объединение АУ «Авангард»»") ошибочно
    засчитывается как расхождение, хотя это одна и та же СРО."""
    if _fuzzy_match(regex_val, llm_val):
        return True
    r_full = resolve_sro(regex_val)
    l_full = resolve_sro(llm_val)
    if r_full and l_full:
        return r_full == l_full
    return False




# df_v5 показал, что текстовый запрет "sro — не число" модель (4B, Q4_K_M)
# слушается ненадёжно — 4/36 файлов всё равно кладут в sro ОГРН/ИНН/КПП
# соседней организации. Промпт-итерации дальше дают шум (чинят одни файлы,
# ломают другие, см. handoff §R.7) — надёжнее детерминированный код-сайд
# фильтр, тот же принцип, что is_valid_inn/is_valid_ogrn_any для debtor.
_SRO_REQUISITE_PREFIX_RE = re.compile(r"^\s*(?:ИНН|ОГРН|ОГРНИП|КПП|№)\b", re.IGNORECASE)


def _looks_like_requisite(s: str) -> bool:
    s = (s or "").strip()
    if not s:
        return False
    if _SRO_REQUISITE_PREFIX_RE.match(s):
        return True
    digits = sum(c.isdigit() for c in s)
    return digits / len(s) > 0.5


def _sanitize(parsed: dict) -> dict:
    """Код-сайд предохранитель (тот же принцип, что в llm_bench_run.py)."""
    if not isinstance(parsed, dict):
        return parsed
    debtor = parsed.get("debtor")
    if isinstance(debtor, dict):
        if debtor.get("inn") and not is_valid_inn(debtor["inn"]):
            debtor["inn"] = ""
        if debtor.get("ogrn") and not is_valid_ogrn_any(debtor["ogrn"]):
            debtor["ogrn"] = ""
        if debtor.get("birthDate") and not _DATE_RE.match(debtor["birthDate"].strip()):
            debtor["birthDate"] = ""
    manager = parsed.get("manager")
    if isinstance(manager, dict) and _looks_like_requisite(manager.get("sro", "")):
        manager["sro"] = ""
    if parsed.get("entityType") not in _VALID_TYPES:
        parsed["entityType"] = ""
    return parsed


def _match_array(regex_list: list, llm_list: list, fields: tuple, name_field: str = "name") -> tuple:
    """Жадное сопоставление regex-эталона с LLM-ответом для массивных ролей
    (debtors/thirdParties/properties): порядок у модели может отличаться от
    regex, поэтому сопоставляем по `name_field` (`_fuzzy_match`), не по
    индексу — для properties это "description", у остальных ролей "name".

    Возвращает (field_total, field_match) — dict'ы {field: count}, ключи —
    элементы `fields`. Regex-запись без пары (LLM не нашла соответствия) —
    mismatch по ВСЕМ её непустым полям. Лишние LLM-записи без пары regex не
    штрафуются (не с чем сравнивать) — не участвуют в счёте вообще."""
    field_total: dict = {f: 0 for f in fields}
    field_match: dict = {f: 0 for f in fields}
    llm_pool = [x for x in llm_list if isinstance(x, dict)]
    used = [False] * len(llm_pool)
    for reg in regex_list:
        reg_name = reg.get(name_field, "")
        best_idx, best_score = None, False
        for i, llm_item in enumerate(llm_pool):
            if used[i]:
                continue
            if _fuzzy_match(reg_name, llm_item.get(name_field, "")):
                best_idx, best_score = i, True
                break
        pair = llm_pool[best_idx] if best_idx is not None else {}
        if best_idx is not None:
            used[best_idx] = True
        for f in fields:
            reg_val = reg.get(f, "") or ""
            if not reg_val:
                continue
            field_total[f] += 1
            if best_score and _fuzzy_match(reg_val, pair.get(f, "")):
                field_match[f] += 1
    return field_total, field_match


def physical_cores(default: int = 8) -> int:
    """Честное число ПОТОКОВ под инференс. `n_threads=8` был захардкожен под
    машину разработки (8 физических / 16 логических); на чужой машине это
    ловит переподписку по HT, а на слабой — наоборот, просит больше ядер, чем
    есть. psutil в зависимостях backend'а нет и тянуть его ради одного числа
    не стоит, wmic на свежих сборках Windows 11 уже выпилен — поэтому берём
    только то, что есть в stdlib:
      - Linux: набор РАЗРЕШЁННЫХ процессу CPU (в контейнере он меньше общего);
      - иначе: половина логических как гипотеза SMT.
    Зажимаем в [4, 16] — на 2-ядерной машине смысла нет, выше 16 у 4B-модели
    отдача уже отрицательная."""
    try:
        logical = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except AttributeError:
        import multiprocessing
        logical = multiprocessing.cpu_count()
    except Exception:
        return default
    physical = logical // 2 if (logical >= 4 and logical % 2 == 0) else logical
    # ОДНО ядро всегда оставляем системе. Потоки llama.cpp работают на
    # busy-wait: они не засыпают в ожидании, а жгут ядро целиком, поэтому
    # инференс «на все ядра» подвешивает интерфейс всего ПК, а не только наш.
    # Юрист работает не в одном нашем окне — фоновый слой не имеет права
    # забирать машину.
    return max(1, min(16, (physical - 1) or 1))


def lower_process_priority() -> str:
    """Опустить приоритет процесса ниже обычного. Для фонового слоя это
    важнее числа потоков: при равном приоритете ОС делит время поровну и
    инференс «честно» отбирает ядра у браузера и Word, из-за чего подвисает
    весь ПК. Ниже обычного — планировщик вытесняет наши потоки, как только
    что-то нужно пользователю, а на простаивающей машине они всё равно
    получают всё время, то есть плата по скорости близка к нулю.

    Без psutil: на Windows через ctypes SetPriorityClass, на Unix — os.nice.
    Возвращает описание применённого режима (идёт в summary)."""
    try:
        if sys.platform == "win32":
            import ctypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.kernel32.SetPriorityClass(
                handle, BELOW_NORMAL_PRIORITY_CLASS)
            return "below_normal" if ok else "failed"
        os.nice(10)
        return "nice+10"
    except Exception as exc:
        return f"failed: {type(exc).__name__}"


def process_rss_mb() -> float:
    """Резидентная память процесса, МБ. Без psutil (его нет в зависимостях):
    на Windows через GetProcessMemoryInfo, на Linux через /proc/self/statm.
    Нужна, чтобы цена кеша префикса была видна в отчёте, а не только выигрыш
    по времени — на машине с 8 ГБ лишний гигабайт означает своп."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class _PMC(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            # Без объявления типов ctypes считает аргументы int и усекает
            # 64-битный HANDLE — вызов молча возвращает 0.
            ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            # На современных Windows функция живёт в kernel32 под именем
            # K32GetProcessMemoryInfo; psapi.dll остаётся как совместимость,
            # но не во всех сборках — поэтому сначала kernel32.
            fn = getattr(ctypes.windll.kernel32, "K32GetProcessMemoryInfo", None)
            if fn is None:
                fn = ctypes.windll.psapi.GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            if not fn(handle, ctypes.byref(pmc), pmc.cb):
                return 0.0
            # WorkingSetSize включает страницы mmap-нутого файла модели —
            # они файловые, вытесняются без свопа и завышают «цену» процесса.
            # PagefileUsage (приватная память) — то, за что реально платит ОЗУ.
            return round(pmc.PagefileUsage / 2 ** 20, 1)
        with open("/proc/self/statm", "r") as f:
            pages = int(f.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 2 ** 20, 1)
    except Exception:
        return 0.0


def _run_config(args, load_sec: float) -> dict:
    """Конфигурация прогона в summary. Раньше не писалась вообще — из-за чего
    базовая линия v6 оказалась невоспроизводимой по собственному артефакту
    (неизвестны n_ctx/n_threads/max_tokens), а без этого сравнение «до/после»
    недоказуемо."""
    try:
        import llama_cpp
        ver = getattr(llama_cpp, "__version__", "?")
    except Exception:
        ver = "?"
    return {
        "windows": args.windows, "no_reps_in_main": args.no_reps_in_main,
        "priority": getattr(args, "_priority_mode", "normal"),
        "prompt_cache_mb": args.prompt_cache_mb, "rss_mb": process_rss_mb(),
        "draft_lookup": args.draft_lookup, "draft_ngram": args.draft_ngram,
        "compact_json": args.compact_json,
        "n_threads_batch": args.n_threads_batch or "по умолчанию (логические)",
        "n_ctx": args.n_ctx, "n_threads": args.n_threads,
        "n_batch": args.n_batch, "n_ubatch": args.n_ubatch,
        "max_tokens": args.max_tokens, "dump": os.path.basename(args.dump),
        "llama_cpp_version": ver, "load_sec": round(load_sec, 1),
    }


def _call_aggregates(results: list) -> dict:
    """Средние на файл: токены и split prefill/decode (этап 1). Считаются по
    ВСЕМ вызовам файла, а не только основному — иначе изолированные вызовы
    (representatives/collateral/valuation) выпадают из картины."""
    per_file = [r.get("calls") or [] for r in results]
    if not any(per_file):
        return {}
    n = len(per_file)

    def _avg(key: str) -> float:
        return round(sum(sum(c.get(key, 0) for c in calls) for calls in per_file) / n, 1)

    return {
        "prompt_tokens_avg": _avg("prompt_tokens"),
        "completion_tokens_avg": _avg("completion_tokens"),
        "prefill_sec_avg": _avg("prefill_sec"),
        "decode_sec_avg": _avg("decode_sec"),
    }


# Поля manager, у которых есть предпосылка "нужно ли вообще спрашивать ЭТО
# поле у ЭТОГО документа" (df_v7, см. handoff §R.10) — не оцениваем то, что
# сознательно не запрашивали, иначе цифра нечестно занижена промахом по полю,
# которого в схеме для этого документа не было.
_GATED_BY_FIO = {"managerName", "managerAddress"}
_GATED_BY_SRO = {"sroName"}

# regex-имя поля -> ключ в LLM-ответе (у роли своя раскладка).
_BANKRUPTCY_FIELD_MAP = {
    "debtorName": "name", "applicantAddress": "address",
    "inn": "inn", "ogrn": "ogrn", "birthDate": "birthDate",
    "birthPlace": "birthPlace", "managerName": "name",
    "managerAddress": "address", "sroName": "sro",
}


def score_bankruptcy(results: list) -> tuple:
    """Чистый скоринг банкротной схемы: results -> (field_total, field_match).
    Раньше жил инлайном в main(), а llm_bench_rescore.py держал свою копию —
    и та копия отстала: в ней нет гейтинга df_v7 по need_fio/need_sro, то есть
    rescore штрафовал за поля, которых в схеме документа не было."""
    field_total: dict = {}
    field_match: dict = {}
    for r in results:
        parsed = r["parsed"] or {}
        need_fio = r.get("need_manager_fio", True)
        need_sro = r.get("need_manager_sro", True)
        for role, fields in r["regex_roles"].items():
            llm_role = parsed.get(role) or {}
            if not isinstance(llm_role, dict):
                llm_role = {}
            for f, regex_val in fields.items():
                if not regex_val:
                    continue
                if f in _GATED_BY_FIO and not need_fio:
                    continue
                if f in _GATED_BY_SRO and not need_sro:
                    continue
                key = f"{role}.{f}"
                field_total[key] = field_total.get(key, 0) + 1
                sub = _BANKRUPTCY_FIELD_MAP.get(f, f)
                llm_val = llm_role.get(sub, "")
                matcher = _fuzzy_match_sro if sub == "sro" else _fuzzy_match
                if matcher(regex_val, llm_val):
                    field_match[key] = field_match.get(key, 0) + 1
    return field_total, field_match


def dump_fingerprint(docs: list) -> str:
    """Отпечаток входных данных прогона: сколько файлов и хеш их содержимого.

    Зачем: корпус живёт ВНЕ репозитория и меняется. Однажды в файл корпуса
    вставили строку-мусор посреди серии замеров, и цифры двух прогонов стали
    несравнимы — понять это удалось только на глаз. Отпечаток в шапке отчёта
    показывает такое сразу, а не через полчаса.

    Считаем по ОКНАМ, которые реально видит модель, а не по файлам на диске:
    правка документа за пределами окна на результат не влияет, и объявлять
    из-за неё замеры несравнимыми было бы ложной тревогой.
    """
    h = hashlib.sha256()
    for doc in sorted(docs, key=lambda d: d.get("file", "")):
        h.update(str(doc.get("file", "")).encode("utf-8"))
        for key in ("header_window", "prayer_window",
                    "collateral_block", "valuation_block"):
            part = str(doc.get(key, "") or "")
            h.update(("|%d|" % len(part)).encode("utf-8"))
            h.update(part.encode("utf-8"))
    return "%d файлов, %s" % (len(docs), h.hexdigest()[:12])


def score_mortgage(results: list) -> tuple:
    """Чистый скоринг ипотечной схемы: results -> (field_total, field_match).
    Вынесен из _report_mortgage, чтобы llm_bench_rescore.py считал качество
    ТЕМ ЖЕ кодом, а не своей копией — банкротная ветка rescore именно так и
    разъехалась (ручной дубль цикла)."""
    array_fields = ("name", "address", "inn", "birthDate")
    field_total: dict = {}
    field_match: dict = {}

    def _bump(key: str, total: int, match: int):
        field_total[key] = field_total.get(key, 0) + total
        field_match[key] = field_match.get(key, 0) + match

    for r in results:
        parsed = r["parsed"] or {}
        mr = r["mortgage_regex"]

        court_llm = parsed.get("court") or {}
        for f in ("name", "address"):
            reg_val = mr["court"].get(f, "")
            if reg_val:
                _bump(f"court.{f}", 1, 1 if _fuzzy_match(reg_val, court_llm.get(f, "")) else 0)

        d_total, d_match = _match_array(mr["debtors"], parsed.get("debtors") or [], array_fields)
        for f in array_fields:
            _bump(f"debtors.{f}", d_total[f], d_match[f])

        tp_fields = ("name", "address", "inn")
        tp_total, tp_match = _match_array(mr["thirdParties"], parsed.get("thirdParties") or [], tp_fields)
        for f in tp_fields:
            _bump(f"thirdParties.{f}", tp_total[f], tp_match[f])

        reps_llm = parsed.get("representatives") or {}
        for f in ("plaintiff", "defendant"):
            reg_val = mr["representatives"].get(f, "")
            if reg_val:
                _bump(f"representatives.{f}", 1, 1 if _fuzzy_match(reg_val, reps_llm.get(f, "")) else 0)

        fin_llm = parsed.get("financial") or {}
        fin_map = {
            "mortgageCreditAmount111": "creditAmount", "mortgageCreditTerm112": "creditTermMonths",
            "mortgageInterestRate113": "interestRate", "mortgagePenaltyRate114": "penaltyRate",
        }
        for regex_key, llm_key in fin_map.items():
            reg_val = mr["financial"].get(regex_key, "")
            if reg_val:
                _bump(f"financial.{llm_key}", 1, 1 if _fuzzy_match(reg_val, fin_llm.get(llm_key, "")) else 0)

        prop_fields = ("description", "cadastralNumber", "address", "value",
                       "startingPrice", "npcStrategy", "appraisalReport", "egrnRecord")
        p_total, p_match = _match_array(
            mr.get("properties") or [], parsed.get("properties") or [],
            prop_fields, name_field="description")
        for f in prop_fields:
            _bump(f"properties.{f}", p_total[f], p_match[f])

    return field_total, field_match


def _report_mortgage(results: list, args, load_sec: float = 0.0) -> None:
    """Отдельный отчёт для df_mortgage — своя схема (court/debtors/
    thirdParties/representatives/financial), не смешивается с банкротными
    метриками df_v7/df_v8."""
    times = [r["elapsed_sec"] for r in results]
    valid_json = sum(1 for r in results if r["parsed"] is not None)
    field_total, field_match = score_mortgage(results)

    overall_total = sum(field_total.values())
    overall_match = sum(field_match.values())

    print("\n" + "=" * 78)
    print(f"ИТОГ [{args.label}] (ипотека)")
    print("=" * 78)
    print(f"Модель: {os.path.basename(args.model)}  промпт={args.prompt}")
    if getattr(args, "corpus_fingerprint", None):
        print(f"Корпус: {args.corpus_fingerprint}")
    print(f"Файлов: {len(results)}  Время/файл: мин={min(times):.1f}с "
          f"макс={max(times):.1f}с среднее={sum(times)/len(times):.1f}с")
    print(f"Валидный JSON: {valid_json}/{len(results)} = {valid_json/len(results):.0%}")
    print(f"Совпадение полей (общее): {overall_match}/{overall_total} = "
          f"{(overall_match/overall_total if overall_total else 0):.0%}")
    for key in sorted(field_total):
        total = field_total[key]
        match = field_match.get(key, 0)
        if total:
            print(f"  {key:24} {match}/{total} = {match/total:.0%}")

    summary = {
        "label": args.label, "model": os.path.basename(args.model),
        "prompt": args.prompt, "n_files": len(results),
        "time_min": min(times), "time_max": max(times), "time_avg": sum(times) / len(times),
        "valid_json": valid_json, "valid_json_rate": valid_json / len(results),
        "overall_match": overall_match, "overall_total": overall_total,
        "overall_rate": (overall_match / overall_total) if overall_total else 0,
        "field_total": field_total, "field_match": field_match,
    }
    summary.update(_run_config(args, load_sec))
    summary.update(_call_aggregates(results))
    out_path = os.path.join(_THIS, f"llm_bench_results_{args.label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=1)
    print(f"\n-> {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", required=True,
                     choices=list(DF_PROMPTS) + ["df_v7", "df_v8", "df_mortgage"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--n-ctx", type=int, default=4096)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--n-threads", type=int, default=0,
                    help="0 — определить автоматически (physical_cores)")
    # Prefill — половина времени прогона (замер этапа 1), а идёт он батчами по
    # n_batch: ~6100 токенов основного вызова — это 12 батчей по умолчанию.
    # Эффект подъёма батча на CPU не очевиден (меняются формы GEMM и попадания
    # в кеш) — ручка нужна именно чтобы ЗАМЕРИТЬ, а не чтобы поверить.
    # Режим окна основного вызова (этап 6). Раздельные значения, а не набор
    # булевых флагов: за один прогон меняется РОВНО одно, иначе непонятно,
    # что дало эффект (правило журнала прогонов).
    #   full     — как в v6: 9000 симв. шапки + 2000 симв. просительной части;
    #   noprayer — только шапка (просительная часть ипотечной схеме не нужна);
    #   narrow   — якорное окно сторон + якорный финансовый блок.
    ap.add_argument("--windows", choices=("full", "noprayer", "narrow"),
                    default="full")
    # Этап 5a: не просить у основного вызова representatives — его вывод всё
    # равно перезаписывается изолированным вызовом.
    ap.add_argument("--no-reps-in-main", action="store_true")
    # Отзывчивость ПК под фоновым инференсом: приоритет ниже обычного и
    # запас ядер. По умолчанию ВЫКЛЮЧЕНО, чтобы замеры скорости остались
    # сопоставимы с базой; для прода режим обязателен (см. журнал прогонов).
    ap.add_argument("--low-priority", action="store_true")
    # Кеш префикса (этап 4b). После сужения окон 2258 из 3389 входных токенов
    # основного вызова — это НЕИЗМЕННЫЙ system+few-shot, и он пересчитывается
    # с нуля на каждом файле. llama-cpp умеет переиспользовать KV по общему
    # префиксу сам, но только с ПРЕДЫДУЩИМ вызовом — а у нас 4 разных промпта
    # вперемешку, они убивают префикс друг друга. LlamaRAMCache держит по
    # состоянию на каждый промпт. Цена — память: замерено 133 КБ на токен,
    # то есть ~0.9 ГБ на все четыре. 0 — выключено.
    ap.add_argument("--prompt-cache-mb", type=int, default=0)
    # Спекулятивное декодирование по n-граммам промпта. Наша выдача — почти
    # дословное копирование из входа (ФИО, ИНН, адреса, кадастровые номера),
    # то есть черновик угадывается прямо из промпта, без второй модели.
    # Декодирование СПЕКУЛЯТИВНОЕ, а не приблизительное: предложения
    # проверяются полной моделью, результат тот же, что и при обычной
    # генерации. Подвох в другом — llama-cpp при draft_model принудительно
    # включает logits_all, а это логиты на КАЖДЫЙ токен промпта. Замерить.
    # 0 — выключено; иначе число токенов в одном предложении черновика.
    ap.add_argument("--draft-lookup", type=int, default=0)
    ap.add_argument("--draft-ngram", type=int, default=2)
    # Компактный JSON грамматикой (см. _COMPACT_JSON_GBNF): −146 ток/файл.
    ap.add_argument("--compact-json", action="store_true")
    # llama-cpp по умолчанию ставит n_threads_batch = число ЛОГИЧЕСКИХ ядер
    # (llama.py:306), то есть prefill всё это время шёл на 16 потоках при 8
    # физических — та самая переподписка по гиперпоточности. 0 — как есть.
    ap.add_argument("--n-threads-batch", type=int, default=0)
    ap.add_argument("--n-batch", type=int, default=512)
    ap.add_argument("--n-ubatch", type=int, default=512)
    ap.add_argument("--dump", default=DUMP_PATH)
    args = ap.parse_args()
    if args.n_threads <= 0:
        args.n_threads = physical_cores()
    global _COMPACT_ON
    _COMPACT_ON = args.compact_json
    priority_mode = lower_process_priority() if args.low_priority else "normal"
    args._priority_mode = priority_mode

    if not os.path.isfile(args.dump):
        print(f"Нет дампа {args.dump} — сначала запусти llm_bench_phase1_dump.py.")
        return 1

    from llama_cpp import Llama

    is_mortgage = args.prompt == "df_mortgage"
    dynamic_schema = args.prompt in ("df_v7", "df_v8", "df_mortgage")
    if not dynamic_schema:
        prompt_cfg = DF_PROMPTS[args.prompt]
        system = prompt_cfg["system"]
        use_grammar = prompt_cfg["grammar"]
        fewshot = prompt_cfg["fewshot"]
    else:
        use_grammar = False  # df_v7/df_v8/df_mortgage не используют grammar-режим
        if is_mortgage:
            # Фиксированная схема (не зависит от per-doc need_fio/entityType,
            # как df_v7/df_v8) — собираем один раз, а не в цикле по документам.
            prompt_cfg = build_df_mortgage_prompt(
                with_representatives=not args.no_reps_in_main)
            system = prompt_cfg["system"]
            fewshot = prompt_cfg["fewshot"]

    print(f"Модель: {args.model}")
    print(f"Промпт: {args.prompt}  grammar={use_grammar}  "
          f"n_threads={args.n_threads}  n_batch={args.n_batch}/{args.n_ubatch}")
    t_load0 = time.perf_counter()
    draft = None
    if args.draft_lookup > 0:
        from llama_cpp.llama_speculative import LlamaPromptLookupDecoding
        draft = LlamaPromptLookupDecoding(max_ngram_size=args.draft_ngram,
                                          num_pred_tokens=args.draft_lookup)
    # llama-cpp при draft_model принудительно ставит self._logits_all=True
    # (llama.py:344), но буфер логитов выделяет по ПАРАМЕТРУ logits_all
    # (llama.py:475) — размеры расходятся и eval падает с broadcast-ошибкой.
    # Обход: выставить параметр явно. Цена — буфер n_ctx x n_vocab x 4 байта,
    # то есть 4.3 ГБ при n_ctx=4096 и 8.6 ГБ при 8192 (словарь Gemma — 262к).
    llm = Llama(model_path=args.model, n_ctx=args.n_ctx,
                n_threads=args.n_threads, n_batch=args.n_batch,
                n_ubatch=args.n_ubatch, draft_model=draft,
                logits_all=bool(draft), verbose=False,
                **({"n_threads_batch": args.n_threads_batch}
                   if args.n_threads_batch > 0 else {}))
    if args.prompt_cache_mb > 0:
        from llama_cpp import LlamaRAMCache
        llm.set_cache(LlamaRAMCache(capacity_bytes=args.prompt_cache_mb * 2 ** 20))
    load_sec = time.perf_counter() - t_load0
    print(f"Модель загружена за {load_sec:.1f} с (разово на процесс)\n")

    with open(args.dump, "r", encoding="utf-8") as f:
        docs = json.load(f)
    # Отпечаток входа — до прогона, чтобы несравнимость была видна сразу.
    args.corpus_fingerprint = dump_fingerprint(docs)
    print(f"Корпус: {args.corpus_fingerprint}", flush=True)
    if is_mortgage:
        # Своя, отдельная от банкротной, роль-схема — гоняем ТОЛЬКО ипотечные
        # файлы (documentType == mortgage_claim), не смешиваем с df_v7/df_v8.
        docs = [d for d in docs if d.get("mortgage_regex") is not None]
        if not docs:
            print("В дампе нет ипотечных документов (mortgage_regex пуст).")
            return 1

    # temperature/max_tokens задаёт _timed_call; здесь остаётся только то, что
    # зависит от промпта (grammar-режим у df_v1..df_v6).
    grammar_kwargs = {"response_format": {"type": "json_object"}} if use_grammar else {}

    results = []
    for doc in docs:
        rel = doc["file"]
        # raw_text есть только в дампах, снятых после правки этапа 6; на
        # старых берём шапку — все ипотечные якоря укладываются в её 9000
        # символов (проверено на корпусе), поэтому сужение работает и без
        # перегенерации дампа.
        source = doc.get("raw_text") or doc["header_window"]
        window = doc["header_window"]
        prayer = doc.get("prayer_window", "")
        if args.windows == "full" and prayer:
            window = window + "\n[...]\n" + prayer
        elif args.windows == "narrow":
            parties = extract_parties_window(source)
            financial = extract_financial_block(source)
            window = parties + ("\n[...]\n" + financial if financial else "")
        entity_type_true = doc.get("entity_type", "")
        regex_roles = doc["regex_roles"]
        need_fio = doc.get("need_manager_fio", True)
        need_sro = doc.get("need_manager_sro", True)

        if args.prompt == "df_v8":
            regex_entity_type = doc.get("entity_type", "")
            prompt_cfg = build_df_v8_prompt(need_fio, need_sro, regex_entity_type)
            system = prompt_cfg["system"]
            fewshot = prompt_cfg["fewshot"]
        elif is_mortgage:
            pass  # system/fewshot фиксированы, собраны один раз до цикла
        elif dynamic_schema:
            prompt_cfg = build_df_v7_prompt(need_fio, need_sro)
            system = prompt_cfg["system"]
            fewshot = prompt_cfg["fewshot"]

        msgs = [{"role": "system", "content": system}]
        for u, a in fewshot:
            msgs.append({"role": "user", "content": u})
            msgs.append({"role": "assistant", "content": a})
        msgs.append({"role": "user", "content": f"Текст:\n«{window}»"})

        _CALLS.clear()
        raw, meta = _timed_call(llm, msgs, args.max_tokens, "main", **grammar_kwargs)
        if meta.get("error"):
            print(f"[ОШИБКА генерации] {rel}: {meta['error']}")
        elapsed = meta["elapsed_sec"]

        parsed = _extract_json(raw)
        leak_markers = DF_MORTGAGE_LEAK_MARKERS if is_mortgage else DF_V4_LEAK_MARKERS
        leaked = _check_leak(parsed, leak_markers) if isinstance(parsed, dict) else 0
        parsed = _sanitize_mortgage(parsed) if is_mortgage else _sanitize(parsed)
        if is_mortgage and isinstance(parsed, dict):
            # representatives — ОТДЕЛЬНЫЙ изолированный вызов на блок
            # «Представитель истца/ответчика:», а не то, что дал общий
            # вызов выше (см. комментарий у _fetch_representative: 12%→100%
            # на изоляции). Общий вызов результат по representatives всё
            # равно даёт — он просто здесь ПЕРЕЗАПИСЫВАЕТСЯ.
            plaintiff, rep_elapsed_p = _fetch_representative(llm, window, "plaintiff")
            defendant, rep_elapsed_d = _fetch_representative(llm, window, "defendant")
            parsed["representatives"] = {"plaintiff": plaintiff, "defendant": defendant}
            elapsed += rep_elapsed_p + rep_elapsed_d
            # mortgageProperties — та же логика (ДВА изолированных вызова,
            # план §5), собственные якорные блоки из phase1-дампа.
            props, props_elapsed = _fetch_mortgage_properties(
                llm, doc.get("collateral_block", ""), doc.get("valuation_block", ""))
            parsed["properties"] = props
            elapsed += props_elapsed
        results.append({
            "file": rel, "elapsed_sec": elapsed, "raw": raw,
            # Метрики каждого вызова (этап 1) — включая raw изолированных
            # вызовов, который раньше выбрасывался: без него правки парсинга
            # и слияния properties нельзя перепроверить офлайн.
            "calls": list(_CALLS),
            "parsed": parsed, "entity_type_true": entity_type_true,
            "regex_roles": regex_roles, "mortgage_regex": doc.get("mortgage_regex"),
            "leaked_fields": leaked,
            "need_manager_fio": need_fio, "need_manager_sro": need_sro,
        })
        status = "JSON ok" if parsed is not None else "JSON НЕВАЛИДЕН"
        if is_mortgage:
            n_deb = len((parsed or {}).get("debtors") or [])
            print(f"[{elapsed:5.1f} с] {status:16} debtors={n_deb} {rel}")
        else:
            et_llm = (parsed or {}).get("entityType", "?") if parsed else "?"
            et_mark = "OK" if et_llm == entity_type_true else "MISMATCH"
            print(f"[{elapsed:5.1f} с] {status:16} entityType={et_llm:10} "
                  f"({et_mark:8}) {rel}")

    if is_mortgage:
        _report_mortgage(results, args, load_sec)
        return 0

    times = [r["elapsed_sec"] for r in results]
    valid_json = sum(1 for r in results if r["parsed"] is not None)
    entity_correct = sum(
        1 for r in results
        if r["parsed"] and r["parsed"].get("entityType") == r["entity_type_true"]
    )

    field_total, field_match = score_bankruptcy(results)

    overall_total = sum(field_total.values())
    overall_match = sum(field_match.values())
    total_leaked = sum(r["leaked_fields"] for r in results)
    files_leaked = sum(1 for r in results if r["leaked_fields"])

    print("\n" + "=" * 78)
    print(f"ИТОГ [{args.label}]")
    print("=" * 78)
    print(f"Модель: {os.path.basename(args.model)}  промпт={args.prompt}")
    print(f"Загрузка модели: {load_sec:.1f} с")
    print(f"Файлов: {len(results)}  Время/файл: мин={min(times):.1f}с "
          f"макс={max(times):.1f}с среднее={sum(times)/len(times):.1f}с")
    print(f"Валидный JSON: {valid_json}/{len(results)} = {valid_json/len(results):.0%}")
    print(f"Утечка few-shot (обнулено предохранителем): {total_leaked} полей "
          f"в {files_leaked} файлах")
    print(f"entityType верно определён: {entity_correct}/{len(results)} = "
          f"{entity_correct/len(results):.0%}")
    print(f"Совпадение полей (общее): {overall_match}/{overall_total} = "
          f"{(overall_match/overall_total if overall_total else 0):.0%}")
    for key in sorted(field_total):
        total = field_total[key]
        match = field_match.get(key, 0)
        print(f"  {key:24} {match}/{total} = {match/total:.0%}")

    summary = {
        "label": args.label, "model": os.path.basename(args.model),
        "prompt": args.prompt, "load_sec": load_sec, "n_files": len(results),
        "time_min": min(times), "time_max": max(times),
        "time_avg": sum(times) / len(times),
        "valid_json": valid_json, "valid_json_rate": valid_json / len(results),
        "leaked_fields": total_leaked, "leaked_files": files_leaked,
        "entity_correct": entity_correct, "entity_correct_rate": entity_correct / len(results),
        "overall_match": overall_match, "overall_total": overall_total,
        "overall_rate": (overall_match / overall_total) if overall_total else 0,
        "field_total": field_total, "field_match": field_match,
    }
    summary.update(_run_config(args, load_sec))
    summary.update(_call_aggregates(results))
    out_path = os.path.join(_THIS, f"llm_bench_results_{args.label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=1)
    print(f"\n-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
