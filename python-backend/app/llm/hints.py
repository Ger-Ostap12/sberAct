# -*- coding: utf-8 -*-
"""Теневые подсказки по полям: второе независимое мнение о разборе.

Слой ничего не подставляет и не исправляет — только отмечает расхождения,
чтобы юрист перепроверил конкретное поле. Тот же принцип, что у
debtorNameWarning и fieldQuality.

Раньше этот код жил в конвертере (там были llama-cpp-python и файл модели).
С переездом на llama-server зависимость исчезла: считает отдельный процесс, а
нам нужен только локальный HTTP. Заодно ушла нелепость, при которой ради
подсказок к обычному DOCX поднимался docling на 3.5 ГБ.
"""
from __future__ import annotations

import logging
import re

from . import client, server
from .fields import (
    BLOCKS,
    PROGRESS_KEYS,
    SANITY_BLOCK,
    SANITY_ENABLED,
    block_by_key,
    field_key,
    field_label,
)
from .matching import core_name, fuzzy_match, norm
from .parsing import check_leak, sanitize_mortgage
from .prompts import (
    DF_MORTGAGE_LEAK_MARKERS,
    build_df_mortgage_collateral_prompt,
    build_df_mortgage_court_prompt,
    build_df_mortgage_prompt,
    build_df_mortgage_valuation_prompt,
    build_field_sanity_prompt,
)
from .windows import (
    extract_collateral_block,
    extract_court_window,
    extract_parties_window,
    extract_valuation_block,
)

logger = logging.getLogger(__name__)

# Во сколько раз одно значение должно быть длиннее другого, чтобы вхождение
# подстроки перестало считаться согласием. Причина конкретная: в документ между
# названием суда и адресом вставили строку-мусор, разбор взял мусор, а модель
# вернула «мусор + настоящий адрес» — и правило «одно внутри другого» назвало
# это согласием, хотя показать разницу было бы полезно. Замер на корпусе: при
# пороге 1.5 подсказками становятся 3 согласия из 128, при 2.0 — ни одного, а
# тот самый случай ловится с отношением ~3.2.
_LENGTH_RATIO_LIMIT = 2.0


def _hint(field: str, label: str, block_key: str, regex_val: str, llm_val: str):
    """Одна подсказка. None — если сравнивать нечего или значения согласованы:
    молчание и есть нормальный исход."""
    regex_val = (regex_val or "").strip()
    llm_val = str(llm_val or "").strip()
    # Модель ничего не нашла — сказать нечего. Обратный случай (пусто у
    # разбора, но есть у модели) НЕ пропускаем: раньше он тоже молчал, и это
    # было хуже всего именно там, где помощь нужнее — поле пустое, и юрист не
    # знает, потому ли, что значения в документе нет, или разбор его потерял.
    if not llm_val:
        return None
    if regex_val and fuzzy_match(regex_val, llm_val):
        # fuzzy_match намеренно мягкий: он обслуживает МЕТРИКУ бенчмарка, где
        # «нашла по сути то же» — это успех, и трогать его нельзя, иначе цифра
        # качества станет несравнимой. Но как сигнал юристу он слишком мягкий:
        # сильная разница в длине означает, что одна из сторон захватила лишнее
        # (или потеряла половину), и это стоит показать.
        # Длину меряем по ЯДРУ названия, без слов орг-правовой формы: иначе
        # «ООО «Ромашка»» против полного наименования даёт трёхкратную разницу
        # на ровном месте и ложную тревогу.
        a, b = len(norm(core_name(regex_val))), len(norm(core_name(llm_val)))
        if max(a, b) <= _LENGTH_RATIO_LIMIT * max(1, min(a, b)):
            return None
    return {
        "field": field,
        "label": label,
        "block": block_key,
        "regexValue": regex_val,
        "llmValue": llm_val,
        "agrees": False,
    }


