#!/bin/bash

# Скрипт запуска SberAct Document Generator
# Автор: SberAct Team
# Версия: 1.0.0

echo "=========================================="
echo "SberAct Document Generator - Запуск"
echo "=========================================="

# Проверяем, что мы в корневой директории проекта
if [ ! -f "package.json" ]; then
    echo "❌ Запустите скрипт из корневой директории проекта"
    exit 1
fi

# Проверяем наличие Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js не установлен"
    echo "   Запустите: sudo bash install.sh"
    exit 1
fi

# Проверяем версию Node.js
NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "❌ Требуется Node.js версии 18 или выше"
    echo "   Текущая версия: $(node --version)"
    echo "   Запустите: sudo bash install.sh"
    exit 1
fi

echo "✅ Node.js версии $(node --version) найден"

# Проверяем наличие Python backend
if [ ! -d "python-backend" ]; then
    echo "❌ Python backend не найден"
    echo "   Запустите: sudo bash install.sh"
    exit 1
fi

# Проверяем виртуальное окружение Python
if [ ! -d "python-backend/venv" ]; then
    echo "❌ Виртуальное окружение Python не найдено"
    echo "   Запустите: sudo bash install.sh"
    exit 1
fi

echo "✅ Python backend найден"

# Проверяем зависимости
if [ ! -d "node_modules" ]; then
    echo "📦 Устанавливаем npm зависимости..."
    npm install
fi

if [ ! -d "electron-app/node_modules" ]; then
    echo "📦 Устанавливаем зависимости для frontend..."
    cd electron-app
    npm install
    cd ..
fi

echo "✅ Зависимости проверены"

# Проверяем, что порты свободны
echo "🔍 Проверяем доступность портов..."

# Проверяем порт 8000 (Python backend)
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Порт 8000 занят. Возможно, Python backend уже запущен"
    read -p "Продолжить? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Проверяем порт 3000 (React dev server)
if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Порт 3000 занят. Возможно, React dev server уже запущен"
    read -p "Продолжить? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "✅ Порты свободны"

# Запускаем Python backend (WSL/Linux) в фоне и сообщаем Electron не запускать свой процесс
echo "🔧 Запускаем Python backend (WSL/Linux) в фоне..."
(
    set -e
    cd python-backend/app
    # Активируем Linux venv, если существует на уровень выше
    if [ -f "../venv/bin/activate" ]; then
        source ../venv/bin/activate
    elif [ -f "../../venv/bin/activate" ]; then
        # fallback: если venv создан в корне проекта (например, ./venv)
        source ../../venv/bin/activate
    fi
    # Запуск с автоперезапуском для разработки
    python main.py >/dev/null 2>&1 &
) || true

# Сообщаем Electron использовать внешний backend
export USE_EXTERNAL_BACKEND=1

echo "🚀 Запускаем SberAct Document Generator..."
echo ""
echo "📱 Приложение будет доступно по адресу: http://localhost:3000"
echo "🔧 Python backend будет доступен по адресу: http://localhost:8000"
echo ""
echo "⏹️  Для остановки нажмите Ctrl+C"
echo ""

# Запускаем в режиме разработки (Linux Node/Electron)
npm run dev
