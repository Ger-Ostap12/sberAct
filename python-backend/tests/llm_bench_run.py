# -*- coding: utf-8 -*-
"""Бенчмарк LLM-извлечения полей (Андрей): универсальный прогон.

Читает `llm_bench_dump.json` (фаза 1, python-backend/venv), прогоняет
указанную модель+версию промпта, меряет время и сверяет с regex. Каждый
прогон пишет отдельный `llm_bench_results_<label>.json`, чтобы сравнивать
модели/итерации между собой в финальном отчёте.

ВАЖНО: запускать через converter/.venv (там llama-cpp-python).

Запуск:
  cd converter && .venv/Scripts/python.exe ../python-backend/tests/llm_bench_run.py \
      --model ../converter/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
      --prompt v2 --label qwen1.5b_v2 --n-ctx 4096
"""
import argparse
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_THIS = os.path.dirname(os.path.abspath(__file__))
DUMP_PATH = os.path.join(_THIS, "llm_bench_dump.json")

sys.path.insert(0, _THIS)
from llm_bench_prompts import PROMPTS  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join(_THIS, "..", "app")))
from requisites_validation import is_valid_inn, is_valid_ogrn_any  # noqa: E402

_DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def _sanitize(parsed: dict) -> dict:
    """Код-сайд предохранитель: не верим модели на слово даже после промпта —
    отбрасываем ИНН/ОГРН без верной контрольной суммы, даты не по формату.
    Тот же принцип, что requisites_validation в проде (regex ловит жадно,
    контрольная сумма отсеивает мусор)."""
    if not isinstance(parsed, dict):
        return parsed
    for role in ("debtor", "creditor"):
        r = parsed.get(role)
        if not isinstance(r, dict):
            continue
        if "inn" in r and r["inn"] and not is_valid_inn(r["inn"]):
            r["inn"] = ""
        if "ogrn" in r and r["ogrn"] and not is_valid_ogrn_any(r["ogrn"]):
            r["ogrn"] = ""
        if "registrationDate" in r and r["registrationDate"] and not _DATE_RE.match(r["registrationDate"].strip()):
            r["registrationDate"] = ""
    return parsed


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


_NORM_RE = re.compile(r"[\s«»\"'.,]+")


def _norm(s: str) -> str:
    return _NORM_RE.sub("", (s or "").lower())


def _fuzzy_match(regex_val: str, llm_val: str) -> bool:
    a, b = _norm(regex_val), _norm(llm_val)
    if not a or not b:
        return False
    return a in b or b in a


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", required=True, choices=list(PROMPTS))
    ap.add_argument("--label", required=True)
    ap.add_argument("--n-ctx", type=int, default=4096)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--dump", default=DUMP_PATH)
    ap.add_argument("--n-threads", type=int, default=8)
    args = ap.parse_args()

    if not os.path.isfile(args.dump):
        print(f"Нет дампа {args.dump} — сначала запусти фазу 1 (python-backend/venv).")
        return 1

    from llama_cpp import Llama

    prompt_cfg = PROMPTS[args.prompt]
    system = prompt_cfg["system"]
    use_grammar = prompt_cfg["grammar"]
    fewshot_user = prompt_cfg["fewshot_user"]
    fewshot_assistant = prompt_cfg["fewshot_assistant"]

    print(f"Модель: {args.model}")
    print(f"Промпт: {args.prompt}  grammar={use_grammar}")
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
        regex_roles = doc["regex_roles"]

        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": fewshot_user},
            {"role": "assistant", "content": fewshot_assistant},
            {"role": "user", "content": f"Текст:\n«{window}»"},
        ]

        t0 = time.perf_counter()
        try:
            out = llm.create_chat_completion(messages=msgs, **kwargs)
            raw = out["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            raw = ""
            print(f"[ОШИБКА генерации] {rel}: {exc}")
        elapsed = time.perf_counter() - t0

        parsed = _sanitize(_extract_json(raw))
        results.append({
            "file": rel, "elapsed_sec": elapsed, "raw": raw,
            "parsed": parsed, "regex_roles": regex_roles,
        })
        status = "JSON ok" if parsed is not None else "JSON НЕВАЛИДЕН"
        print(f"[{elapsed:5.1f} с] {status:16} {rel}")

    times = [r["elapsed_sec"] for r in results]
    valid_json = sum(1 for r in results if r["parsed"] is not None)

    field_total, field_match = {}, {}
    for r in results:
        parsed = r["parsed"] or {}
        for role, fields in r["regex_roles"].items():
            llm_role = parsed.get(role) or {}
            if not isinstance(llm_role, dict):
                llm_role = {}
            for f, regex_val in fields.items():
                if not regex_val:
                    continue
                key = f"{role}.{f}"
                field_total[key] = field_total.get(key, 0) + 1
                fl = f.lower()
                if fl.endswith("ogrn"):
                    sub = "ogrn"
                elif fl.endswith("inn") or f == "inn":
                    sub = "inn"
                elif "address" in fl:
                    sub = "address"
                elif f == "registrationDate":
                    sub = "registrationDate"
                else:
                    sub = "name"
                llm_val = llm_role.get(sub, "")
                if _fuzzy_match(regex_val, llm_val):
                    field_match[key] = field_match.get(key, 0) + 1

    overall_total = sum(field_total.values())
    overall_match = sum(field_match.values())

    print("\n" + "=" * 78)
    print(f"ИТОГ [{args.label}]")
    print("=" * 78)
    print(f"Модель: {os.path.basename(args.model)}  промпт={args.prompt}  grammar={use_grammar}")
    print(f"Загрузка модели: {load_sec:.1f} с")
    print(f"Файлов: {len(results)}  Время/файл: мин={min(times):.1f}с "
          f"макс={max(times):.1f}с среднее={sum(times)/len(times):.1f}с")
    print(f"Валидный JSON: {valid_json}/{len(results)} = {valid_json/len(results):.0%}")
    print(f"Совпадение полей (общее): {overall_match}/{overall_total} = "
          f"{(overall_match/overall_total if overall_total else 0):.0%}")
    for key in sorted(field_total):
        total = field_total[key]
        match = field_match.get(key, 0)
        print(f"  {key:24} {match}/{total} = {match/total:.0%}")

    summary = {
        "label": args.label, "model": os.path.basename(args.model),
        "prompt": args.prompt, "grammar": use_grammar,
        "load_sec": load_sec, "n_files": len(results),
        "time_min": min(times), "time_max": max(times),
        "time_avg": sum(times) / len(times),
        "valid_json": valid_json, "valid_json_rate": valid_json / len(results),
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