def _regex_rows(block: dict, regex_values: dict) -> list:
    """Строки формы восстанавливаем из ключей вида debtors[3].inn: сам список
    строк нам не присылают, присылают плоскую карту значений."""
    prefix = block["prefix"]
    idx_re = re.compile(r"^%s\[(\d+)\]\.(\w+)$" % re.escape(prefix))
    rows: dict = {}
    for key, val in regex_values.items():
        m = idx_re.match(key)
        if m:
            rows.setdefault(int(m.group(1)), {})[m.group(2)] = val
    if not rows:
        return []
    return [rows.get(i, {}) for i in range(max(rows) + 1)]


def _pair_rows(regex_rows: list, llm_rows: list, name_field: str) -> list:
    """Сопоставляет записи LLM со строками формы. Порядок у модели может не
    совпадать с порядком разбора, а подсказку нужно повесить на КОНКРЕТНУЮ
    строку — иначе юрист увидит замечание к чужому ответчику. Сопоставляем по
    имени, жадно и без повторов; для чего пары не нашлось — подсказок не
    будет, это честнее, чем угадать строку."""
    pairs = []
    used = set()
    for i, reg in enumerate(regex_rows):
        reg_name = str((reg or {}).get(name_field, "") or "")
        best = None
        for j, cand in enumerate(llm_rows):
            if j in used or not isinstance(cand, dict):
                continue
            if reg_name and fuzzy_match(reg_name, str(cand.get(name_field, "") or "")):
                best = j
                break
        if best is None:
            continue
        used.add(best)
        pairs.append((i, llm_rows[best]))
    return pairs


def _flat_hints(block: dict, data: dict, regex_values: dict) -> list:
    hints = []
    for schema_field in block["map"]:
        key = field_key(block, schema_field)
        h = _hint(key, field_label(block, schema_field), block["key"],
                  regex_values.get(key, ""), (data or {}).get(schema_field, ""))
        if h:
            hints.append(h)
    return hints


def _array_hints(block: dict, rows: list, regex_values: dict) -> list:
    """Подсказки только по строкам, которые НАШЁЛ РАЗБОР. Выдуманные моделью
    строки игнорируются целиком, и это не придирка: замер на корпусе показал,
    что при отсутствии третьих лиц модель кладёт туда банк-истца и приписывает
    ему ИНН — каждый раз новый. Сообщать о таких находках значило бы добавить
    ~2.9 ложной подсказки на документ вместо 0.1."""
    ordered = _regex_rows(block, regex_values)
    if not ordered:
        return []
    name_field = "name" if "name" in block["map"] else "description"

    hints = []
    for i, llm_row in _pair_rows(ordered, rows or [], name_field):
        for schema_field in block["map"]:
            key = field_key(block, schema_field, i)
            h = _hint(key, field_label(block, schema_field), block["key"],
                      regex_values.get(key, ""), llm_row.get(schema_field, ""))
            if h:
                hints.append(h)
    return hints


def _sanity_items(regex_values: dict) -> list:
    """Заполненные поля формы в порядке экрана: [(ключ, метка, значение)]."""
    items = []
    for block in BLOCKS:
        if block["kind"] == "flat":
            for schema_field in block["map"]:
                key = field_key(block, schema_field)
                val = str(regex_values.get(key, "") or "").strip()
                if val:
                    items.append((key, field_label(block, schema_field), val))
            continue
        for i, _row in enumerate(_regex_rows(block, regex_values)):
            for schema_field in block["map"]:
                key = field_key(block, schema_field, i)
                val = str(regex_values.get(key, "") or "").strip()
                if val:
                    # Номер строки в метке: у ответчиков и объектов залога поля
                    # называются одинаково, и без него юрист не поймёт, к
                    # какому из них замечание.
                    label = field_label(block, schema_field)
                    items.append((key, "%s (%d)" % (label, i + 1), val))
    return items


