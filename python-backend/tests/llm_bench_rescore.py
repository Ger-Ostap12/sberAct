# -*- coding: utf-8 -*-
"""Пересчёт метрики уже готового прогона (без повторного вызова LLM) через
честное сравнение — resolve_sro-канонизация для sro, нормализация
организационно-правовой формы для name (см. _fuzzy_match/_fuzzy_match_sro в
llm_bench_run_fields.py). Нужен, чтобы получить честную цифру df_v3 ДО
прогона df_v4 — иначе непонятно, что дал промпт-фикс, а что дала починка
метрики.

Запуск (converter/.venv, там нет зависимости от llama_cpp для этого
скрипта, но re-use импортов из run_fields.py тянет sro_registry из
python-backend/app — пути там уже настроены):
  cd converter && .venv/Scripts/python.exe ../python-backend/tests/llm_bench_rescore.py \
      --in ../python-backend/tests/llm_bench_results_gemma_df_v3_full58.json
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_THIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _THIS)

from llm_bench_run_fields import _fuzzy_match, _fuzzy_match_sro  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    args = ap.parse_args()

    with open(args.inp, "r", encoding="utf-8") as f:
        data = json.load(f)
    results = data["results"]

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

    old_summary = data["summary"]
    print(f"Файл: {args.inp}")
    print(f"Было (сырое substring-сравнение): "
          f"{old_summary['overall_match']}/{old_summary['overall_total']} = "
          f"{old_summary['overall_rate']:.0%}")
    print(f"Стало (канонизация sro + нормализация орг.-правовой формы): "
          f"{overall_match}/{overall_total} = "
          f"{(overall_match/overall_total if overall_total else 0):.0%}\n")
    for key in sorted(field_total):
        total = field_total[key]
        old_match = old_summary["field_match"].get(key, 0)
        new_match = field_match.get(key, 0)
        marker = "  <-- изменилось" if old_match != new_match else ""
        print(f"  {key:24} было {old_match}/{total} = {old_match/total:.0%}  "
              f"-> стало {new_match}/{total} = {new_match/total:.0%}{marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
