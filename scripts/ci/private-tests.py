"""Запуск закрытого корпуса без вывода документов в публичные логи."""
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def report_counts(report):
    cases = list(ET.parse(report).iter("testcase"))
    if not cases:
        raise ValueError("Empty test report")
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)
    return len(cases) - failed - skipped, failed, skipped


def execute(command, report, log):
    with open(log, "wb") as output:
        child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        started = time.monotonic()
        while True:
            try:
                code = child.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                print(f"Backend checks running: {int(time.monotonic() - started)} seconds", flush=True)
    try:
        passed, failed, skipped = report_counts(report)
    except (OSError, ValueError, ET.ParseError):
        print("Backend checks failed before a valid report was produced; private output was not published.", flush=True)
        return code or 1
    print(f"Backend: {passed} passed, {failed} failed, {skipped} skipped", flush=True)
    if not passed:
        print("Backend has no successful tests; refusing a green result.", flush=True)
        return code or 1
    if code or failed:
        print("Reproduce locally with the pinned corpus for details; raw test output contains private data.", flush=True)
    return code or (1 if failed else 0)


def main():
    folder = Path(os.environ.get("RUNNER_TEMP", Path.cwd() / "temp")) / "sberact-private-tests"
    folder.mkdir(parents=True, exist_ok=True)
    report = folder / "backend.xml"
    log = folder / "backend.log"
    if report.exists() or log.exists():
        raise SystemExit("Private test output already exists")
    command = [sys.executable, "-m", "pytest", "python-backend/tests",
               "--require-golden-corpus", "-q", "--tb=short", "-p", "no:cacheprovider",
               "--junitxml=" + str(report)]
    raise SystemExit(execute(command, report, log))


if __name__ == "__main__":
    main()