def _sanity_hints(regex_values: dict) -> list:
    """Замечания о правдоподобии. Отключены замером — см. fields.SANITY_ENABLED."""
    items = _sanity_items(regex_values)
    if not items:
        return []
    listing = "\n".join("%d. %s: %s" % (n + 1, label, val)
                        for n, (_k, label, val) in enumerate(items))
    parsed = client.chat(build_field_sanity_prompt(), listing, 200, expect="array")

    hints, seen = [], set()
    for row in parsed or []:
        if not isinstance(row, dict):
            continue
        n = row.get("n")
        # Номер вне списка — это выдумка модели, а не замечание. Молча
        # отбрасываем: показать подсказку не к тому полю хуже, чем не показать.
        if not isinstance(n, int) or not (1 <= n <= len(items)) or n in seen:
            continue
        seen.add(n)
        key, label, val = items[n - 1]
        hints.append({
            "field": key, "label": label, "block": SANITY_BLOCK,
            "regexValue": val, "llmValue": "", "agrees": False,
            "reason": str(row.get("why", "") or "").strip()[:80],
        })
    return hints


# --- Представитель истца отдельным вызовом. В общем окне модель системно
#     брала название банка/филиала вместо ФИО человека: 1 файл из 8, и три
#     раунда текстовых правок промпта не сдвинули результат вообще. Изоляция
#     блока «Представитель истца:» дала 8 из 8 сразу — проблема была не в
#     сложности задачи, а в шуме вокруг.
_REP_BLOCK_RE = re.compile(
    r"Представитель\s+истца\s*:(.*?)(?:Ответчик|ИСКОВОЕ|Цена\s+иска|$)",
    re.IGNORECASE | re.DOTALL,
)

_REP_ONLY_SYSTEM = (
    "Ниже — короткий фрагмент искового заявления, блок «Представитель истца». "
    "В нём сначала может идти название банка/его филиала или отделения "
    "(организация — НЕ ответ), а затем ФИО конкретного человека (Фамилия Имя "
    "Отчество) — это и есть представитель. Верни СТРОГО JSON без пояснений: "
    "{\"name\": \"\"} — только ФИО человека. Если ФИО человека в тексте нет "
    "вообще — {\"name\": \"\"}."
)


def _fetch_representative(parties_window: str) -> str:
    """Пустая строка, если блока в тексте нет — не тратим вызов модели на
    заведомо пустой фрагмент."""
    m = _REP_BLOCK_RE.search(parties_window or "")
    block = m.group(1).strip() if m else ""
    if not block:
        return ""
    parsed = client.chat({"system": _REP_ONLY_SYSTEM, "fewshot": []}, block, 100)
    return str((parsed or {}).get("name", "") or "").strip()


def _mp_type_keyword(s: str) -> str:
    """Тип объекта залога по описанию — та же типология, что у regex-пути
    (_mp_type в document_analyzer.py)."""
    n = (s or "").lower()
    for needle, kind in (("участ", "участок"), ("дом", "дом"),
                         ("квартир", "квартира"), ("машино", "машиноместо"),
                         ("гараж", "гараж"), ("помещ", "помещение")):
        if needle in n:
            return kind
    return ""


def _fetch_properties(raw_text: str) -> list:
    """Два якорных вызова и слияние ПО ТИПУ ОБЪЕКТА: сумма из разбивки «в том
    числе дом — …» относится к конкретному объекту, а не размазывается по всем.
    Данные предмета ипотеки лежат в двух местах документа, разнесённых на
    тысячи символов, — отсюда и два вызова."""
    collateral_block = extract_collateral_block(raw_text)
    valuation_block = extract_valuation_block(raw_text)

    items = []
    if collateral_block:
        parsed = client.chat(build_df_mortgage_collateral_prompt(),
                             collateral_block, 500, expect="array")
        if isinstance(parsed, list):
            items = [x for x in parsed if isinstance(x, dict)]
    if not items:
        return []

    breakdown, npc, report = [], "", ""
    if valuation_block:
        val = client.chat(build_df_mortgage_valuation_prompt(), valuation_block, 400)
        if isinstance(val, dict):
            npc = val.get("npcStrategy", "") or ""
            report = val.get("appraisalReport", "") or ""
            breakdown = [b for b in (val.get("breakdown") or []) if isinstance(b, dict)]

    by_type = {}
    for b in breakdown:
        t = _mp_type_keyword(b.get("type", ""))
        if t:
            by_type[t] = b

    merged = []
    for item in items:
        vb = by_type.get(_mp_type_keyword(item.get("description", "")))
        # Единственная запись без разбивки — это общий итог, он и относится к
        # единственному объекту.
        if not vb and len(breakdown) == 1:
            vb = breakdown[0]
        merged.append({
            "description": item.get("description", "") or "",
            "cadastralNumber": item.get("cadastralNumber", "") or "",
            "address": item.get("address", "") or "",
            "egrnRecord": item.get("egrnRecord", "") or "",
            "value": (vb or {}).get("value", "") or "",
            "startingPrice": (vb or {}).get("startingPrice", "") or "",
            "npcStrategy": npc,
            "appraisalReport": report,
        })
    return merged


