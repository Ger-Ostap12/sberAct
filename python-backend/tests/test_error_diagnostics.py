"""Отказы API объясняют причину, сохраняют код и доступны в журнале."""

import asyncio
from io import BytesIO
import json
import subprocess
import sys
from unittest.mock import Mock
import zipfile

import httpx
import pytest
from fastapi import FastAPI, HTTPException
import diagnostics


@pytest.mark.parametrize(
    "exc,code",
    [
        (PermissionError("secret"), "ACCESS_DENIED"),
        (RuntimeError("[WinError 32] locked"), "ACCESS_DENIED"),
        (FileNotFoundError("secret.docx"), "FILE_NOT_FOUND"),
        (zipfile.BadZipFile("broken"), "INVALID_DOCUMENT"),
        (MemoryError(), "OUT_OF_MEMORY"),
        (RuntimeError("unknown internals"), "UNEXPECTED_ERROR"),
    ],
)
def test_known_failures_are_friendly(exc, code):
    result = diagnostics.failure(exc, message="Не удалось сохранить документ.")
    assert result["code"] == code
    assert result["incidentId"] and result["hint"]
    assert "secret" not in result["message"] and "internals" not in result["message"]


@pytest.mark.parametrize(
    "output,options,code",
    [
        ("ModuleNotFoundError: No module named 'docling'", {}, "CONVERTER_DEPENDENCY_MISSING"),
        ("ImportError: DLL load failed [WinError 126]", {}, "CONVERTER_LIBRARY_MISSING"),
        ("OSError: address already in use", {}, "CONVERTER_PORT_IN_USE"),
        ("Permission denied", {}, "CONVERTER_ACCESS_DENIED"),
        ("", {"missing": True}, "CONVERTER_NOT_INSTALLED"),
        ("no output", {"timeout": True}, "CONVERTER_START_TIMEOUT"),
        ("Killed", {"exit_code": 137}, "CONVERTER_START_FAILED"),
        ("MemoryError:", {}, "CONVERTER_OUT_OF_MEMORY"),
        ("FileNotFoundError: python", {}, "CONVERTER_FILE_MISSING"),
    ],
)
def test_startup_reason_uses_evidence_not_exit_code_guess(output, options, code):
    result = diagnostics.startup_failure(output, **options)
    assert not result["ok"] and result["code"] == code
    assert result["hint"] and result["incidentId"]
    assert "ModuleNotFoundError" not in result["error"]


def test_process_output_is_drained_and_bounded():
    process = Mock(stdout=BytesIO(("я" * 40000).encode("utf-8")))
    capture = diagnostics.ProcessOutput(process)
    text = capture.output(finished=True)
    assert len(text) == 32768
    assert "\ufffd" not in text


def test_journal_redacts_and_bounds():
    assert "123456789012" not in diagnostics.redact("ИНН 123456789012")
    assert "Ароян" not in diagnostics.redact("Должник Ароян Ваче Рушани")
    assert diagnostics.redact("debtorName: Иванов") == "[содержимое заявления скрыто]"
    for n in range(510):
        diagnostics.event("test", str(n), level="info")
    assert len(diagnostics.snapshot()) == 500


def test_api_preserves_expected_status_and_hides_unknown_details(tmp_path):
    app = FastAPI()
    diagnostics.install(app, tmp_path)

    @app.get("/expected")
    async def expected():
        raise HTTPException(404, "Документ не найден")

    @app.get("/failure")
    async def broken():
        raise RuntimeError("internal secret")

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            expected = await client.get("/expected", headers={"X-Request-ID": "test-request-123"})
            assert expected.status_code == 404
            assert expected.json()["detail"]["message"] == "Документ не найден"
            assert expected.json()["detail"]["incidentId"] == expected.headers["X-Request-ID"] == "test-request-123"
            broken = await client.get("/failure")
            assert broken.status_code == 500
            body = broken.json()["detail"]
            assert body["code"] == "UNEXPECTED_ERROR"
            assert "internal secret" not in json.dumps(body)
            report = (await client.get("/diagnostics")).json()
            assert any(
                e["incidentId"] == body["incidentId"] and "internal secret" in e["message"] for e in report["events"]
            )

    asyncio.run(run())


@pytest.fixture
def backend(monkeypatch, tmp_path):
    monkeypatch.setenv("SBERACT_DATA_DIR", str(tmp_path))
    import main

    monkeypatch.setattr(main, "_converter_process", None)
    monkeypatch.setattr(main, "_converter_start_lock", None)
    return main


