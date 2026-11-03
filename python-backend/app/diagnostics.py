"""Понятные отказы API и ограниченный журнал технической диагностики."""

from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
import json
import logging
import re
import sys
import threading
import traceback
import uuid
import zipfile

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

REQUEST_ID = ContextVar("diagnostic_request_id", default="")
OPERATION = ContextVar("diagnostic_operation", default="")
PREFIX = "SBERACT_DIAGNOSTIC "
LOCK = threading.RLock()
EVENTS = deque(maxlen=500)
FILE_HANDLER = None
LOGGER = logging.getLogger(__name__)
PRIVATE_PAYLOAD = re.compile(
    r"""requestData\s*:|(?:debtorName|applicantName|rawText|passportNumber|edited_text)["']?\s*[:=]|Данные для замены|Очищенные данные|Полученные данные""",
    re.I,
)
LONG_NUMBER = re.compile(r"(?<!\d)\d{10,19}(?!\d)")
PERSON_NAME = re.compile(r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\b")
USER_PATH = re.compile(r"(?i)([\\/]Users[\\/])[^\\/\s]+")
OPERATION_MESSAGES = {
    "/analyze-document": "Не удалось проанализировать документ.",
    "/analyze-text": "Не удалось проанализировать текст.",
    "/generate-document": "Не удалось сформировать документы.",
    "/download-document": "Не удалось подготовить документ для сохранения.",
    "/download-all-documents": "Не удалось подготовить архив.",
    "/converter": "Не удалось выполнить действие с конвертером.",
}
TECHNICAL_TEXT = re.compile(
    r"Traceback|WinError|Errno|Permission denied|No such file|Package not found|not a zip file|[A-Z]:\\", re.I
)


def operation_message(path):
    return next(
        (message for prefix, message in OPERATION_MESSAGES.items() if path.startswith(prefix)),
        "Не удалось выполнить операцию.",
    )


ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MODULE_PATTERN = re.compile(r"No module named ['\"](?P<module>[\w.]+)['\"]", re.I)


def redact(value):
    text = str(value)
    text = "\n".join(
        "[содержимое заявления скрыто]" if PRIVATE_PAYLOAD.search(line) else line for line in text.split("\n")
    )
    text = USER_PATH.sub(r"\1[пользователь]", text)
    text = LONG_NUMBER.sub("[реквизит скрыт]", text)
    text = PERSON_NAME.sub("[ФИО скрыто]", text)
    return text[:2000] + "\n[часть журнала сокращена]\n" + text[-9000:] if len(text) > 12000 else text


def event(component, message, *, level="error", code="", incident_id=""):
    item = {
        "time": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "level": level,
        "message": redact(message),
        "operation": OPERATION.get(),
        "code": code,
        "incidentId": incident_id or REQUEST_ID.get(),
    }
    with LOCK:
        EVENTS.append(item)
        line = json.dumps(item, ensure_ascii=False)
        if FILE_HANDLER is not None:
            try:
                record = logging.LogRecord("diagnostics", logging.INFO, "", 0, line, (), None)
                FILE_HANDLER.emit(record)
            except Exception:
                pass
    try:
        if sys.stdout:
            sys.stdout.write(PREFIX + line + "\n")
            sys.stdout.flush()
    except Exception:
        pass
    return item


def snapshot():
    with LOCK:
        return list(EVENTS)


class DiagnosticHandler(logging.Handler):
    def emit(self, record):
        try:
            message = self.format(record)
            event("backend", message, level=record.levelname.lower())
        except Exception:
            pass


def template_context(data):
    fields = data.get("fields") or {}
    entity = data.get("selectedEntityType") or fields.get("selectedEntityType") or data.get("entityType")
    kind = data.get("selectedApplicationKind") or fields.get("selectedApplicationKind")
    labels = {"individual": "ФЛ", "ip": "ИП", "legal": "ЮЛ", "kfh": "КФХ"}
    kinds = {
        "rtk": "включение в РТК",
        "self": "самобанкротство",
        "other": "инициирование",
        "self_bankruptcy": "самобанкротство",
    }
    return ", ".join(value for value in (kinds.get(str(kind), ""), labels.get(str(entity), "")) if value)


def error_info(exc, fallback="Операция не выполнена.", _seen=None):
    seen = set() if _seen is None else _seen
    if id(exc) in seen:
        return "UNEXPECTED_ERROR", fallback, "Откройте «Подробности» и сохраните отчёт."
    seen.add(id(exc))
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        result = error_info(cause, fallback, seen)
        if result[0] not in ("UNEXPECTED_ERROR", "INVALID_INPUT"):
            return result
    text = str(exc)
    if (
        isinstance(exc, PermissionError)
        or "Permission denied" in text
        or re.search(r"WinError (?:5|32)|Errno 13", text)
    ):
        return (
            "ACCESS_DENIED",
            "Нет доступа к файлу или папке.",
            "Проверьте права доступа. Если документ открыт в Word, закройте его.",
        )
    if isinstance(exc, zipfile.BadZipFile) or "Package not found" in text or "not a zip file" in text:
        return (
            "INVALID_DOCUMENT",
            "Не удалось прочитать документ: файл повреждён или имеет неподходящий формат.",
            "Откройте его в Word и сохраните заново в формате DOCX.",
        )
    if isinstance(exc, FileNotFoundError) or re.search(r"No such file|WinError 2\b|Errno 2\b", text):
        return (
            "FILE_NOT_FOUND",
            "Не найден необходимый файл.",
            "Проверьте наличие документа или компонентов приложения.",
        )
    if re.search(r"No space left|WinError 112\\b|Errno 28\\b", text):
        return "DISK_FULL", "Недостаточно свободного места на диске.", "Освободите место или выберите другой диск."
    if isinstance(exc, MemoryError) or "out of memory" in text.lower():
        return "OUT_OF_MEMORY", "Недостаточно оперативной памяти.", "Закройте другие программы и повторите операцию."
    if isinstance(exc, ValueError):
        message = text if re.search(r"[А-ЯЁа-яё]", text) and len(text) <= 600 else fallback
        return "INVALID_INPUT", message, "Проверьте документ и введённые данные."
    return "UNEXPECTED_ERROR", fallback, "Откройте «Подробности» и сохраните отчёт об ошибке."


def failure(exc, *, message="Операция не выполнена.", code=None, incident_id=None):
    incident = incident_id or REQUEST_ID.get() or uuid.uuid4().hex
    reason, friendly, hint = error_info(exc, message)
    event(
        "backend",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        code=code or reason,
        incident_id=incident,
    )
    return {"message": friendly, "hint": hint, "code": code or reason, "incidentId": incident}


def startup_failure(output="", *, exit_code=None, timeout=False, missing=False):
    incident = REQUEST_ID.get() or uuid.uuid4().hex
    module = MODULE_PATTERN.search(output)
    if missing:
        code, message, hint = (
            "CONVERTER_NOT_INSTALLED",
            "Не найдены компоненты конвертера.",
            "Установите или восстановите компонент конвертации.",
        )
    elif module:
        code, message, hint = (
            "CONVERTER_DEPENDENCY_MISSING",
            "Конвертер не запустился: отсутствует необходимый модуль.",
            "Восстановите компонент конвертации через установщик или обновление.",
        )
    elif re.search(r"DLL load failed|WinError 126|cannot open shared object", output, re.I):
        code, message, hint = (
            "CONVERTER_LIBRARY_MISSING",
            "Не удалось загрузить библиотеку конвертера.",
            "Восстановите компоненты приложения. Точная библиотека указана в подробностях.",
        )
    elif re.search(r"address already in use|WinError 10048", output, re.I):
        code, message, hint = (
            "CONVERTER_PORT_IN_USE",
            "Порт конвертера занят другой программой.",
            "Закройте другую копию приложения и повторите запуск.",
        )
    elif re.search(r"Permission denied|WinError 5|Access is denied", output, re.I):
        code, message, hint = (
            "CONVERTER_ACCESS_DENIED",
            "Система запретила запуск конвертера.",
            "Проверьте права доступа и сообщения защиты системы.",
        )
    elif re.search(r"MemoryError|OutOfMemoryError|out of memory|cannot allocate memory", output, re.I):
        code, message, hint = (
            "CONVERTER_OUT_OF_MEMORY",
            "Недостаточно памяти для запуска конвертера.",
            "Закройте другие программы и повторите запуск.",
        )
    elif re.search(r"FileNotFoundError|can't open file|WinError 2\\b", output, re.I):
        code, message, hint = (
            "CONVERTER_FILE_MISSING",
            "Не найден файл запуска конвертера.",
            "Восстановите компонент конвертации.",
        )
    elif timeout:
        code, message, hint = (
            "CONVERTER_START_TIMEOUT",
            "Конвертер не успел запуститься.",
            "Повторите запуск. Если ошибка повторяется, сохраните отчёт.",
        )
    else:
        code, message, hint = (
            "CONVERTER_START_FAILED",
            "Конвертер завершился при запуске.",
            "Откройте «Подробности» и сохраните отчёт об ошибке.",
        )
    event("converter", f"exit={exit_code}; timeout={timeout}\n{output}", code=code, incident_id=incident)
    return {
        "ok": False,
        "error": message,
        "message": message,
        "hint": hint,
        "code": code,
        "incidentId": incident,
        "exitCode": exit_code,
    }


class ProcessOutput:
    """Дренирует pipe без блокировки процесса и хранит ограниченный хвост."""

    def __init__(self, process):
        self.process = process
        self.tail = ""
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        import codecs

        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            stream = self.process.stdout
            read = getattr(stream, "read1", stream.read)
            while True:
                chunk = read(4096)
                if not chunk:
                    break
                text = decoder.decode(chunk)
                with self.lock:
                    self.tail = (self.tail + text)[-32768:]
                level = "error" if re.search(r"error|exception|traceback|failed|ошиб", text, re.I) else "info"
                event("converter", text, level=level)
        except Exception as exc:
            event("converter", f"Не удалось прочитать вывод процесса: {exc}", level="warning")

    def output(self, finished=False):
        if finished:
            self.thread.join(timeout=0.5)
        with self.lock:
            return self.tail


def install(app, log_dir):
    global FILE_HANDLER
    if FILE_HANDLER is not None:
        FILE_HANDLER.close()
    try:
        folder = Path(log_dir)
        folder.mkdir(parents=True, exist_ok=True)
        FILE_HANDLER = RotatingFileHandler(
            folder / "diagnostics.log", maxBytes=2 * 1024 * 1024, backupCount=1, encoding="utf-8", delay=True
        )
        FILE_HANDLER.setFormatter(logging.Formatter("%(message)s"))
    except OSError:
        FILE_HANDLER = None
    root = logging.getLogger()
    if not any(isinstance(h, DiagnosticHandler) for h in root.handlers):
        handler = DiagnosticHandler(level=logging.WARNING)
        handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
        root.addHandler(handler)

    @app.middleware("http")
    async def request_context(request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        incident = supplied if ID_PATTERN.fullmatch(supplied) else uuid.uuid4().hex
        request.state.incident_id = incident
        token = REQUEST_ID.set(incident)
        operation_token = OPERATION.set(request.method + " " + request.url.path)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                LOGGER.exception("Необработанный сбой запроса %s", request.url.path)
                body = failure(exc, message=operation_message(request.url.path), incident_id=incident)
                response = JSONResponse(status_code=500, content={"detail": body})
            response.headers["X-Request-ID"] = incident
            if response.status_code >= 400:
                event(
                    "backend",
                    f"{request.method} {request.url.path}: {response.status_code}",
                    code="HTTP_ERROR",
                    incident_id=incident,
                )
            return response
        finally:
            REQUEST_ID.reset(token)
            OPERATION.reset(operation_token)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        incident = getattr(request.state, "incident_id", "") or uuid.uuid4().hex
        if isinstance(exc.detail, dict):
            body = {**exc.detail, "incidentId": exc.detail.get("incidentId") or incident}
        elif exc.status_code in (502, 503, 504) and "конвертер" in str(exc.detail).lower():
            body = {
                "code": "CONVERTER_TIMEOUT" if exc.status_code == 504 else "CONVERTER_UNAVAILABLE",
                "message": "Конвертер не отвечает." if exc.status_code == 504 else "Нет связи с конвертером.",
                "hint": "Повторите запуск конвертации. Если ошибка повторяется, сохраните отчёт.",
                "incidentId": incident,
            }
        elif exc.status_code < 500:
            text = str(exc.detail)
            reason, friendly, hint = error_info(RuntimeError(text), operation_message(request.url.path))
            body = {
                "code": reason if reason != "UNEXPECTED_ERROR" else "REQUEST_REJECTED",
                "message": friendly if TECHNICAL_TEXT.search(text) else text,
                "hint": hint if TECHNICAL_TEXT.search(text) else "Проверьте данные и выбранные действия.",
                "incidentId": incident,
            }
        else:
            LOGGER.error("HTTP %s: %s", exc.status_code, exc.detail)
            body = failure(
                RuntimeError(str(exc.detail)), message=operation_message(request.url.path), incident_id=incident
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": body}, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        incident = getattr(request.state, "incident_id", "") or uuid.uuid4().hex
        event("backend", "Неверный формат запроса", code="INVALID_REQUEST", incident_id=incident)
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "INVALID_REQUEST",
                    "message": "Не заполнены обязательные поля или указан неверный формат данных.",
                    "hint": "Проверьте заполнение формы.",
                    "incidentId": incident,
                }
            },
        )

    @app.get("/diagnostics")
    async def diagnostics_snapshot():
        return {"events": snapshot(), "pythonVersion": sys.version.split()[0]}
