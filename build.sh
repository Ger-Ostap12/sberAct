#!/bin/bash
# SberAct: сборка исполняемого файла (Linux / macOS)
# Запуск из корня проекта: ./build.sh   или   bash build.sh

set -e
cd "$(dirname "$0")"

echo "=== SberAct: сборка ==="

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "Ошибка: Python не найден. Установите Python 3."
    exit 1
fi
PYTHON=$(command -v python3 2>/dev/null || command -v python)

echo ""
echo "Сборка React фронтенда (electron-app)..."
if ! command -v npm &>/dev/null; then
    echo "Ошибка: npm не найден. Установите Node.js (с npm) и повторите."
    exit 1
fi
pushd electron-app >/dev/null
npm install
npm run build
popd >/dev/null

if [[ ! -f "electron-app/build/index.html" ]]; then
    echo "Ошибка: сборка фронтенда не создала electron-app/build/index.html"
    exit 1
fi
if [[ ! -d "electron-app/build/static" ]]; then
    echo "Предупреждение: electron-app/build/static не найден. Проверьте, что build действительно CRA-сборка."
fi

echo ""
echo "Установка зависимостей из python-backend/requirements.txt..."
"$PYTHON" -m pip install -r python-backend/requirements.txt -q
"$PYTHON" -m pip install pyinstaller -q
"$PYTHON" -m spacy download ru_core_news_sm 2>/dev/null || echo "Предупреждение: установите модель: $PYTHON -m spacy download ru_core_news_sm"

echo ""
echo "Запуск PyInstaller..."
"$PYTHON" -m PyInstaller --noconfirm SberAct.spec

echo ""
echo "=== Готово ==="
echo "Исполняемый файл и библиотеки: dist/SberAct/"
echo "Запуск: ./dist/SberAct/SberAct"
echo "Рядом положите папку Templates с шаблонами .docx"
