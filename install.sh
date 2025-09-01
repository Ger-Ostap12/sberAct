#!/bin/bash

echo "========================================"
echo "SberAct - Установка зависимостей"
echo "========================================"

echo ""
echo "[1/4] Установка Node.js зависимостей..."
npm install
if [ $? -ne 0 ]; then
    echo "Ошибка при установке Node.js зависимостей"
    exit 1
fi

echo ""
echo "[2/4] Установка React зависимостей..."
cd electron-app
npm install
if [ $? -ne 0 ]; then
    echo "Ошибка при установке React зависимостей"
    exit 1
fi
cd ..

echo ""
echo "[3/4] Установка Python зависимостей..."
cd python-backend
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Ошибка при установке Python зависимостей"
    exit 1
fi

echo ""
echo "[4/4] Установка русской языковой модели spaCy..."
python3 -m spacy download ru_core_news_sm
if [ $? -ne 0 ]; then
    echo "Предупреждение: Не удалось установить русскую модель spaCy"
    echo "Приложение будет работать с базовой моделью"
fi

cd ..

echo ""
echo "========================================"
echo "Установка завершена успешно!"
echo "========================================"
echo ""
echo "Для запуска приложения выполните:"
echo "npm run dev"
echo ""
