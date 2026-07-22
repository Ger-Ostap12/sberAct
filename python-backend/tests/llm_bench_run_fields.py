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
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_THIS = os.path.dirname(os.path.abspath(__file__))
DUMP_PATH = os.path.join(_THIS, "llm_bench_dump_debtorfields.json")

sys.path.insert(0, _THIS)
from llm_bench_prompts import (  # noqa: E402
    DF_PROMPTS, DF_V4_LEAK_MARKERS, build_df_v7_prompt, build_df_v8_prompt,
)

sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
from requisites_validation import is_valid_inn, is_valid_ogrn_any  # noqa: E402
from sro_registry import resolve_sro  # noqa: E402

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
_VALID_TYPES = {"individual", "legal", "ip", "kfh"}


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    blob = m.group(0)
    try:
        return json.loads(blob)
    except Exception:
        pass
    return _repair_json(blob)


# Реальная причина 3/58 "невалидных JSON" на df_v3 (full58, см. handoff §R.6)
# оказалась НЕ обрезкой по max_tokens (ответы полные, со закрывающей
# скобкой), а (а) вложенными неэкранированными кавычками внутри значения
# "sro" — модель игнорировала текстовый запрет, когда в самом документе СРО
# названа в несколько уровней кавычек («Союз «СРО «Гильдия...»»»); и (б)
# невалидным escape-символом (`\я`, похоже на OCR-артефакт «а/я» → «а\я»),
# который json.loads не может проглотить. Обе причины чинятся построчным
# repair-проходом: для строк вида `"key": "...значение..."` берём ВЕСЬ текст
# между первой и последней кавычками на строке как значение и экранируем
# то, что внутри.
_REPAIR_LINE_RE = re.compile(r'^(\s*"[a-zA-Z]+"\s*:\s*)"(.*)"(\s*,?\s*)$')


def _repair_json(blob: str) -> dict | None:
    fixed_lines = []
    for line in blob.splitlines():
        m = _REPAIR_LINE_RE.match(line)
        if m:
            prefix, value, suffix = m.groups()
            value = value.replace("\\", "\\\\").replace('"', '\\"')
            line = f'{prefix}"{value}"{suffix}'
        fixed_lines.append(line)
    try:
        return json.loads("\n".join(fixed_lines))
    except Exception:
        return None


_NORM_RE = re.compile(r"[\s«»\"'.,]+")
# Родовые слова организационно-правовой формы — регекс-эталон и LLM-ответ
# часто расходятся ТОЛЬКО форматом (ООО vs "Общество с ограниченной
# ответственностью"), это не ошибка модели. Убираем их с обеих сторон перед
# сравнением, аналогично _GENERIC в sro_registry.py.
_LEGAL_FORM_WORDS = {
    "ооо", "зао", "оао", "пао", "нао", "ао", "ип", "кфх",
    "общество", "ограниченной", "ответственностью", "акционерное",
    "акционерного", "публичное", "непубличное", "закрытое", "открытое",
    "товарищество", "индивидуальный", "предприниматель", "крестьянское",
    "фермерское", "хозяйство",
}


def _norm(s: str) -> str:
    return _NORM_RE.sub("", (s or "").lower())


def _core_name(s: str) -> str:
    words = re.sub(r"[«»\"'.,]+", " ", (s or "").lower()).split()
    return " ".join(w for w in words if w not in _LEGAL_FORM_WORDS)


def _fuzzy_match(regex_val: str, llm_val: str) -> bool:
    a, b = _norm(regex_val), _norm(llm_val)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ca, cb = _norm(_core_name(regex_val)), _norm(_core_name(llm_val))
    if not ca or not cb:
        return False
    return ca in cb or cb in ca


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


