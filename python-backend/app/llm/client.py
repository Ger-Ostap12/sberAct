# -*- coding: utf-8 -*-
"""Разговор с llama-server по локальному HTTP.

Заменяет прямой вызов llama-cpp-python. Транспорт — единственное, что
поменялось: окна, промпты, разбор ответа и сравнение остались теми же
функциями, что и раньше, поэтому цифры качества сравнимы с прежними прогонами.

Кеш префикса здесь НЕ нужен: llama-server держит его сам по слотам. Наша
самодельная версия складывала состояния файлами по 250 МБ и требовала уборки
за собой — всё это ушло вместе с переездом.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from . import server

logger = logging.getLogger(__name__)

# Сколько ждать ответа. Самый долгий вызов (ответчики) укладывается в ~30с на
# видеоядре и ~60с на процессоре; берём с большим запасом, чтобы на слабой
# машине не рвать работу на середине.
TIMEOUT_SEC = 600


def _messages(cfg: dict, user_text: str) -> list:
    msgs = [{"role": "system", "content": cfg["system"]}]
    for u, a in cfg.get("fewshot", []):
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": "Текст:\n«%s»" % user_text})
    return msgs


def chat(cfg: dict, user_text: str, max_tokens: int, expect: str = "object"):
    """Один вызов модели. Ошибку НЕ поднимаем: слой теневой и не имеет права
    ломать работу пользователя — максимум промолчать."""
    from .parsing import extract_json, extract_json_array

    body = json.dumps({
        "messages": _messages(cfg, user_text),
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        server.base_url() + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as r:
            out = json.loads(r.read().decode("utf-8"))
        raw = (out["choices"][0]["message"]["content"] or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM: вызов не удался: %s", exc)
        return None
    return extract_json_array(raw) if expect == "array" else extract_json(raw)