def test_real_api_missing_template_and_download_do_not_become_500(backend, monkeypatch, tmp_path):
    fake = Mock()
    fake.generate.return_value = {
        "success": False,
        "error": "missing",
        "error_code": "templates_unavailable",
        "unresolved_act_ids": ["acceptance_definition"],
    }
    fake._TREE_ACT_LABELS = {"acceptance_definition": ("acceptance", "Определение о принятии")}
    fake.generated_dir = tmp_path
    monkeypatch.setattr(backend, "document_generator", fake)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://test") as client:
            response = await client.post(
                "/generate-document",
                json={"template_type": "x", "data": {"selectedEntityType": "ip", "selectedApplicationKind": "other"}},
            )
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "TEMPLATES_UNAVAILABLE"
            assert "Определение о принятии" in response.json()["detail"]["message"]
            assert "acceptance_definition" not in response.json()["detail"]["message"]
            assert "ИП" in response.json()["detail"]["message"]
            response = await client.get("/download-document/missing")
            assert response.status_code == 404, response.text
            for error, code in [
                (PermissionError("native denied"), "ACCESS_DENIED"),
                (RuntimeError("internal generator failure"), "UNEXPECTED_ERROR"),
            ]:
                fake.generate.side_effect = error
                failed = await client.post("/generate-document", json={"template_type": "x", "data": {"a": 1}})
                assert failed.status_code == 500
                assert failed.json()["detail"]["code"] == code
                assert failed.json()["detail"]["incidentId"] == failed.headers["X-Request-ID"]
                assert str(error) not in failed.text
            fake.generate.side_effect = None
            invalid = await client.post("/generate-document", json={"template_type": "x", "data": "invalid"})
            assert invalid.status_code == 422
            response = await client.post("/generate-document", json={})
            assert response.status_code == 400
            response = await client.post(
                "/analyze-document", files={"document": ("empty.docx", b"", "application/octet-stream")}
            )
            assert response.status_code == 400, response.text
            response = await client.post(
                "/analyze-document",
                files={
                    "document": (
                        "broken.docx",
                        b"broken zip",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
            assert response.status_code == 400, response.text
            assert response.json()["detail"]["code"] == "INVALID_DOCUMENT"

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["module_missing", "timeout"])
def test_converter_start_with_actual_failing_child(backend, monkeypatch, tmp_path, mode):
    async def unhealthy():
        return False

    monkeypatch.setattr(backend, "_converter_healthy", unhealthy)
    command = [
        sys.executable,
        "-u",
        "-c",
        "raise ModuleNotFoundError(\"No module named 'docling'\")"
        if mode == "module_missing"
        else "import time;time.sleep(30)",
    ]
    monkeypatch.setattr(backend, "_converter_command", lambda: command)
    monkeypatch.setattr(backend, "CONVERTER_DIR", tmp_path)
    monkeypatch.setattr(backend, "CONVERTER_START_TIMEOUT_S", 3 if mode == "module_missing" else 0)
    processes = []
    original = subprocess.Popen

    def start(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(backend.subprocess, "Popen", start)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend.app), base_url="http://test") as client:
            response = await client.post("/converter/start")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["code"] == (
                "CONVERTER_DEPENDENCY_MISSING" if mode == "module_missing" else "CONVERTER_START_TIMEOUT"
            )
            assert body["incidentId"] == response.headers["X-Request-ID"]
            if mode == "module_missing":
                events = (await client.get("/diagnostics")).json()["events"]
                assert any("docling" in e["message"] and e["incidentId"] == body["incidentId"] for e in events)

    try:
        asyncio.run(run())
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def test_technical_field_names_in_trace_are_not_treated_as_document_payload():
    try:
        raise KeyError("debtorName")
    except KeyError as error:
        result = diagnostics.failure(error)
    record = next(e for e in reversed(diagnostics.snapshot()) if e["incidentId"] == result["incidentId"])
    assert "KeyError" in record["message"]
    assert "debtorName" in record["message"]
    assert "Traceback" in record["message"]
    text = diagnostics.redact("Traceback\nДанные для замены: debtorName: Иванов Иван Иванович\nKeyError: 'debtorName'")
    assert "Иванов" not in text
    assert "KeyError: 'debtorName'" in text
