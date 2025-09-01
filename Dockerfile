# Многоэтапная сборка для оптимизации размера
FROM node:18-bullseye AS electron-builder

# Установка зависимостей для сборки Linux пакетов
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    build-essential \
    libarchive-tools \
    rpm \
    xz-utils \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Копирование package.json файлов
COPY package*.json ./
COPY electron-app/package*.json ./electron-app/

# Установка зависимостей
RUN npm ci
RUN cd electron-app && npm ci

# Копирование исходного кода
COPY . .

# Сборка React приложения
RUN cd electron-app && npm run build

# Сборка Electron приложения
RUN npm run dist:linux

# Финальный образ с Python backend (опционально)
FROM python:3.10-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование Python зависимостей
COPY python-backend/requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Установка русской языковой модели spaCy
RUN python -m spacy download ru_core_news_sm || true

# Копирование Python кода
COPY python-backend/ ./python-backend/

# Копирование собранного Electron приложения
COPY --from=electron-builder /app/dist/ ./dist/

# Создание пользователя для безопасности
RUN useradd -m -u 1000 sberact
USER sberact

# Открытие порта
EXPOSE 8000

# Запуск приложения (только backend)
CMD ["python", "-m", "uvicorn", "python-backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
