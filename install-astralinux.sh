#!/bin/bash

set -euo pipefail

echo "========================================"
echo "SberAct - Установка на Astra Linux"
echo "========================================"

# Проверка на Astra Linux
if ! grep -q "Astra" /etc/os-release; then
    echo "Внимание: Этот скрипт предназначен для Astra Linux"
    echo "Текущая система: $(cat /etc/os-release | grep PRETTY_NAME)"
    read -p "Продолжить установку? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Проверка прав root
if [[ $EUID -ne 0 ]]; then
    echo "Пожалуйста, запустите скрипт от root: sudo $0"
    exit 1
fi

echo ""
echo "[1/5] Установка системных зависимостей..."
bash ./install-astralinux-deps.sh

echo ""
echo "[2/5] Установка Node.js 18+..."
# Добавление репозитория NodeSource
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt-get install -y nodejs

# Проверка установки Node.js
if ! command -v node &> /dev/null; then
    echo "Ошибка: Node.js не установлен"
    exit 1
fi

echo "Node.js версия: $(node --version)"
echo "npm версия: $(npm --version)"

echo ""
echo "[3/5] Установка Node.js зависимостей..."
npm install
if [ $? -ne 0 ]; then
    echo "Ошибка при установке Node.js зависимостей"
    exit 1
fi

echo ""
echo "[4/5] Установка React зависимостей..."
cd electron-app
npm install
if [ $? -ne 0 ]; then
    echo "Ошибка при установке React зависимостей"
    exit 1
fi
cd ..

echo ""
echo "[5/5] Установка Python зависимостей..."
cd python-backend

# Создание виртуального окружения для Astra Linux
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей в виртуальное окружение
pip install --upgrade pip
pip install -r requirements.txt

# Установка русской модели spaCy
python -m spacy download ru_core_news_sm || true

deactivate
cd ..

echo ""
echo "========================================"
echo "Установка завершена успешно!"
echo "========================================"
echo ""
echo "Для запуска приложения выполните:"
echo "npm run dev"
echo ""
echo "Примечания для Astra Linux:"
echo "- Убедитесь, что SELinux настроен корректно"
echo "- Проверьте права доступа к портам 3000 и 8000"
echo "- При проблемах с Electron проверьте настройки безопасности"
echo ""
