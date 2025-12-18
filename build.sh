#!/bin/bash

# Скрипт сборки SberAct Document Generator для Linux
# Автор: SberAct Team
# Версия: 1.0.0

echo "=========================================="
echo "SberAct Document Generator - Сборка"
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

# Собираем React приложение
echo "🔨 Собираем React приложение..."
cd electron-app
npm run build
cd ..

# Проверяем, что сборка прошла успешно
if [ ! -d "electron-app/build" ]; then
    echo "❌ Ошибка при сборке React приложения"
    exit 1
fi

echo "✅ React приложение собрано"

# Собираем Electron приложение для Linux
echo "🔨 Собираем Electron приложение для Linux..."
npm run dist:linux

# Проверяем результат сборки
if [ ! -d "dist" ]; then
    echo "❌ Ошибка при сборке Electron приложения"
    exit 1
fi

echo "✅ Сборка завершена успешно!"
echo ""
echo "📁 Результат сборки находится в папке: dist/"
echo ""

# Показываем содержимое папки dist
echo "📋 Содержимое папки dist/:"
ls -la dist/

echo ""
echo "🎯 Для установки на целевую систему:"
echo "   1. Скопируйте файл .AppImage на целевой компьютер"
echo "   2. Сделайте файл исполняемым: chmod +x filename.AppImage"
echo "   3. Запустите: ./filename.AppImage"
echo ""
echo "🔧 Дополнительные опции сборки:"
echo "   - npm run dist:linux -- --publish=never  # Только сборка, без публикации"
echo "   - npm run dist:linux -- --arm64         # Сборка для ARM64"
echo "   - npm run dist:linux -- --x64           # Сборка для x64"