def warmup() -> dict:
    """Поднять сервер заранее. Замер: первый документ после запуска платил ~80с
    только за подъём весов модели с диска, и платил этим ожиданием юрист.
    Теперь это делает фон, пока он выбирает файл и категорию."""
    return server.start()


def run_hints(raw_text: str, regex_values: dict, on_block=None, should_cancel=None) -> list:
    """Прогоняет блоки ПО ПОРЯДКУ ЭКРАНА и отдаёт подсказки по мере готовности
    через on_block(block_key, hints). Юрист читает форму сверху вниз — то, что
    он увидит первым, должно быть проверено первым.

    should_cancel() проверяется между блоками: брошенное задание держит ресурсы
    минутами, и отменять его нужно на самом деле, а не только в интерфейсе."""
    if not server.healthy():
        info = server.start()
        if not info.get("ok"):
            logger.warning("LLM: сервер недоступен (%s)", info.get("reason"))
            return []

    all_hints: list = []

    def emit(block_key: str, hints: list) -> None:
        all_hints.extend(hints)
        if on_block:
            on_block(block_key, hints)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    # 0. Правдоподобие — отключено замером (fields.SANITY_ENABLED, там же цифры
    #    и разбор). Условие оставлено, чтобы включить обратно одной константой,
    #    когда будет что перепроверять.
    if SANITY_ENABLED:
        if cancelled():
            return all_hints
        emit(SANITY_BLOCK, _sanity_hints(regex_values))

    # 1. Суд — крошечное окно, отвечает первым, и блок первый на экране.
    if cancelled():
        return all_hints
    court = client.chat(build_df_mortgage_court_prompt(),
                        extract_court_window(raw_text), 120)
    emit("court", _flat_hints(block_by_key("court"), court or {}, regex_values))

    parties_window = extract_parties_window(raw_text)

    # 2. Представитель истца — отдельным вызовом, см. _fetch_representative.
    if cancelled():
        return all_hints
    rep_hints = []
    rep_name = _fetch_representative(parties_window)
    if rep_name:
        rep_hints = _flat_hints(block_by_key("representative"),
                                {"plaintiff": rep_name}, regex_values)
    emit("representative", rep_hints)

    # 3. Ответчики и третьи лица — общий вызов по шапке. Ни суда (он уже
    #    получен отдельным вызовом), ни финансов: финансовые поля на форме не
    #    показываются вовсе, подсказке негде появиться, а фрагмент текста с
    #    суммами кредита в это окно даже не попадает — просить их значило бы
    #    оплачивать выдумку модели выходными токенами.
    if cancelled():
        return all_hints
    parsed = client.chat(build_df_mortgage_prompt(with_representatives=False,
                                                  with_court=False,
                                                  with_financial=False),
                         parties_window, 1000) or {}
    check_leak(parsed, DF_MORTGAGE_LEAK_MARKERS)
    parsed = sanitize_mortgage(parsed)
    emit("debtors", _array_hints(block_by_key("debtors"),
                                 parsed.get("debtors") or [], regex_values))
    emit("thirdParties", _array_hints(block_by_key("thirdParties"),
                                      parsed.get("thirdParties") or [], regex_values))

    # 4. Предмет ипотеки — данные живут в двух далёких местах документа (блок
    #    залога и блок оценки), поэтому два якорных вызова и слияние.
    if cancelled():
        return all_hints
    emit("properties", _array_hints(block_by_key("properties"),
                                    _fetch_properties(raw_text), regex_values))

    _ = PROGRESS_KEYS  # порядок задан там, здесь он воспроизведён явно
    return all_hints
