#!/bin/bash

echo "========================================"
echo "SberAct - Сборка приложения"
echo "========================================"

echo ""
echo "[1/3] Сборка React приложения..."
cd electron-app
npm run build
if [ $? -ne 0 ]; then
    echo "Ошибка при сборке React приложения"
    exit 1
fi
cd ..

echo ""
echo "[2/3] Сборка Electron приложения..."
npm run dist:linux
if [ $? -ne 0 ]; then
    echo "Ошибка при сборке Electron приложения"
    exit 1
fi

echo ""
echo "[3/3] Создание установщиков..."
echo "Готовые файлы находятся в папке dist/"
echo "- SberAct.AppImage (портативная версия)"
echo "- sberact_1.0.0_amd64.deb (пакет для Ubuntu/Debian)"

echo ""
echo "========================================"
echo "Сборка завершена успешно!"
echo "========================================"
echo ""
