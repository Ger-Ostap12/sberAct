#!/bin/bash

# Скрипт установки SberAct Document Generator для Astra Linux
# Автор: SberAct Team
# Версия: 1.0.0

set -e

echo "=========================================="
echo "SberAct Document Generator - Установка"
echo "=========================================="

# Проверяем, что мы в Astra Linux
if ! grep -q "Astra" /etc/os-release 2>/dev/null; then
    echo "⚠️  Внимание: Этот скрипт предназначен для Astra Linux"
    echo "   Установка может не работать корректно на других дистрибутивах"
    read -p "Продолжить установку? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Проверяем права root
if [[ $EUID -ne 0 ]]; then
   echo "❌ Этот скрипт должен быть запущен с правами root"
   echo "   Используйте: sudo bash install.sh"
   exit 1
fi

echo "🔍 Проверяем системные зависимости..."

# Обновляем пакеты
apt-get update

# Устанавливаем системные зависимости
echo "📦 Устанавливаем системные зависимости..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    git \
    curl \
    wget \
    ca-certificates \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libcups2 \
    libxss1 \
    libxrandr2 \
    libasound2t64 \
    libatk1.0-0 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    xvfb \
    xauth \
    libxkbcommon0 \
    libxshmfence1 \
    libappindicator3-1 \
    libindicator3-7 \
    libnotify4 \
    libatk-bridge2.0-0

echo "✅ Системные зависимости установлены"

# Устанавливаем Node.js 18+
echo "📦 Устанавливаем Node.js 18+..."
if ! command -v node &> /dev/null || [[ $(node --version | cut -d'v' -f2 | cut -d'.' -f1) -lt 18 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y nodejs
    echo "✅ Node.js установлен"
else
    echo "✅ Node.js уже установлен: $(node --version)"
fi

# Устанавливаем npm зависимости
echo "📦 Устанавливаем npm зависимости..."
npm install

echo "📦 Устанавливаем зависимости для frontend..."
cd electron-app
npm install
cd ..

# Создаем виртуальное окружение Python
echo "🐍 Создаем виртуальное окружение Python..."
cd python-backend
python3 -m venv venv
source venv/bin/activate

# Обновляем pip
pip install --upgrade pip

# Устанавливаем Python зависимости
echo "📦 Устанавливаем Python зависимости..."
pip install -r requirements.txt

# Загружаем модель spaCy для русского языка
echo "🤖 Загружаем модель spaCy для русского языка..."
python -m spacy download ru_core_news_sm || echo "⚠️  Не удалось загрузить модель spaCy, будет использована базовая модель"

deactivate
cd ..

echo "✅ Установка завершена!"
echo ""
echo "🎯 Для запуска приложения используйте:"
echo "   npm run dev          # Режим разработки"
echo "   npm run dist:linux   # Сборка для Linux"
echo ""
echo "📁 Структура проекта:"
echo "   ├── electron-app/    # Frontend (React)"
echo "   ├── python-backend/  # Backend (FastAPI)"
echo "   └── dist/           # Собранное приложение"
echo ""
echo "🔧 Дополнительные настройки:"
echo "   - Убедитесь, что порт 8000 свободен для Python backend"
echo "   - Убедитесь, что порт 3000 свободен для React dev server"
echo "   - Для продакшена используйте: npm run dist:linux"
