# -*- coding: utf-8 -*-
"""Жизненный цикл llama-server — локального процесса, который считает модель.

Почему отдельный процесс, а не llama-cpp-python в нашем: официальные сборки
llama.cpp несут Vulkan-бэкенд и CPU-варианты под конкретные архитектуры, а
питоновская обвязка — одну универсальную сборку под любой x86. Замер на
Ryzen 7 8845HS / Radeon 780M:

    чтение промпта   75 -> 580 токенов/с   (видеоядро против нашей сборки)
    генерация        12 -> 24 токена/с
    на реальных промптах: ~92с -> 66с на документ, при прогретом кеше 54с

Плюс процессор освобождается: при -ngl 99 все слои считает видеоядро.

Сервер слушает ТОЛЬКО 127.0.0.1 и наружу не ходит — это разговор двух
процессов внутри машины, интернет не нужен ни на секунду. Проверено:
единственный слушающий сокет 127.0.0.1, исходящих соединений нет.

Владелец жизненного цикла — бэкенд, как и у конвертера (форма converter_start
в main.py повторена намеренно). Раньше инференс жил в конвертере, и ради
подсказок к обычному DOCX поднимался docling на 3.5 ГБ, которому там нечего
было делать.
"""
from __future__ import annotations

import glob
import logging
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
import urllib.request

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir, os.pardir))
_LLAMA_DIR = os.path.join(_ROOT, "converter", "llama")
_MODEL = os.path.join(_ROOT, "converter", "models", "gemma-3-4b-it-Q4_K_M.gguf")

HOST = "127.0.0.1"
PORT = int(os.environ.get("SBERACT_LLM_PORT", "18080"))
N_CTX = int(os.environ.get("SBERACT_LLM_CTX", "4096"))

# Сколько слоёв отдать видеоядру. 99 = все. При неудачном старте пробуем 0 —
# на слабых видеоядрах памяти может не хватить, и упереться в это должен
# параметр, а не пользователь.
NGL = os.environ.get("SBERACT_LLM_NGL", "99")

_process = None
_lock = threading.Lock()
_job = None  # дескриптор job-объекта Windows, см. _bind_to_parent_life


