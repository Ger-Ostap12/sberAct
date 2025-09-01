#!/bin/bash

set -euo pipefail

echo "==> Установка системных зависимостей для Astra Linux"

if [[ $EUID -ne 0 ]]; then
  echo "Пожалуйста, запустите скрипт от root: sudo $0"
  exit 1
fi

# Обновление системы
apt-get update

# Основные пакеты для разработки
apt-get install -y \
  python3 python3-pip python3-venv python3-dev \
  build-essential \
  git curl wget \
  ca-certificates

# Зависимости для Electron (Astra Linux специфичные)
apt-get install -y \
  libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 \
  libnss3 libcups2 libxss1 libxrandr2 libasound2 libatk1.0-0 libpangocairo-1.0-0 \
  libgtk-3-0 libdrm2 libgbm1 xvfb xauth \
  libxkbcommon0 libxshmfence1 \
  libappindicator3-1 libindicator3-7

# Дополнительные пакеты для Astra Linux
apt-get install -y \
  libnotify4 \
  libxtst6 \
  libnss3 \
  libxss1 \
  libasound2 \
  libatk-bridge2.0-0 \
  libgtk-3-0 \
  libdrm2 \
  libgbm1 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  libxshmfence1

# Очистка кэша
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "==> Системные зависимости установлены."
echo "==> Теперь установите Node.js и npm:"
echo "curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -"
echo "sudo apt-get install -y nodejs"