def _check_leak(parsed: dict) -> int:
    """Обнуляет поля, дословно совпавшие с few-shot маркерами (см.
    DF_V4_LEAK_MARKERS) — сигнал, что модель скопировала пример вместо
    реального текста. Возвращает число обнуленных полей."""
    if not isinstance(parsed, dict):
        return 0
    leaked = 0
    for path, markers in DF_V4_LEAK_MARKERS.items():
        role, field = path.split(".")
        section = parsed.get(role)
        if isinstance(section, dict) and section.get(field) in markers:
            section[field] = ""
            leaked += 1
    return leaked


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", required=True, choices=list(DF_PROMPTS) + ["df_v7", "df_v8"])
    ap.add_argument("--label", required=True)
    ap.add_argument("--n-ctx", type=int, default=4096)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--n-threads", type=int, default=8)
    ap.add_argument("--dump", default=DUMP_PATH)
    args = ap.parse_args()

    if not os.path.isfile(args.dump):
        print(f"Нет дампа {args.dump} — сначала запусти llm_bench_phase1_dump.py.")
        return 1

    from llama_cpp import Llama

    dynamic_schema = args.prompt in ("df_v7", "df_v8")
    if not dynamic_schema:
        prompt_cfg = DF_PROMPTS[args.prompt]
        system = prompt_cfg["system"]
        use_grammar = prompt_cfg["grammar"]
        fewshot = prompt_cfg["fewshot"]
    else:
        use_grammar = False  # df_v7/df_v8 не используют grammar-режим, как и всё после df_v1

    print(f"Модель: {args.model}")
    print(f"Промпт: {args.prompt}  grammar={use_grammar}  n_threads={args.n_threads}")
    t_load0 = time.perf_counter()
    llm = Llama(model_path=args.model, n_ctx=args.n_ctx,
                n_threads=args.n_threads, verbose=False)
    load_sec = time.perf_counter() - t_load0
    print(f"Модель загружена за {load_sec:.1f} с (разово на процесс)\n")

    with open(args.dump, "r", encoding="utf-8") as f:
        docs = json.load(f)

    kwargs = dict(temperature=0.0, max_tokens=args.max_tokens)
    if use_grammar:
        kwargs["response_format"] = {"type": "json_object"}

    results = []
    for doc in docs:
        rel = doc["file"]
        window = doc["header_window"]
        prayer = doc.get("prayer_window", "")
        if prayer:
            window = window + "\n[...]\n" + prayer
        entity_type_true = doc.get("entity_type", "")
        regex_roles = doc["regex_roles"]
        need_fio = doc.get("need_manager_fio", True)
        need_sro = doc.get("need_manager_sro", True)

        if args.prompt == "df_v8":
            regex_entity_type = doc.get("entity_type", "")
            prompt_cfg = build_df_v8_prompt(need_fio, need_sro, regex_entity_type)
            system = prompt_cfg["system"]
            fewshot = prompt_cfg["fewshot"]
        elif dynamic_schema:
            prompt_cfg = build_df_v7_prompt(need_fio, need_sro)
            system = prompt_cfg["system"]
            fewshot = prompt_cfg["fewshot"]

        msgs = [{"role": "system", "content": system}]
        for u, a in fewshot:
            msgs.append({"role": "user", "content": u})
            msgs.append({"role": "assistant", "content": a})
        msgs.append({"role": "user", "content": f"Текст:\n«{window}»"})

        t0 = time.perf_counter()
        try:
            out = llm.create_chat_completion(messages=msgs, **kwargs)
            raw = out["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            raw = ""
            print(f"[ОШИБКА генерации] {rel}: {exc}")
        elapsed = time.perf_counter() - t0

        parsed = _extract_json(raw)
        leaked = _check_leak(parsed) if isinstance(parsed, dict) else 0
        parsed = _sanitize(parsed)
        results.append({
            "file": rel, "elapsed_sec": elapsed, "raw": raw,
            "parsed": parsed, "entity_type_true": entity_type_true,
            "regex_roles": regex_roles, "leaked_fields": leaked,
            "need_manager_fio": need_fio, "need_manager_sro": need_sro,
        })
        status = "JSON ok" if parsed is not None else "JSON НЕВАЛИДЕН"
        et_llm = (parsed or {}).get("entityType", "?") if parsed else "?"
        et_mark = "OK" if et_llm == entity_type_true else "MISMATCH"
        print(f"[{elapsed:5.1f} с] {status:16} entityType={et_llm:10} "
              f"({et_mark:8}) {rel}")

    times = [r["elapsed_sec"] for r in results]
    valid_json = sum(1 for r in results if r["parsed"] is not None)
    entity_correct = sum(
        1 for r in results
        if r["parsed"] and r["parsed"].get("entityType") == r["entity_type_true"]
    )

    # Поля manager, у которых есть предпосылка "нужно ли вообще спрашивать
    # ЭТО поле у ЭТОГО документа" (df_v7, см. handoff §R.10) — не оцениваем
    # то, что сознательно не запрашивали, иначе цифра нечестно занижена
    # промахом по полю, которого в схеме для этого документа не было.
    _GATED_BY_FIO = {"managerName", "managerAddress"}
    _GATED_BY_SRO = {"sroName"}

    field_total, field_match = {}, {}
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
                sub = {"debtorName": "name", "applicantAddress": "address",
                       "inn": "inn", "ogrn": "ogrn", "birthDate": "birthDate",
                       "birthPlace": "birthPlace", "managerName": "name",
                       "managerAddress": "address", "sroName": "sro"}.get(f, f)
                llm_val = llm_role.get(sub, "")
                matcher = _fuzzy_match_sro if sub == "sro" else _fuzzy_match
                if matcher(regex_val, llm_val):
                    field_match[key] = field_match.get(key, 0) + 1

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
    out_path = os.path.join(_THIS, f"llm_bench_results_{args.label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=1)
    print(f"\n-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
