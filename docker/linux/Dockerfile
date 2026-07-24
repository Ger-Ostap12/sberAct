# Полная Linux-сборка: Python-бэкенд (PyInstaller onedir) + упаковка в AppImage.
# Всё внутри Linux-контейнера — на Windows выносится ТОЛЬКО готовый .AppImage
# (в нём нет симлинков, поэтому docker cp на Windows-ФС не спотыкается о права,
# в отличие от сырого onedir с numpy.libs/*.so-симлинками).
#
# База debian:buster (glibc 2.28 = Astra Linux 1.7) — бинарники идут и на Astra,
# и на новые Ubuntu.
#
# Сборка (из корня проекта):
#   docker build -f docker/linux/Dockerfile -t sberact-linux .
# Извлечение AppImage — scripts/build-linux.ps1.

# ============================ Стадия 1: backend ============================
# Инструкции ИДЕНТИЧНЫ docker/backend-linux/Dockerfile — buildkit переиспользует
# уже собранные слои (компиляция Python не повторяется).
FROM debian:buster AS backend

RUN printf 'deb http://archive.debian.org/debian buster main\ndeb http://archive.debian.org/debian-security buster/updates main\n' > /etc/apt/sources.list \
 && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no-check-valid \
 && apt-get update && apt-get install -y --no-install-recommends \
      build-essential wget ca-certificates \
      zlib1g-dev libssl-dev libffi-dev libbz2-dev libreadline-dev libsqlite3-dev \
      liblzma-dev libncurses5-dev tk-dev uuid-dev \
 && rm -rf /var/lib/apt/lists/*

ARG PY=3.12.6
RUN cd /tmp \
 && wget -q https://www.python.org/ftp/python/${PY}/Python-${PY}.tgz \
 && tar xf Python-${PY}.tgz && cd Python-${PY} \
 && ./configure --enable-shared --prefix=/opt/python312 LDFLAGS=-Wl,-rpath=/opt/python312/lib \
 && make -j"$(nproc)" && make install \
 && cd / && rm -rf /tmp/Python-*
ENV PATH=/opt/python312/bin:$PATH
ENV LD_LIBRARY_PATH=/opt/python312/lib

WORKDIR /build
COPY python-backend/requirements.txt ./requirements.txt
RUN python3.12 -m venv /build/venv \
 && /build/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /build/venv/bin/pip install --no-cache-dir -r requirements.txt \
 && /build/venv/bin/pip install --no-cache-dir pyinstaller \
 && /build/venv/bin/pip install --no-cache-dir \
      https://github.com/explosion/spacy-models/releases/download/ru_core_news_sm-3.7.0/ru_core_news_sm-3.7.0-py3-none-any.whl

COPY python-backend ./python-backend
COPY SberAct.spec ./SberAct.spec
COPY Templates ./Templates
RUN /build/venv/bin/pyinstaller --noconfirm SberAct.spec \
 && test -f /build/dist/SberAct/SberAct

# ========================== Стадия 2: AppImage =============================
FROM debian:buster AS appimage

RUN printf 'deb http://archive.debian.org/debian buster main\ndeb http://archive.debian.org/debian-security buster/updates main\n' > /etc/apt/sources.list \
 && printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no-check-valid \
 && apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates wget xz-utils file \
 && rm -rf /var/lib/apt/lists/*

# Node 20 (бинарный тарбол; buster glibc 2.28 удовлетворяет требованию Node >=2.28)
ARG NODE=20.17.0
RUN wget -q https://nodejs.org/dist/v${NODE}/node-v${NODE}-linux-x64.tar.xz \
 && tar -xJf node-v${NODE}-linux-x64.tar.xz -C /opt \
 && ln -s /opt/node-v${NODE}-linux-x64/bin/node /usr/local/bin/node \
 && ln -s /opt/node-v${NODE}-linux-x64/bin/npm /usr/local/bin/npm \
 && ln -s /opt/node-v${NODE}-linux-x64/bin/npx /usr/local/bin/npx \
 && rm node-v${NODE}-linux-x64.tar.xz

# appimagetool без FUSE (в контейнере FUSE недоступен)
ENV APPIMAGE_EXTRACT_AND_RUN=1
# electron-builder не должен лезть в git/сеть за метаданными публикации
ENV CI=true

WORKDIR /work

# Сначала манифесты + установка зависимостей (кешируемый слой).
# npm install тянет linux-electron (его postinstall качает бинарь под платформу).
COPY package.json package-lock.json ./
RUN npm install --no-audit --no-fund

# Исходники Electron-приложения (готовый React-build берётся как есть).
COPY electron-app ./electron-app

# Linux-бэкенд из стадии 1 в путь, который ждёт extraResources (from: dist/SberAct).
COPY --from=backend /build/dist/SberAct ./dist/SberAct

# Сборка AppImage -> /work/release/*.AppImage
RUN npx electron-builder --linux --publish never

# Складываем ТОЛЬКО плоские артефакты в /out. release/linux-unpacked/ содержит
# симлинки (chrome-sandbox и пр.) — его на Windows-ФС тащить нельзя, а .AppImage,
# latest-linux.yml и .blockmap — обычные файлы, docker cp их вынесет без проблем.
RUN mkdir -p /out \
 && cp /work/release/*.AppImage /out/ \
 && (cp /work/release/latest-linux.yml /out/ 2>/dev/null || true) \
 && (cp /work/release/*.AppImage.blockmap /out/ 2>/dev/null || true) \
 && ls -la /out

# Артефакты в /out; извлекаются docker cp (см. build-linux.ps1).
