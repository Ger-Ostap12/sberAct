# -*- coding: utf-8 -*-
"""HTTP-слой теневых LLM-подсказок по полям ипотечного иска.

Форма задачи намеренно повторяет /convert: POST создаёт задание и сразу
возвращает job_id, GET отдаёт состояние, DELETE отменяет. Фронт уже умеет
опрашивать задания именно так, отдельный протокол только плодил бы сущности.

Отличие одно и важное: `hints` РАСТЁТ по мере готовности блоков. Смысл всей
затеи — не заставить юриста ждать полторы минуты, а отдавать проверенное по
мере того, как он читает форму сверху вниз.

Раньше эти ручки жили в конвертере, а бэкенд их проксировал: инференс требовал
llama-cpp-python и файла модели, которые лежали там. С переездом на
llama-server посредник стал не нужен — и вместе с ним ушёл подъём docling на
3.5 ГБ ради подсказок к обычному DOCX.
"""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from llm import hints as llm_hints
from llm import server as llm_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])

# job_id → {status, blocks_done, blocks_total, hints, error, cancel}
#   status: queued | running | done | error | cancelled
_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()

# Один воркер. Параллелить нечего: llama-server считает по одному запросу, а
# второй прогон только отнимал бы у первого то же самое железо.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="llm-hints")

# Задач держим немного: каждая тащит за собой текст документа целиком.
_MAX_JOBS = 8

# Прогрев: idle -> running -> done/failed. Идёт через ТОТ ЖЕ единственный
# воркер, что и подсказки. Побочный эффект полезен: если юрист успел дойти до
# формы раньше, чем закончился прогрев, его задача просто встанет в очередь
# следом, а не подерётся за модель.
_WARMUP = {"state": "idle", "detail": None}


class HintsRequest(BaseModel):
    """`regex` — ПЛОСКАЯ карта «ключ поля формы → текущее значение»
    (`courtName`, `debtors[0].inn`, `mortgageProperties[1].cadastralNumber`).
    Так вся раскладка «схема LLM → форма» остаётся в одном месте на бэкенде, а
    фронт просто отдаёт то, что показывает пользователю."""

    rawText: str
    regex: dict = {}
    mortgageKind: str | None = None


def shutdown_executor() -> None:
    """Погасить пул при остановке приложения.

    Потоки пула не daemon, и `concurrent.futures` join'ит их на выходе
    интерпретатора: незавершённая подсказка задерживала выход (замер: 3226 мс
    на трёхсекундной задаче, а реальная подсказка идёт около минуты). Electron
    ждёт три секунды и убивает бэкенд жёстко — то есть мимо хука, который
    гасит llama-server и конвертер, и те остаются сиротами с гигабайтами.
    """
    _EXECUTOR.shutdown(wait=False, cancel_futures=True)


def _set(job_id: str, **changes) -> None:
    with _JOBS_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(changes)


def _prune() -> None:
    """Выбрасываем самые старые завершённые задачи. Держать их вечно нельзя —
    в каждой лежит полный текст документа.

    Бюджет считаем по ЗАВЕРШЁННЫМ, а не по всем: активные задачи удалить всё
    равно нельзя, и раньше они съедали лимит, после чего чистка переставала
    работать вовсе. Проверено симуляцией: 9 задач в словаре, из них 0
    завершённых — удалялось 0, и словарь рос дальше.
    """
    with _JOBS_LOCK:
        finished = [k for k, v in _JOBS.items()
                    if v["status"] in ("done", "error", "cancelled")]
        # Свежие завершённые ещё нужны фронту: он дочитывает подсказки уже
        # после того, как задача закрылась. Оставляем последние _MAX_JOBS.
        for k in finished[:-_MAX_JOBS] if len(finished) > _MAX_JOBS else []:
            _JOBS.pop(k, None)


def _run(job_id: str, payload: HintsRequest) -> None:
    from llm.fields import PROGRESS_KEYS

    _set(job_id, status="running", blocks_total=len(PROGRESS_KEYS))

    def should_cancel() -> bool:
        with _JOBS_LOCK:
            return bool(_JOBS.get(job_id, {}).get("cancel"))

    def on_block(block_key: str, block_hints: list) -> None:
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                return
            job["hints"].extend(block_hints)
            job["blocks_done"] = job.get("blocks_done", 0) + 1
            job["last_block"] = block_key

    try:
        llm_hints.run_hints(payload.rawText, payload.regex or {},
                            on_block=on_block, should_cancel=should_cancel,
                            mortgage_kind=payload.mortgageKind)
        _set(job_id, status="cancelled" if should_cancel() else "done")
    except Exception as exc:  # noqa: BLE001
        logger.exception("llm-hints: задача %s упала", job_id)
        _set(job_id, status="error", error=str(exc))


def _run_warmup() -> None:
    try:
        info = llm_hints.warmup()
        with _JOBS_LOCK:
            _WARMUP["state"] = "done" if info.get("ok") else "failed"
            _WARMUP["detail"] = info.get("reason")
    except Exception as exc:  # noqa: BLE001
        logger.exception("llm-warmup: прогрев упал")
        with _JOBS_LOCK:
            _WARMUP["state"] = "failed"
            _WARMUP["detail"] = str(exc)


@router.post("/warmup")
async def warmup():
    """Поднять llama-server заранее.

    Замер: первый документ после запуска платил ~80 секунд только за подъём
    весов модели с диска. Эту цену должен платить фон — пока юрист выбирает
    файл и категорию, — а не тот, кто ждёт подсказку.

    Отвечает сразу, работа идёт в фоне. Повторные вызовы бесплатны.
    """
    if not llm_server.available():
        # Не 500: отсутствие модели — штатная ситуация (слой опционален),
        # фронт на такой ответ просто не показывает подсказок.
        raise HTTPException(status_code=503, detail="LLM-слой недоступен")
    with _JOBS_LOCK:
        state = _WARMUP["state"]
        if state in ("running", "done"):
            return {"state": state}
        _WARMUP["state"] = "running"
    _EXECUTOR.submit(_run_warmup)
    return {"state": "running"}


@router.get("/warmup")
async def warmup_status():
    with _JOBS_LOCK:
        return {"state": _WARMUP["state"], "detail": _WARMUP["detail"],
                "server": llm_server.status()}


@router.post("/hints")
async def create_hints(payload: HintsRequest):
    if not (payload.rawText or "").strip():
        raise HTTPException(status_code=400, detail="Пустой текст документа")
    if not llm_server.available():
        raise HTTPException(status_code=503, detail="LLM-слой недоступен")

    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id, "status": "queued", "hints": [],
            "blocks_done": 0, "blocks_total": 0, "cancel": False,
            "error": None, "last_block": None,
        }
    _prune()
    _EXECUTOR.submit(_run, job_id, payload)
    return {"job_id": job_id}


@router.get("/hints/{job_id}")
async def hints_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        return {
            "job_id": job_id,
            "status": job["status"],
            "blocksDone": job.get("blocks_done", 0),
            "blocksTotal": job.get("blocks_total", 0),
            "lastBlock": job.get("last_block"),
            "hints": list(job["hints"]),
            "error": job.get("error"),
        }


@router.delete("/hints/{job_id}")
async def cancel_hints(job_id: str):
    """Отмена обязательна, а не «на всякий случай»: брошенная задача держит
    железо минутами, и юрист, уже ушедший к следующему документу, получил бы
    тормозящий интерфейс без всякой причины."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        job["cancel"] = True
        if job["status"] in ("queued",):
            job["status"] = "cancelled"
    return {"job_id": job_id, "cancelled": True}
