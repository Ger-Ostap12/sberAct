# Linux-окружение OCR-конвертера: relocatable Python (pyruntime) + зависимости
# (torch-CPU/docling/llama/pytesseract) + код конвертера. Модели (~4.6 ГБ,
# платформо-независимые) СЮДА НЕ входят — едут отдельно и переиспользуются из
# Windows-конвертера. tesseract на Linux — системный (README, установка на
# целевой машине), тут не бандлим.
#
# Симлинки (pyruntime, site-packages) нельзя вынести на Windows-ФС напрямую,
# поэтому на выходе — .tar.gz, который install-linux.sh распакует на Linux.
#
# База debian:buster (glibc 2.28 = Astra 1.7). relocatable CPython от
# python-build-standalone запускается без системного Python на любой цели.
#
# Сборка (из корня проекта):
#   docker build -f docker/converter-linux/Dockerfile -t sberact-converter-linux .
# Извлечение tar — scripts/build-converter-linux.ps1.

# --- Стадия tess: вытаскиваем tesseract 5 + его библиотеки + языки ---
# bookworm даёт tesseract 5.x (buster — только 4). Бинарь и .so из bookworm
# (glibc 2.36) запускаются на Ubuntu 24.04. Обёртка изолирует их LD_LIBRARY_PATH,
# поэтому на python-процесс (relocatable) они не влияют.
FROM debian:bookworm-slim AS tess
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng tesseract-ocr-osd \
 && mkdir -p /tess-out/bin /tess-out/lib /tess-out/tessdata \
 && cp /usr/bin/tesseract /tess-out/bin/tesseract.real \
 && ldd /usr/bin/tesseract | awk '/=>/{print $3}' | while read -r lib; do \
      b=$(basename "$lib"); \
      case "$b" in \
        libc.so*|libm.so*|libpthread.so*|libdl.so*|librt.so*|ld-linux*|libresolv.so*|libgcc_s.so*) ;; \
        *) cp -Lv "$lib" /tess-out/lib/ ;; \
      esac; \
    done \
 && for L in rus eng osd; do \
      f=$(find /usr/share -name "$L.traineddata" 2>/dev/null | head -1); \
      [ -n "$f" ] && cp "$f" /tess-out/tessdata/; \
    done \
 && printf '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexport LD_LIBRARY_PATH="$HERE/../lib:$LD_LIBRARY_PATH"\nexport TESSDATA_PREFIX="$HERE/../tessdata"\nexec "$HERE/tesseract.real" "$@"\n' > /tess-out/bin/tesseract \
 && chmod +x /tess-out/bin/tesseract

# --- Основная стадия: окружение конвертера ---
FROM debian:buster

RUN printf 'deb http://archive.debian.org/debian buster main\ndeb http://archive.debian.org/debian-security buster/updates main\n' > /etc/apt/sources.list \
 && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no-check-valid \
 && apt-get update && apt-get install -y --no-install-recommends \
      wget ca-certificates xz-utils build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# Итоговый пейлоад собираем в /build/out/converter
RUN mkdir -p /build/out/converter

# Relocatable CPython 3.12 (python-build-standalone) -> pyruntime.
# install_only-вариант самодостаточен и переносим.
ARG PBS_TAG=20241016
ARG PBS_VER=3.12.7
RUN wget -q "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PBS_VER}+${PBS_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz" -O /tmp/pbs.tgz \
 && tar xf /tmp/pbs.tgz -C /tmp \
 && mv /tmp/python /build/out/converter/pyruntime \
 && rm /tmp/pbs.tgz

ENV PYRUN=/build/out/converter/pyruntime/bin/python
ENV SITE=/build/out/converter/.venv/lib/python3.12/site-packages

# Зависимости: lock минус pywin32 (Windows-only), CPU-индексы torch/llama.
# Ставим в --target site-packages — конвертер грузит их через PYTHONPATH
# (см. main.py _converter_env / main.js), venv-активация не нужна.
COPY converter/requirements-lock.txt /build/requirements-lock.txt
RUN grep -viE '^pywin32' /build/requirements-lock.txt > /build/req-linux.txt \
 && "$PYRUN" -m pip install --no-cache-dir --upgrade pip \
 && mkdir -p "$SITE" \
 && "$PYRUN" -m pip install --no-cache-dir --target "$SITE" -r /build/req-linux.txt \
      --extra-index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# Код конвертера (context уже без .venv/pyruntime/models/vendor — см. .dockerignore).
COPY converter/ /build/out/converter/
# Наш launcher (в проде исходников backend нет) — канонический из python-backend.
COPY python-backend/app/run_converter.py /build/out/converter/run_converter.py

# Вшитый tesseract 5 (bin/tesseract — обёртка, tesseract.real — бинарь, lib/, tessdata/).
# run_converter.py кладёт vendor-linux/tesseract/bin в начало PATH на Linux.
COPY --from=tess /tess-out /build/out/converter/vendor-linux/tesseract

# Упаковка с сохранением симлинков.
RUN mkdir -p /out \
 && tar -czf /out/converter-linux.tar.gz -C /build/out converter \
 && ls -la /out && du -sh /build/out/converter