def _bind_to_parent_life(proc) -> None:
    """Ребёнок должен умирать вместе с бэкендом ЛЮБЫМ способом, а не только
    при вежливом завершении.

    Обработчик shutdown у FastAPI не отрабатывает, если процесс убили жёстко, —
    проверено: сервер пережил Stop-Process и остался держать 2.5 ГБ и порт.
    Полагаться на вежливое завершение нельзя: приложение может упасть, а
    Electron — прибить бэкенд без церемоний.

    Windows: job-объект с KILL_ON_JOB_CLOSE — когда наш процесс исчезает,
    закрывается последний дескриптор задания, и система гасит всех, кто в нём.
    Linux: PR_SET_PDEATHSIG, тот же смысл ядерными средствами.
    Обе ветки необязательные: не вышло — просто останется прежний риск.
    """
    global _job
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if _job is None:
            class _BASIC(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _IO(ctypes.Structure):
                _fields_ = [("ReadOperationCount", ctypes.c_uint64),
                            ("WriteOperationCount", ctypes.c_uint64),
                            ("OtherOperationCount", ctypes.c_uint64),
                            ("ReadTransferCount", ctypes.c_uint64),
                            ("WriteTransferCount", ctypes.c_uint64),
                            ("OtherTransferCount", ctypes.c_uint64)]

            class _EXT(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", _BASIC),
                            ("IoInfo", _IO),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]

            k32.CreateJobObjectW.restype = wintypes.HANDLE
            handle = k32.CreateJobObjectW(None, None)
            if not handle:
                return
            info = _EXT()
            info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(
                    wintypes.HANDLE(handle), 9,  # ExtendedLimitInformation
                    ctypes.byref(info), ctypes.sizeof(info)):
                k32.CloseHandle(wintypes.HANDLE(handle))
                return
            _job = handle

        k32.OpenProcess.restype = wintypes.HANDLE
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        hproc = k32.OpenProcess(0x0100 | 0x0001, False, proc.pid)
        if not hproc:
            return
        k32.AssignProcessToJobObject(wintypes.HANDLE(_job), wintypes.HANDLE(hproc))
        k32.CloseHandle(wintypes.HANDLE(hproc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM: не удалось привязать сервер к жизни бэкенда: %s", exc)


def _pdeathsig():
    """Linux: попросить ядро прислать ребёнку SIGTERM, когда умрёт родитель."""
    try:
        import ctypes
        import signal

        ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def _binary():
    sub = "win" if platform.system() == "Windows" else "linux"
    name = "llama-server.exe" if sub == "win" else "llama-server"
    path = os.path.join(_LLAMA_DIR, sub, name)
    return path if os.path.isfile(path) else None


def _resolve_model():
    """Путь к .gguf. Модель режут на куски `.partNNN` ради лимита GitHub —
    если собранного файла нет, склеиваем один раз."""
    if os.path.isfile(_MODEL):
        return _MODEL
    parts = sorted(glob.glob(_MODEL + ".part*"))
    if not parts:
        return None
    try:
        logger.info("LLM: собираю модель из %d кусков", len(parts))
        with open(_MODEL, "wb") as out:
            for part in parts:
                with open(part, "rb") as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)
        return _MODEL
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM: не удалось собрать модель: %s", exc)
        try:
            if os.path.isfile(_MODEL):
                os.remove(_MODEL)  # половинчатый файл хуже отсутствующего
        except OSError:
            pass
        return None


def available() -> bool:
    """Есть ли чем считать. Отсутствие модели или бинарника — штатная
    ситуация: слой опционален, и правильная реакция на неё молчание."""
    return _binary() is not None and _resolve_model() is not None


def base_url() -> str:
    return "http://%s:%d" % (HOST, PORT)


def healthy(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(base_url() + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _port_busy() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST, PORT)) == 0


def _threads() -> int:
    """Одно ядро всегда оставляем системе: потоки llama.cpp работают на
    busy-wait — жгут ядро, а не спят в ожидании."""
    try:
        logical = os.cpu_count() or 4
    except Exception:
        return 4
    physical = logical // 2 if (logical >= 4 and logical % 2 == 0) else logical
    return max(1, min(16, (physical - 1) or 1))


def _spawn(model: str, ngl: str):
    cmd = [
        _binary(), "-m", model,
        "--host", HOST, "--port", str(PORT),
        "-c", str(N_CTX), "-ngl", ngl, "-t", str(_threads()),
        "--no-webui",
    ]
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if platform.system() == "Windows":
        # Без консольного окна поверх интерфейса юриста.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["preexec_fn"] = _pdeathsig
    logger.info("LLM: запускаю llama-server (-ngl %s, потоков %d)", ngl, _threads())
    proc = subprocess.Popen(cmd, **kwargs)
    _bind_to_parent_life(proc)
    return proc


def _wait_healthy(proc, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if proc.poll() is not None:
            return False  # процесс умер, ждать больше нечего
        if healthy():
            return True
        time.sleep(0.5)
    return False


def start(wait_seconds: float = 120.0) -> dict:
    """Поднять сервер, если он ещё не отвечает. Уже работающий (в том числе
    запущенный вручную) переиспользуется — как и у конвертера."""
    global _process

    if healthy():
        return {"ok": True, "external": _process is None}
    if not available():
        return {"ok": False, "reason": "нет модели или бинарника llama-server"}

    with _lock:
        # Повторная проверка ПОД локом обязательна: пока ждали очередь,
        # конкурент мог уже поднять сервер, и без неё мы наплодим процессов,
        # дерущихся за один порт.
        if healthy():
            return {"ok": True, "external": _process is None}
        if _port_busy():
            return {"ok": False, "reason": "порт %d занят чужим процессом" % PORT}

        model = _resolve_model()
        if model is None:
            return {"ok": False, "reason": "модель недоступна"}

        for ngl in ([NGL, "0"] if NGL != "0" else ["0"]):
            proc = _spawn(model, ngl)
            if _wait_healthy(proc, wait_seconds):
                _process = proc
                logger.info("LLM: сервер готов (-ngl %s)", ngl)
                return {"ok": True, "external": False, "ngl": ngl}
            # Не поднялся: чаще всего видеоядру не хватило памяти под слои.
            # Гасим и пробуем на процессоре, вместо того чтобы отдать отказ.
            logger.warning("LLM: старт с -ngl %s не удался, пробую дальше", ngl)
            try:
                proc.kill()
                proc.wait(timeout=10)
            except Exception:
                pass
        return {"ok": False, "reason": "сервер не поднялся"}


def stop() -> None:
    global _process
    with _lock:
        proc, _process = _process, None
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    logger.info("LLM: сервер остановлен")


def status() -> dict:
    return {
        "available": available(),
        "healthy": healthy(),
        "owned": _process is not None,
        "url": base_url(),
    }
