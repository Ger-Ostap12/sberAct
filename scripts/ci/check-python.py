"""Проверка закреплённого окружения runner без установки пакетов."""
import importlib.metadata
import pathlib
import re
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit("CI requires Python 3.12")
lock = pathlib.Path(__file__).resolve().parents[2] / "python-backend" / "requirements-ci.lock"
errors = []
for line in lock.read_text(encoding="utf-8").splitlines():
    if not line or line.startswith(("#", "--")):
        continue
    if "==" in line:
        name, expected = line.split("==", 1)
    else:
        match = re.fullmatch(r"ru-core-news-sm @ .*ru_core_news_sm-(\d+\.\d+\.\d+)-py3-none-any.whl#sha256=[a-f0-9]{64}", line)
        if not match:
            raise SystemExit("Unsupported CI requirement: " + line)
        name, expected = "ru-core-news-sm", match[1]
    try:
        actual = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        actual = "missing"
    if actual != expected:
        errors.append(f"{name}: expected {expected}, got {actual}")
if errors:
    raise SystemExit("\n".join(errors))
print("Python environment matches requirements-ci.lock")
