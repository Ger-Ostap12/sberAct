"""Имя ZIP-архива с готовыми актами: ФИО должника и дата генерации."""
import re
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import quote

# Запрещённые в именах файлов символы плюс кавычки, которые ломают заголовок.
_ЗАПРЕЩЁННЫЕ = re.compile(r'[\\/:*?"<>|\r\n\t«»]')

ЗАПАСНОЕ_ИМЯ = "Судебные акты"


def sanitize_file_name(name: str) -> str:
    """Имя, пригодное для файловой системы: без служебных символов и хвостовых точек."""
    чистое = _ЗАПРЕЩЁННЫЕ.sub(" ", str(name or ""))
    чистое = re.sub(r"\s+", " ", чистое).strip()
    return чистое.rstrip(". ")


def content_disposition(file_name: str) -> str:
    """Заголовок скачивания: кириллица едет в filename* (RFC 5987), ASCII — запасной."""
    ascii_имя = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name).strip("_") or "documents.zip"
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
        ascii_имя, quote(file_name, safe=""))


def debtor_display_name(data: Dict[str, Any]) -> str:
    """ФИО должника из данных генерации. В ипотеке с несколькими — первый."""
    if not isinstance(data, dict):
        return ""
    должники = data.get("debtors")
    if isinstance(должники, list) and должники:
        первый = должники[0]
        if isinstance(первый, dict):
            имя = sanitize_file_name(первый.get("name"))
            if имя:
                return имя
    for ключ in ("debtorName", "applicantName"):
        имя = sanitize_file_name(data.get(ключ))
        if имя:
            return имя
    поля = data.get("fields")
    if isinstance(поля, dict):
        for ключ in ("debtorName", "applicantName"):
            имя = sanitize_file_name(поля.get(ключ))
            if имя:
                return имя
    return ""


def archive_base_name(data: Dict[str, Any], today: Optional[date] = None) -> str:
    """«Иванов Иван Иванович 13-10-2026». Без имени должника — запасное имя с датой."""
    день = (today or date.today()).strftime("%d-%m-%Y")
    имя = debtor_display_name(data)
    return f"{имя} {день}" if имя else f"{ЗАПАСНОЕ_ИМЯ} {день}"


def archive_name_for_documents(store: Dict[str, Any], doc_ids: List[str],
                               today: Optional[date] = None) -> str:
    """Имя архива по первому документу, у которого есть данные генерации."""
    for doc_id in doc_ids or []:
        данные = (store or {}).get(doc_id, {}).get("data")
        if isinstance(данные, dict) and debtor_display_name(данные):
            return archive_base_name(данные, today)
    return archive_base_name({}, today)
