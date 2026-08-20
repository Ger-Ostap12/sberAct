# -*- coding: utf-8 -*-
"""Пересчёт метрики готового прогона БЕЗ повторного вызова LLM и диф двух
прогонов по полям. Два назначения:

1. Пересчёт под изменившуюся метрику (исходный сценарий: честное сравнение
   через resolve_sro-канонизацию и нормализацию орг.-правовой формы — нужно
   было отделить эффект промпт-фикса df_v4 от эффекта починки метрики).
2. Quality gate этапов оптимизации скорости: `--baseline` даёт пополевой диф
   нового прогона против эталонного одной командой. Без этого гейт —
   ручная арифметика по двум JSON, которая под давлением времени пропускается.

Скоринг НЕ дублируется здесь: score_bankruptcy/score_mortgage импортируются
из llm_bench_run_fields.py. Раньше банкротный скоринг был скопирован в этот
файл руками и отстал — в копии не было гейтинга df_v7 по need_fio/need_sro.

Запуск (llama_cpp не нужен, но импорт тянет sro_registry из python-backend/app —
пути настроены внутри llm_bench_run_fields.py):
  venv/Scripts/python.exe tests/llm_bench_rescore.py \
      --in tests/llm_bench_results_stage1.json \
      --baseline tests/llm_bench_results_gemma_df_mortgage_v6.json --calls
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)

from llm_bench_run_fields import score_bankruptcy, score_mortgage  # noqa: E402


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _score(data: dict) -> tuple:
    """Ипотечная схема или банкротная — по промпту прогона. Дефолт банкротный:
    df_mortgage появился позже, все старые прогоны без этого ключа банкротные."""
    prompt = (data.get("summary") or {}).get("prompt", "")
    scorer = score_mortgage if prompt == "df_mortgage" else score_bankruptcy
    return scorer(data["results"])


def _print_calls(data: dict) -> None:
    """Таблица вызовов из инструментации (этап 1): токены и split
    prefill/decode по тегам. Старые прогоны ключа `calls` не имеют."""
    rows: dict = {}
    n_files = 0
    for r in data["results"]:
        calls = r.get("calls") or []
        if not calls:
            continue
        n_files += 1
        for c in calls:
            acc = rows.setdefault(c["tag"], {"n": 0, "pt": 0, "ct": 0, "pre": 0.0, "dec": 0.0})
            acc["n"] += 1
            acc["pt"] += c.get("prompt_tokens", 0)
            acc["ct"] += c.get("completion_tokens", 0)
            acc["pre"] += c.get("prefill_sec", 0.0)
            acc["dec"] += c.get("decode_sec", 0.0)
    if not rows:
        print("В прогоне нет метрик вызовов (прогон сделан до этапа 1).\n")
        return
    print(f"{'вызов':16} {'n':>3} {'вх.ток':>8} {'вых.ток':>8} "
          f"{'prefill,с':>10} {'decode,с':>9}   (суммы на файл)")
    tot = {"pt": 0, "ct": 0, "pre": 0.0, "dec": 0.0}
    for tag in sorted(rows):
        a = rows[tag]
        for k in tot:
            tot[k] += a[k]
        print(f"  {tag:14} {a['n']:>3} {a['pt']/n_files:8.0f} {a['ct']/n_files:8.0f} "
              f"{a['pre']/n_files:10.1f} {a['dec']/n_files:9.1f}")
    print(f"  {'ИТОГО':14} {'':>3} {tot['pt']/n_files:8.0f} {tot['ct']/n_files:8.0f} "
          f"{tot['pre']/n_files:10.1f} {tot['dec']/n_files:9.1f}")
    per_tok = tot["dec"] / tot["ct"] if tot["ct"] else 0
    print(f"  decode: {1/per_tok if per_tok else 0:.1f} ток/с\n")


def _print_config(tag: str, data: dict) -> None:
    s = data.get("summary") or {}
    cfg = " ".join(
        f"{k}={s[k]}" for k in
        ("n_ctx", "n_batch", "n_threads", "max_tokens", "llama_cpp_version")
        if k in s
    )
    print(f"{tag}: {s.get('label', '?')}  {cfg or 'конфигурация не записана'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--baseline", help="прогон-эталон для пополевого дифа")
    ap.add_argument("--calls", action="store_true",
                    help="таблица токенов и prefill/decode по вызовам")
    args = ap.parse_args()

    data = _load(args.inp)
    field_total, field_match = _score(data)
    overall_total = sum(field_total.values())
    overall_match = sum(field_match.values())
    summary = data["summary"]

    print(f"Файл: {args.inp}")
    _print_config("прогон  ", data)

    if args.baseline:
        base = _load(args.baseline)
        base_total, base_match = _score(base)
        _print_config("эталон  ", base)
        print()
        b_all = sum(base_total.values())
        b_hit = sum(base_match.values())
        print(f"Качество: эталон {b_hit}/{b_all} = {(b_hit/b_all if b_all else 0):.1%}"
              f"  ->  прогон {overall_match}/{overall_total} = "
              f"{(overall_match/overall_total if overall_total else 0):.1%}")
        b_t = base["summary"].get("time_avg")
        n_t = summary.get("time_avg")
        if b_t and n_t:
            print(f"Время/файл: эталон {b_t:.1f}с  ->  прогон {n_t:.1f}с "
                  f"({(n_t - b_t) / b_t:+.0%})")
        print(f"Валидный JSON: эталон {base['summary'].get('valid_json')}"
              f"  ->  прогон {summary.get('valid_json')}\n")
        regressed = []
        for key in sorted(set(field_total) | set(base_total)):
            total = field_total.get(key, base_total.get(key, 0))
            b = base_match.get(key, 0)
            n = field_match.get(key, 0)
            if b == n:
                mark = ""
            else:
                mark = "  <-- ЛУЧШЕ" if n > b else "  <-- ХУЖЕ"
            if n < b:
                regressed.append((key, b - n))
            print(f"  {key:26} эталон {b}/{total} -> прогон {n}/{total}{mark}")
        print()
        if regressed:
            worst = max(d for _, d in regressed)
            print("ПРОСЕЛИ: " + ", ".join(f"{k} (-{d})" for k, d in regressed))
            print(f"Максимальная просадка по одному полю: {worst}")
        else:
            print("Просевших полей нет.")
    else:
        # Режим 1: пересчёт под изменившуюся метрику — сравниваем с цифрой,
        # записанной в summary этого же прогона.
        print(f"Было (метрика прогона):  {summary['overall_match']}/"
              f"{summary['overall_total']} = {summary['overall_rate']:.1%}")
        print(f"Стало (текущая метрика): {overall_match}/{overall_total} = "
              f"{(overall_match/overall_total if overall_total else 0):.1%}\n")
        for key in sorted(field_total):
            total = field_total[key]
            old_match = summary["field_match"].get(key, 0)
            new_match = field_match.get(key, 0)
            marker = "  <-- изменилось" if old_match != new_match else ""
            print(f"  {key:26} было {old_match}/{total} -> стало "
                  f"{new_match}/{total}{marker}")

    if args.calls:
        print()
        _print_calls(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
