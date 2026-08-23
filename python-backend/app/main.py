from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import asyncio
import contextlib
import os
import sys
import threading
import time
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel
import json
import logging
from datetime import datetime

from document_analyzer import DocumentAnalyzer
from document_generator import DocumentGenerator
from template_manager import TemplateManager
from creditor_registry import list_banks
import paths as app_paths
from llm_api import router as llm_router

logger = logging.getLogger(__name__)

def _get_frontend_dir() -> Optional[Path]:
    """Путь к собранному React: рядом с exe (frontend/build) или в _internal."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates = [
            exe_dir / "frontend",
            exe_dir / "build",
            exe_dir / "_internal" / "frontend",
            exe_dir / "_internal" / "build",
        ]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            me = Path(meipass)
            candidates.extend([me / "frontend", me / "build"])
        for p in candidates:
            if p.exists() and (p / "index.html").exists():
                logger.info("Frontend found at %s", p)
                return p
        logger.warning("Frontend not found in exe bundle")
        return None
    project_root = Path(__file__).resolve().parents[2]
    build_path = project_root / "electron-app" / "build"
    if (build_path / "index.html").exists():
        return build_path
    return None

frontend_dir = _get_frontend_dir()

app = FastAPI(
    title="SberAct Document Generator API",
    description="API для анализа заявлений и генерации судебных актов",
    version="1.0.0"
)

def _mount_frontend_static(app: FastAPI, frontend_dir: Path) -> None:
    """
    Монтирует статику фронтенда, не падая если структура сборки отличается.
    - CRA обычно кладет файлы в `static/` и ссылается на `/static/...`
    - Vite обычно кладет файлы в `assets/` и ссылается на `/assets/...`
    """
    static_dir = frontend_dir / "static"
    assets_dir = frontend_dir / "assets"

    mounted_any = False
    if static_dir.exists() and static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        mounted_any = True
    else:
        logger.warning("Frontend 'static' dir not found at %s", static_dir)

    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        mounted_any = True
    else:
        logger.info("Frontend 'assets' dir not found at %s", assets_dir)

    if not mounted_any:
        logger.warning("No frontend static assets mounted (static/assets not found)")


# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить до конкретных доменов
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация компонентов
document_analyzer = DocumentAnalyzer()
document_generator = DocumentGenerator()
template_manager = TemplateManager()

# Разбор и генерация уезжают в тредпул, чтобы не блокировать цикл событий.
# Замер (сервер отдельным процессом, /health пингуется параллельно анализу):
# до — пик 1293 мс и 21 ответ за окно, после — пик 127 мс и 43 ответа.
# Медиана в обоих случаях 2 мс: блокировка была одним долгим провалом, а не
# общим замедлением — её видно по пику и по числу ответов, не по медиане.
#
# Но параллелизма здесь быть НЕ должно: анализатор и генератор держат общее
# изменяемое состояние (`self.morph` с ленивой инициализацией, `documents`,
# объект spaCy, потокобезопасность которого не гарантирована). Раньше их
# защищал сам факт исполнения в одном цикле событий; теперь защищает лок.
_ANALYSIS_LOCK = threading.Lock()
_GENERATION_LOCK = threading.Lock()

@app.get("/")
async def root():
    if frontend_dir:
        index_path = frontend_dir / "index.html"
        html = index_path.read_text(encoding="utf-8")
        inject = '''
        <script>
        (function() {
          // Ждем немного, чтобы preload.js успел загрузиться
          var checkAttempts = 0;
          var maxAttempts = 20; // Увеличиваем количество попыток
          function checkElectronAPI() {
            checkAttempts++;
            // Проверяем, загружен ли Electron API из preload.js
            // ВАЖНО: Проверяем не только analyzeDocument, но и downloadAllDocuments
            if (window.electronAPI &&
                typeof window.electronAPI.analyzeDocument === 'function' &&
                typeof window.electronAPI.downloadAllDocuments === 'function') {
              console.log('[index] Electron API loaded from preload.js');
              console.log('[index] Available methods:', Object.keys(window.electronAPI));
              console.log('[index] downloadAllDocuments type:', typeof window.electronAPI.downloadAllDocuments);
              // НЕ загружаем web-api.js если Electron API уже есть
              return;
            } else if (checkAttempts < maxAttempts) {
              // Продолжаем проверять
              console.log('[index] Waiting for Electron API, attempt', checkAttempts, 'of', maxAttempts);
              setTimeout(checkElectronAPI, 100);
            } else {
              // После всех попыток, если Electron API все еще нет, загружаем fallback
              console.warn('[index] Electron API not found after', maxAttempts, 'attempts');
              console.warn('[index] window.electronAPI exists:', !!window.electronAPI);
              if (window.electronAPI) {
                console.warn('[index] window.electronAPI methods:', Object.keys(window.electronAPI));
                console.warn('[index] downloadAllDocuments exists:', !!window.electronAPI.downloadAllDocuments);
              }
              console.warn('[index] Loading web-api.js fallback');
              var script = document.createElement('script');
              script.src = '/web-api.js';
              document.body.appendChild(script);
            }
          }
          // Начинаем проверку через небольшую задержку
          setTimeout(checkElectronAPI, 50);
        })();
        </script>
        '''
        if inject not in html:
            html = html.replace("</body>", inject + "\n</body>")
        return HTMLResponse(html)
    return {"message": "SberAct Document Generator API", "status": "running"}

if frontend_dir:
    _mount_frontend_static(app, frontend_dir)

    def _web_api_path():
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent
            meipass = getattr(sys, "_MEIPASS", None)
            for base in (exe_dir, exe_dir / "_internal", Path(meipass) if meipass else None):
                if base and (base / "static" / "web-api.js").exists():
                    return base / "static" / "web-api.js"
        return Path(__file__).resolve().parent / "static" / "web-api.js"

    @app.get("/web-api.js")
    async def serve_web_api():
        p = _web_api_path()
        if p.exists():
            return FileResponse(p, media_type="application/javascript")
        from fastapi.responses import Response
        return Response(status_code=404)

@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "components": {
        "analyzer": "ready",
        "generator": "ready",
        "templates": "ready"
    }}

def _detect_upload_suffix(content: bytes) -> str:
    """Определяет формат по магическим байтам. PDF: %PDF-, DOCX: PK (ZIP)."""
    if content[:5] == b"%PDF-":
        return ".pdf"
    if content[:2] == b"PK":
        return ".docx"
    return ".docx"


@app.post("/analyze-document")
async def analyze_document(document: UploadFile = File(...)):
    """
    Анализирует загруженный документ и извлекает данные.
    Поддерживаются форматы: .docx (Word), .pdf. Генерация актов по-прежнему только в .docx.
    """
    logger.info("Запрос на анализ документа")
    try:
        filename_lower = (document.filename or "").lower()
        if not (filename_lower.endswith(".docx") or filename_lower.endswith(".pdf")):
            raise HTTPException(
                status_code=400,
                detail="Поддерживаются только файлы .docx и .pdf"
            )

        # Читаем содержимое и определяем формат по магическим байтам (на случай неверного имени с клиента)
        content = await document.read()
        if not content:
            raise HTTPException(status_code=400, detail="Файл пуст")
        suffix = _detect_upload_suffix(content)

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            def _run():
                with _ANALYSIS_LOCK:
                    return document_analyzer.analyze(tmp_path)

            analysis_result = await run_in_threadpool(_run)
            return {
                "success": True,
                "data": analysis_result
            }
        finally:
            os.unlink(tmp_path)

    except ValueError as e:
        # Ошибки извлечения текста/поврежденный файл -> 400
        raise HTTPException(status_code=400, detail=f"Ошибка при анализе документа: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при анализе документа: {str(e)}")


class AnalyzeTextRequest(BaseModel):
    """Тело /analyze-text: плоский текст заявления (+ число страниц исходника)."""
    text: str
    page_count: Optional[int] = None


@app.post("/analyze-text")
async def analyze_text(request: AnalyzeTextRequest):
    """
    Анализирует уже извлечённый текст заявления (без файла).

    Используется convert-шагом: пользователь правит распознанный после
    OCR-конвертации текст в предпросмотре, и по «Далее» сюда приходит
    именно текст — файла-источника на этом пути нет.
    Формат ответа и ошибок идентичен /analyze-document.
    """
    logger.info("Запрос на анализ текста")
    try:
        def _run():
            with _ANALYSIS_LOCK:
                return document_analyzer.analyze_from_text(
                    request.text, page_count=request.page_count
                )

        analysis_result = await run_in_threadpool(_run)
        return {
            "success": True,
            "data": analysis_result
        }
    except ValueError as e:
        # Пустой/непригодный текст -> 400
        raise HTTPException(status_code=400, detail=f"Ошибка при анализе документа: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при анализе документа: {str(e)}")


@app.post("/docx-text")
async def docx_text(document: UploadFile = File(...)):
    """
    Текст DOCX тем же экстрактором, что и анализ (тело + колонтитулы +
    надписи + сноски). Convert-шаг показывает его пользователю для правки —
    в анализ уходит ровно то, что видно на экране, без потерь предпросмотра.
    """
    try:
        content = await document.read()
        if not content:
            raise HTTPException(status_code=400, detail="Файл пуст")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name
        try:
            def _run():
                with _ANALYSIS_LOCK:
                    text = document_analyzer.extract_text(tmp_path)
                    # Секции — представление ТОГО ЖЕ текста для посекционного
                    # редактора; анализ и «Скачать с правками» работают с плоским
                    # text (не меняются).
                    return text, document_analyzer.extract_sections(tmp_path)

            text, sections = await run_in_threadpool(_run)
            return {"success": True, "text": text, "sections": sections}
        finally:
            os.unlink(tmp_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Не удалось извлечь текст: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось извлечь текст: {str(e)}")


@app.post("/docx-apply-edits")
async def docx_apply_edits(
    document: UploadFile = File(...),
    edited_text: str = Form(...),
):
    """
    «Скачать с правками»: вставляет текстовые правки пользователя в оригинальную
    вёрстку DOCX (замена текста абзацев/ячеек, стили сохраняются) и отдаёт файл.
    Правки строк вне тела документа (колонтитулы/надписи) в DOCX не переносятся.
    """
    from docx_edit import apply_text_edits

    try:
        content = await document.read()
        if not content:
            raise HTTPException(status_code=400, detail="Файл пуст")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name
        out_path = tmp_path + ".edited.docx"
        try:
            def _run():
                with _ANALYSIS_LOCK:
                    original_text = document_analyzer.extract_text(tmp_path)
                    doc = apply_text_edits(tmp_path, edited_text, original_text)
                    doc.save(out_path)

            await run_in_threadpool(_run)
        finally:
            os.unlink(tmp_path)

        def _stream_and_cleanup():
            try:
                with open(out_path, "rb") as f:
                    yield from f
            finally:
                os.unlink(out_path)

        return StreamingResponse(
            _stream_and_cleanup(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="edited.docx"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось применить правки: {str(e)}")


# Прокси к конвертеру (sidecar-процесс на 127.0.0.1:8008).
# Фронт ходит только на наш origin (:8000) — порт конвертера наружу не течёт,
# CORS не нужен. Catch-all не привязан к конкретным путям конвертера: контракт
# (analyze/scan/native/status/download) живёт на стороне фронта.
CONVERTER_URL = os.environ.get("CONVERTER_URL", "http://127.0.0.1:8008")
CONVERTER_API_URL = os.environ.get("CONVERTER_API_URL", f"{CONVERTER_URL}/convert")
# Заголовки соединения не пробрасываем: они описывают hop, а не содержимое.
_CONVERT_HOP_HEADERS = {"host", "content-length", "connection", "transfer-encoding"}


@app.api_route("/convert/{conv_path:path}", methods=["GET", "POST"])
async def convert_proxy(conv_path: str, request: Request):
    return await _proxy_to_converter(f"{CONVERTER_API_URL}/{conv_path}", request)


_converter_client: Optional["httpx.AsyncClient"] = None  # noqa: F821


def _get_converter_client() -> "httpx.AsyncClient":  # noqa: F821
    """Один клиент на приложение: соединения переиспользуются, а не открываются
    заново на каждый тик поллинга. Закрывается в lifespan."""
    global _converter_client
    import httpx

    if _converter_client is None:
        # Upload скана и синхронный analyze могут длиться десятки секунд;
        # connect короткий — «конвертер не запущен» должен падать быстро.
        _converter_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=3.0))
    return _converter_client


async def _proxy_to_converter(url: str, request: Request):
    """
    Прозрачный проброс запроса к конвертеру: тело и content-type передаются
    как есть (multipart с boundary в заголовке проходит без пересборки),
    ответ стримится обратно (download DOCX не буферизуется в памяти).
    """
    import httpx

    _converter_touch()  # любой проброс = конвертером пользуются, сторож не трогает
    # URL приходит собранным: у /convert и /llm разные базы — CONVERTER_API_URL
    # уже включает суффикс /convert, и добавлять его второй раз нельзя.
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _CONVERT_HOP_HEADERS
    }
    body = await request.body()
    client = _get_converter_client()
    try:
        upstream = await client.send(
            client.build_request(
                request.method, url,
                headers=headers,
                content=body,
                params=request.query_params,
            ),
            stream=True,
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Конвертер не запущен. Запустите конвертацию заново или пропустите её."
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Конвертер не отвечает (таймаут)")
    except httpx.HTTPError as exc:
        # Обрыв протокола, сброс соединения, ошибка чтения: раньше эти ветки
        # уносили с собой незакрытый AsyncClient (ловились только ConnectError
        # и TimeoutException). Клиент теперь общий и живёт до shutdown, но
        # ответ всё равно нужен внятный, а не 500 с трейсбеком.
        raise HTTPException(status_code=502, detail=f"Сбой связи с конвертером: {exc}")

    async def _stream_and_close():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()  # клиент общий — его закрывает lifespan

    passthrough = {
        k: v for k, v in upstream.headers.items()
        if k.lower() in ("content-type", "content-disposition")
    }
    return StreamingResponse(
        _stream_and_close(),
        status_code=upstream.status_code,
        headers=passthrough,
    )

def _default_converter_dir() -> Path:
    """converter/ в корне проекта (рядом с python-backend)."""
    return Path(__file__).resolve().parents[2] / "converter"


CONVERTER_DIR = Path(os.environ.get("CONVERTER_DIR", str(_default_converter_dir())))
CONVERTER_PORT = os.environ.get("CONVERTER_PORT", "8008")
CONVERTER_START_TIMEOUT_S = 180  # холодный старт с LLM — десятки секунд, с запасом
CONVERTER_IDLE_TIMEOUT_S = int(os.environ.get("CONVERTER_IDLE_TIMEOUT_S", "300"))
CONVERTER_IDLE_CHECK_S = 30  # как часто сторож смотрит на простой

_converter_process: Optional["subprocess.Popen[bytes]"] = None
_converter_start_lock: Optional["asyncio.Lock"] = None


def _get_converter_lock() -> "asyncio.Lock":
    """Лок создаём лениво: на импорте модуля event loop ещё нет."""
    global _converter_start_lock
    if _converter_start_lock is None:
        _converter_start_lock = asyncio.Lock()
    return _converter_start_lock


# Момент последнего обращения к конвертеру; None — им ещё не пользовались.
_converter_last_used: Optional[float] = None


def _converter_touch() -> None:
    """Отмечает активность. Монотонные часы: перевод системного времени не собьёт."""
    global _converter_last_used
    _converter_last_used = time.monotonic()


async def _converter_idle_watchdog() -> None:
    """Гасит простаивающий конвертер, возвращая ОС его память."""
    while True:
        await asyncio.sleep(CONVERTER_IDLE_CHECK_S)
        try:
            if _converter_process is None or _converter_last_used is None:
                continue  # нашего процесса нет — гасить нечего (внешний не трогаем)
            idle = time.monotonic() - _converter_last_used
            if idle >= CONVERTER_IDLE_TIMEOUT_S:
                logger.info("Конвертер простаивал %.0f с — останавливаем", idle)
                _kill_converter()
        except Exception:  # сторож не имеет права уронить приложение
            logger.exception("Сбой сторожа простоя конвертера")


async def _converter_healthy() -> bool:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{CONVERTER_URL}/health")
            return res.status_code == 200
    except httpx.HTTPError:
        return False


def _converter_command() -> Optional[list]:
    """
    Команда запуска конвертера; None — не установлен.
    Запускаем НЕ его main.py, а наш лаунчер run_converter.py (тем же venv
    конвертера): у upstream порт захардкожен на 8000, лаунчер поднимает то же
    приложение на CONVERTER_PORT без правок кода конвертера.
    """
    is_windows = sys.platform == "win32"
    py_rel = Path("Scripts" if is_windows else "bin") / ("python.exe" if is_windows else "python")
    # Прод: портируемый Python рядом с конвертером (assemble-converter.ps1), зависимости
    # берём из .venv через PYTHONPATH (см. _converter_env). .venv сам не самодостаточен.
    runtime_py = CONVERTER_DIR / "pyruntime" / ("python.exe" if is_windows else Path("bin") / "python")
    # install_offline.bat конвертера создаёт `.venv`; `venv` — фолбэк на ручную установку
    candidates = [CONVERTER_DIR / ".venv" / py_rel, CONVERTER_DIR / "venv" / py_rel]
    venv_python = next((p for p in candidates if p.exists()), None)
    entry = CONVERTER_DIR / "main.py"
    # Лаунчер: в проде рядом с конвертером (исходников бэкенда нет), в dev — в app/
    launcher = CONVERTER_DIR / "run_converter.py"
    if not launcher.exists():
        launcher = Path(__file__).resolve().parent / "run_converter.py"
    if not entry.exists():
        return None
    if runtime_py.exists():
        return [str(runtime_py), str(launcher)]
    if venv_python is not None:
        return [str(venv_python), str(launcher)]
    return None


def _converter_env() -> dict:
    """Доп. env для запуска конвертера: в проде — PYTHONPATH на .venv/site-packages."""
    is_windows = sys.platform == "win32"
    runtime_py = CONVERTER_DIR / "pyruntime" / ("python.exe" if is_windows else Path("bin") / "python")
    if not runtime_py.exists():
        return {}
    site = CONVERTER_DIR / ".venv" / ("Lib/site-packages" if is_windows else "lib/python3.12/site-packages")
    if not site.exists():
        return {}
    # PYTHONNOUSERSITE: у пользователя может стоять свой Python 3.12 с пакетами в
    # %APPDATA%\Python\Python312\site-packages — они попадают в sys.path РАНЬШЕ
    # PYTHONPATH и способны подменить torch/докling чужой версией. Конвертер обязан
    # брать зависимости только из своего .venv.
    return {"PYTHONPATH": str(site), "PYTHONNOUSERSITE": "1"}


@app.post("/converter/start")
async def converter_start():
    """
    Поднимает sidecar-конвертер, если он ещё не отвечает, и ждёт /health.
    Уже работающий (в т.ч. запущенный вручную/Electron'ом) — переиспользуется.
    """
    global _converter_process

    _converter_touch()  # отсчёт простоя ведём от старта, а не от первой конвертации
    # Быстрый путь мимо лока: сервис уже отвечает — сериализовать нечего.
    if await _converter_healthy():
        return {"ok": True, "external": _converter_process is None}

    async with _get_converter_lock():
        # Повторная проверка ПОД локом обязательна: пока ждали очередь, конкурент
        # мог уже поднять конвертер. Без неё параллельные вызовы плодят Popen'ы,
        # дерущиеся за один порт.
        if await _converter_healthy():
            return {"ok": True, "external": _converter_process is None}

        command = _converter_command()
        if command is None:
            return {
                "ok": False,
                "error": (
                    f"Конвертер не найден в {CONVERTER_DIR} "
                    "(укажите папку через переменную окружения CONVERTER_DIR)"
                ),
            }

        # Любой сбой спавна/ожидания отдаём как {ok:false}, а не 500 — иначе фронт
        # ловит HTTP-ошибку и показывает пользователю пугающий экран вместо «идёт запуск».
        try:
            logger.info("Запускаем конвертер: %s", " ".join(command))
            _converter_process = subprocess.Popen(
                command,
                cwd=str(CONVERTER_DIR),
                env={
                    **os.environ,
                    "CONVERTER_PORT": CONVERTER_PORT,
                    "CONVERTER_DIR": str(CONVERTER_DIR),
                    **_converter_env(),
                },
            )

            deadline = asyncio.get_event_loop().time() + CONVERTER_START_TIMEOUT_S
            while asyncio.get_event_loop().time() < deadline:
                if _converter_process.poll() is not None:
                    code = _converter_process.returncode
                    _converter_process = None
                    return {"ok": False, "error": f"Конвертер завершился до готовности (код {code})"}
                if await _converter_healthy():
                    return {"ok": True, "external": False}
                await asyncio.sleep(1.0)

            _kill_converter()
            return {"ok": False, "error": f"Конвертер не поднялся за {CONVERTER_START_TIMEOUT_S} с"}
        except Exception as e:
            logger.exception("Сбой запуска конвертера")
            _kill_converter()
            return {"ok": False, "error": f"Не удалось запустить конвертер: {e}"}


def _kill_converter() -> None:
    global _converter_process
    if _converter_process is not None and _converter_process.poll() is None:
        logger.info("Останавливаем конвертер (pid %s)", _converter_process.pid)
        _converter_process.kill()
    _converter_process = None


@app.post("/converter/stop")
async def converter_stop():
    """Глушит НАШ процесс конвертера (внешний не трогаем — не мы запускали)."""
    _kill_converter()
    return {"ok": True}


@app.get("/converter/status")
async def converter_status():
    running = _converter_process is not None and _converter_process.poll() is None
    return {"running": running, "healthy": await _converter_healthy()}


# Теневые LLM-подсказки. Раньше их проксировали в конвертер (там жили
# llama-cpp-python и файл модели); с переездом на llama-server бэкенд
# обслуживает их сам, и docling ради подсказок больше не поднимается.
app.include_router(llm_router)


GENERATED_MAX_AGE_H = int(os.environ.get("SBERACT_GENERATED_MAX_AGE_H", "24"))
GENERATED_CLEANUP_EVERY_S = 3600
# Первый проход — вскоре после старта, а не через час: основной мусор это
# наследство ПРОШЛЫХ запусков, а сессия юриста часто короче часа. Небольшая
# задержка нужна, чтобы уборка не соревновалась за диск с подъёмом приложения.
GENERATED_CLEANUP_FIRST_S = 60


async def _generated_cleanup_loop() -> None:
    """Периодически сносит акты старше суток. Задача-демон, как сторож простоя."""
    delay = GENERATED_CLEANUP_FIRST_S
    while True:
        await asyncio.sleep(delay)
        delay = GENERATED_CLEANUP_EVERY_S
        try:
            # В тредпул: уборка ходит по диску, цикл событий держать нельзя.
            await run_in_threadpool(
                document_generator.cleanup_old_documents, GENERATED_MAX_AGE_H
            )
        except Exception:  # уборщик не имеет права уронить приложение
            logger.exception("Сбой уборки сгенерированных документов")


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Сторож простоя: UI больше не гасит конвертер после каждого файла, память
    # возвращает этот таймер. Задача-демон, живёт столько же, сколько приложение.
    watchdog = asyncio.create_task(_converter_idle_watchdog())
    # Уборка сгенерированных актов: без неё папка росла бесконечно (в дереве
    # разработки успело накопиться 376 файлов на 13 МБ), а реестр в памяти
    # держал полный набор полей каждого документа до конца жизни процесса.
    housekeeper = asyncio.create_task(_generated_cleanup_loop())
    try:
        yield
    finally:
        for task in (watchdog, housekeeper):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Ни конвертер, ни llama-server не должны переживать бэкенд:
        # осиротевший процесс держит гигабайты и порт.
        _kill_converter()
        try:
            from llm import server as _llm_server
            _llm_server.stop()
        except Exception:
            logger.warning("не удалось остановить llama-server", exc_info=True)

        # Незавершённая подсказка держала выход интерпретатора (замер: 3226 мс
        # на трёхсекундной задаче) — Electron успевал убить бэкенд жёстко, мимо
        # этого самого хука.
        try:
            from llm_api import shutdown_executor
            shutdown_executor()
        except Exception:
            logger.warning("не удалось остановить пул LLM-подсказок", exc_info=True)

        global _converter_client
        if _converter_client is not None:
            with contextlib.suppress(Exception):
                await _converter_client.aclose()
            _converter_client = None


app.router.lifespan_context = _lifespan


@app.get("/templates")
async def get_templates():
    """
    Возвращает список доступных шаблонов
    """
    try:
        templates = template_manager.get_all_templates()
        return templates
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении шаблонов: {str(e)}")

@app.get("/banks")
async def get_banks():
    """
    Возвращает единый реестр банков-кредиторов (display + реквизиты + алиасы).
    Единый источник для выпадающего списка и автозаполнения на фронте.
    """
    try:
        return list_banks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении банков: {str(e)}")

@app.post("/generate-document")
async def generate_document(request_data: Dict[str, Any]):
    """
    Генерирует документ на основе выбранного шаблона и данных
    """
    # Раньше здесь печатался ВЕСЬ request_data в stdout: это десятки килобайт
    # персональных данных из заявления в консоли на каждую генерацию.
    logger.info("Запрос на генерацию документа: тип %s, полей %d",
                request_data.get("template_type"),
                len(request_data.get("data") or {}))
    try:
        # Извлекаем данные из запроса
        template_type = request_data.get("template_type")
        extracted_data = request_data.get("data")

        if not template_type or not extracted_data:
            raise HTTPException(status_code=400, detail="Отсутствуют обязательные поля: template_type или data")

        # Генерируем документ. Тредпул + лок: генерация пишет в общий
        # `document_generator.documents` и открывает шаблоны с диска.
        def _run():
            with _GENERATION_LOCK:
                return document_generator.generate(template_type, extracted_data)

        result = await run_in_threadpool(_run)

        if result["success"]:
            # Проверяем, генерируется ли один документ или несколько
            if "documents" in result:
                # Генерируется несколько документов
                response = {
                    "success": True,
                    "documents": result["documents"],
                    "document_ids": result["document_ids"],
                    "count": result["count"],
                    "message": f"Успешно сгенерировано {result['count']} документов"
                }
                # Выбранные акты, которые сгенерировать не удалось (нет шаблона/ветки маппинга)
                if result.get("warnings"):
                    response["warnings"] = result["warnings"]
                return response
            else:
                # Генерируется один документ (старый формат)
                return {
                    "success": True,
                    "document_id": result["document_id"],
                    "file_path": result["file_path"]
                }
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации документа: {str(e)}")

@app.get("/download-document/{document_id}")
async def download_document(document_id: str):
    """
    Скачивает сгенерированный документ
    """
    try:
        # Используем ту же папку, что и document_generator (абсолютный путь при frozen)
        generated_dir = document_generator.generated_dir
        document_path = generated_dir / f"{document_id}.docx"

        if not document_path.exists():
            raise HTTPException(status_code=404, detail="Документ не найден")

        # Имя файла делаем таким же, как в интерфейсе (document_name)
        doc_info = document_generator.documents.get(document_id, {})
        doc_name = doc_info.get("document_name", f"Судебный_акт_{document_id}")
        safe_name = str(doc_name).replace("\\", "_").replace("/", "_").replace(":", "_").replace('"', "").strip()
        if not safe_name:
            safe_name = f"Судебный_акт_{document_id}"
        filename = f"{safe_name}.docx"

        return FileResponse(
            path=str(document_path),
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при скачивании документа: {str(e)}")

@app.get("/download-zip")
async def download_zip_get(ids: str = ""):
    """
    Скачивание ZIP по ID документов (GET).
    ВНИМАНИЕ: Этот endpoint используется только как fallback для WebView без Electron.
    В Electron приложении должен использоваться POST /download-all-documents через IPC.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(" Используется GET /download-zip - это fallback! Electron IPC должен использоваться вместо этого.")

    if not ids:
        raise HTTPException(status_code=400, detail="Не указаны ID документов (ids)")
    doc_ids = [i.strip() for i in ids.split(",") if i.strip()]
    if not doc_ids:
        raise HTTPException(status_code=400, detail="Не указаны ID документов")
    try:
        import zipfile
        import tempfile

        def _build_zip() -> bytes:
            generated_dir = document_generator.generated_dir
            # Дескриптор закрываем сразу: zipfile открывает файл заново по пути,
            # а незакрытый handle течёт и на Windows держит файл заблокированным.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_zip:
                zip_path = Path(temp_zip.name)
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for doc_id in doc_ids:
                        file_path = generated_dir / f"{doc_id}.docx"
                        if file_path.exists():
                            doc_info = document_generator.documents.get(doc_id, {})
                            doc_name = doc_info.get("document_name", f"document_{doc_id}")
                            zipf.write(file_path, f"{doc_name}.docx")
                return zip_path.read_bytes()
            finally:
                try:
                    zip_path.unlink()
                except OSError as exc:
                    logger.warning(f"Could not delete temp file {zip_path}: {exc}")

        # Сжатие и чтение архива целиком в память — блокирующая работа,
        # в цикле событий ей не место.
        zip_data = await run_in_threadpool(_build_zip)
        logger.info(f"Created ZIP file with {len(doc_ids)} documents, size: {len(zip_data)} bytes")

        # ВАЖНО: Используем правильные заголовки для скачивания файла
        # Content-Disposition с attachment заставляет браузер скачать файл
        return Response(
            content=zip_data,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="generated_documents.zip"',
                "Content-Type": "application/zip",
                "Content-Length": str(len(zip_data)),
                "Cache-Control": "no-cache"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/download-zip-save")
async def download_zip_save(payload: Dict[str, Any]):
    """
    Создает ZIP с указанными документами и СОХРАНЯЕТ его НА ДИСКЕ
    (без браузерного скачивания), возвращая путь к файлу.
    Используется в desktop-версии (PyInstaller + webview), где
    нормальное скачивание через браузер может не работать.
    """
    ids = payload.get("ids", "")
    if not ids:
        raise HTTPException(status_code=400, detail="Не указаны ID документов (ids)")

    doc_ids = [i.strip() for i in ids.split(",") if i.strip()]
    if not doc_ids:
        raise HTTPException(status_code=400, detail="Не указаны ID документов")

    try:
        import zipfile

        generated_dir = document_generator.generated_dir
        # Папка, куда будем складывать ZIP-файлы
        downloads_dir = generated_dir / "zips"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        # Определяем "человеческое" имя для ZIP
        first_doc_name: Optional[str] = None

        # Имя файла с датой/временем, чтобы файлы не затирались
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Временный путь (переименуем после того, как узнаем имя)
        temp_zip_path = downloads_dir / f"generated_documents_{ts}.zip"

        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for doc_id in doc_ids:
                file_path = generated_dir / f"{doc_id}.docx"
                if file_path.exists():
                    doc_info = document_generator.documents.get(doc_id, {})
                    doc_name = doc_info.get("document_name", f"document_{doc_id}")

                    # Запоминаем имя первого документа для имени ZIP
                    if first_doc_name is None:
                        first_doc_name = str(doc_name)

                    # Внутри ZIP файлы называем так же, как в интерфейсе
                    inner_safe_name = str(doc_name).replace("\\", "_").replace("/", "_").replace(":", "_").replace('"', "").strip()
                    if not inner_safe_name:
                        inner_safe_name = f"document_{doc_id}"
                    zipf.write(file_path, f"{inner_safe_name}.docx")

        # Теперь выбираем финальное имя ZIP
        if len(doc_ids) == 1 and first_doc_name:
            base_name = str(first_doc_name)
        else:
            base_name = f"Судебные акты {ts}"

        zip_safe_name = base_name.replace("\\", "_").replace("/", "_").replace(":", "_").replace('"', "").strip()
        if not zip_safe_name:
            zip_safe_name = f"generated_documents_{ts}"

        target_path = downloads_dir / f"{zip_safe_name}.zip"
        # Переименуем временный файл в конечное имя
        temp_zip_path.replace(target_path)

        logger.info(f"Saved ZIP file with {len(doc_ids)} documents to {target_path}")

        return {
            "success": True,
            "filePath": str(target_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании архива: {str(e)}")


@app.post("/download-all-documents")
async def download_all_documents(request: dict):
    """
    Скачивает все сгенерированные документы в виде ZIP архива
    """
    try:
        import zipfile
        import tempfile
        from pathlib import Path

        logger.info(f" API: Получен запрос на скачивание документов")
        logger.info(f" API: Данные запроса: {request}")

        document_ids = request.get('document_ids', '')
        download_path = request.get('download_path', '')

        logger.info(f" API: ID документов: {document_ids}")
        logger.info(f" API: Путь для скачивания: {download_path}")

        # Парсим ID документов
        ids = document_ids.split(',') if document_ids else []

        if not ids:
            raise HTTPException(status_code=400, detail="Не указаны ID документов")

        # Определяем путь для сохранения
        # Всегда создаем временный файл для скачивания через диалог
        # download_path игнорируется - пользователь выбирает место через Electron диалог
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        zip_path = Path(temp_zip.name)

        # Создаем ZIP архив (используем ту же папку, что и document_generator)
        generated_dir = document_generator.generated_dir
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for doc_id in ids:
                file_path = generated_dir / f"{doc_id}.docx"
                if file_path.exists():
                    # Получаем информацию о документе для имени файла
                    doc_info = document_generator.documents.get(doc_id, {})
                    doc_name = doc_info.get('document_name', f'document_{doc_id}')

                    # Добавляем файл в архив
                    zipf.write(file_path, f"{doc_name}.docx")

        # Всегда возвращаем файл для скачивания через Electron диалог
        logger.info(f" API: Возвращаем файл для скачивания: {zip_path}")
        # ВНИМАНИЕ: Этот endpoint используется только как fallback
        # В Electron приложении файл должен сохраняться через диалог, а не напрямую
        logger.warning(f" Файл будет скачан в папку загрузок браузера: generated_documents.zip")
        return FileResponse(
            path=str(zip_path),
            filename="generated_documents.zip",
            media_type="application/zip"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при создании архива: {str(e)}")

@app.get("/download-paths")
async def get_download_paths():
    """
    Возвращает список доступных путей для сохранения документов
    """
    try:
        from pathlib import Path

        logger.info(f" API: Получен запрос на список путей для скачивания")

        # Предлагаем несколько вариантов путей
        paths = [
            {
                "name": "Рабочий стол",
                "path": str(Path.home() / "Desktop"),
                "description": "Сохранить на рабочий стол"
            },
            {
                "name": "Папка приложения",
                "path": str(app_paths.generated_dir()),
                "description": "Сохранить в рабочую папку приложения"
            },
            {
                "name": "Документы",
                "path": str(Path.home() / "Documents"),
                "description": "Сохранить в папку Документы"
            }
        ]

        return {
            "success": True,
            "paths": paths
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при получении путей: {str(e)}")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Удаляет сгенерированный документ
    """
    try:
        success = document_generator.delete_document(document_id)

        if success:
            return {"success": True, "message": "Документ удален"}
        else:
            raise HTTPException(status_code=404, detail="Документ не найден")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении документа: {str(e)}")

if __name__ == "__main__":
    try:
        # При запуске из exe (PyInstaller) — рабочая директория = папка с exe
        if getattr(sys, "frozen", False):
            os.chdir(Path(sys.executable).parent)

        # Записываемые каталоги — в data dir (в проде вне папки установки)
        app_paths.temp_dir()
        app_paths.generated_dir()

        if getattr(sys, "frozen", False):
            # Десктоп: бэкенд — чистый API-сервер на loopback, окно даёт Electron.
            # (Старый standalone-режим с webview/браузером убран вместе с onefile-сборкой.)
            uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
        else:
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=8000,
                reload=True,
                log_level="info"
            )
    except KeyboardInterrupt:
        sys.exit(0)
