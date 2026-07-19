# -*- coding: utf-8 -*-
"""Разбивка/сборка бинарных файлов эмбеддинг-модели под лимит GitHub (100 МБ/файл).

`model.safetensors` (~470 МБ) в git не помещается целиком — режем на куски по
`_CHUNK_SIZE` в подпапку `<файл>.parts/part-000`, `part-001`, ... + `manifest.json`
(имя исходного файла, его размер, sha256, число кусков) — сборка её сверяет,
чтобы битая/неполная скачка кусков не подсунула модель молча.

Использование:
    venv/Scripts/python.exe tools/split_model.py split <путь к файлу>
    venv/Scripts/python.exe tools/split_model.py assemble <путь к файлу>

`assemble` вызывается автоматически из `semantic_classifier._ensure_model()`
при первом запуске после `git clone`/распаковки дистрибутива — здесь как CLI
для ручной проверки/переупаковки при обновлении модели.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

_CHUNK_SIZE = 90 * 1024 * 1024  # 90 МБ — с запасом под лимит GitHub 100 МБ/файл


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def split(file_path: str) -> None:
    if not os.path.isfile(file_path):
        raise SystemExit(f"Файл не найден: {file_path}")
    parts_dir = file_path + ".parts"
    os.makedirs(parts_dir, exist_ok=True)
    for old in os.listdir(parts_dir):
        os.remove(os.path.join(parts_dir, old))

    total_size = os.path.getsize(file_path)
    sha256 = _sha256_file(file_path)

    part_count = 0
    with open(file_path, "rb") as src:
        while True:
            chunk = src.read(_CHUNK_SIZE)
            if not chunk:
                break
            part_path = os.path.join(parts_dir, f"part-{part_count:03d}")
            with open(part_path, "wb") as dst:
                dst.write(chunk)
            part_count += 1

    manifest = {
        "source_name": os.path.basename(file_path),
        "size": total_size,
        "sha256": sha256,
        "part_count": part_count,
        "chunk_size": _CHUNK_SIZE,
    }
    with open(os.path.join(parts_dir, "manifest.json"), "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2)

    print(f"Разбито: {file_path} ({total_size:,} байт) -> {part_count} кусков в {parts_dir}")
    print(f"sha256: {sha256}")


def assemble(file_path: str) -> bool:
    """Собирает `file_path` из `<file_path>.parts/`, если сам файл отсутствует
    или не проходит sha256-сверку. True — файл на диске и годен к использованию.
    """
    parts_dir = file_path + ".parts"
    manifest_path = os.path.join(parts_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return os.path.isfile(file_path)  # нечем собрать — как есть

    with open(manifest_path, "r", encoding="utf-8") as mf:
        manifest = json.load(mf)

    if os.path.isfile(file_path) and os.path.getsize(file_path) == manifest["size"]:
        if _sha256_file(file_path) == manifest["sha256"]:
            return True  # уже собран и цел

    tmp_path = file_path + ".tmp"
    with open(tmp_path, "wb") as dst:
        for i in range(manifest["part_count"]):
            part_path = os.path.join(parts_dir, f"part-{i:03d}")
            if not os.path.isfile(part_path):
                dst.close()
                os.remove(tmp_path)
                raise FileNotFoundError(f"Не хватает куска модели: {part_path}")
            with open(part_path, "rb") as src:
                dst.write(src.read())

    if _sha256_file(tmp_path) != manifest["sha256"]:
        os.remove(tmp_path)
        raise ValueError(f"Собранный файл не прошёл sha256-сверку: {file_path}")

    os.replace(tmp_path, file_path)
    return True


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("split", "assemble"):
        print(__doc__)
        return 1
    action, file_path = sys.argv[1], sys.argv[2]
    if action == "split":
        split(file_path)
    else:
        ok = assemble(file_path)
        print("OK" if ok else "Файл отсутствует и нечем собрать")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
