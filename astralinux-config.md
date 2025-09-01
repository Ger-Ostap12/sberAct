# Конфигурация Astra Linux для SberAct

## Системные требования

### Минимальные требования
- **Astra Linux 1.7+** (рекомендуется 1.8+)
- **RAM**: 8 ГБ (минимум 4 ГБ)
- **Диск**: 20 ГБ свободного места
- **Процессор**: 2 ядра (рекомендуется 4+)

### Рекомендуемые настройки
- **SELinux**: permissive или disabled для разработки
- **Firewall**: разрешить порты 3000 и 8000
- **Пользователь**: обычный пользователь с sudo правами

## Установка зависимостей

### 1. Системные пакеты
```bash
# Обновление системы
sudo apt update && sudo apt upgrade

# Установка базовых пакетов
sudo apt install -y \
  python3 python3-pip python3-venv python3-dev \
  build-essential git curl wget \
  ca-certificates
```

### 2. Зависимости для Electron
```bash
# Установка библиотек для GUI
sudo apt install -y \
  libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 \
  libnss3 libcups2 libxss1 libxrandr2 libasound2 libatk1.0-0 libpangocairo-1.0-0 \
  libgtk-3-0 libdrm2 libgbm1 xvfb xauth \
  libxkbcommon0 libxshmfence1 \
  libappindicator3-1 libindicator3-7
```

### 3. Node.js
```bash
# Добавление репозитория NodeSource
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -

# Установка Node.js
sudo apt-get install -y nodejs

# Проверка установки
node --version
npm --version
```

## Настройка безопасности

### SELinux
```bash
# Проверка статуса SELinux
sestatus

# Временное отключение для разработки
sudo setenforce 0

# Постоянное отключение (только для разработки!)
sudo sed -i 's/SELINUX=enforcing/SELINUX=disabled/' /etc/selinux/config
```

### Firewall
```bash
# Разрешение портов для разработки
sudo ufw allow 3000
sudo ufw allow 8000

# Проверка статуса
sudo ufw status
```

### Права пользователя
```bash
# Добавление пользователя в группу sudo
sudo usermod -aG sudo $USER

# Перезагрузка для применения изменений
sudo reboot
```

## Установка проекта

### 1. Клонирование
```bash
git clone https://github.com/your-username/sberact.git
cd sberact
```

### 2. Автоматическая установка
```bash
# Запуск полного скрипта установки
sudo bash ./install-astralinux.sh
```

### 3. Ручная установка
```bash
# Системные зависимости
sudo bash ./install-astralinux-deps.sh

# Node.js зависимости
npm install

# React зависимости
cd electron-app && npm install && cd ..

# Python зависимости с виртуальным окружением
cd python-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download ru_core_news_sm
deactivate
cd ..
```

## Запуск и тестирование

### 1. Запуск в режиме разработки
```bash
npm run dev
```

### 2. Проверка работы
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000/health
- **API Docs**: http://localhost:8000/docs

### 3. Сборка дистрибутива
```bash
# Сборка React
cd electron-app && npm run build && cd ..

# Сборка Electron
npm run dist:linux
```

## Решение проблем

### Проблема: Electron не запускается
```bash
# Проверка зависимостей
ldd /usr/bin/electron

# Установка недостающих библиотек
sudo apt install -y libgtk-3-0 libnss3 libxss1 libasound2
```

### Проблема: Python backend не запускается
```bash
# Проверка виртуального окружения
cd python-backend
source venv/bin/activate
python -c "import fastapi; print('OK')"
deactivate
```

### Проблема: Порт занят
```bash
# Поиск процесса
sudo netstat -tulpn | grep :8000
sudo netstat -tulpn | grep :3000

# Остановка процесса
sudo kill -9 <PID>
```

### Проблема: Права доступа
```bash
# Изменение прав на папку проекта
sudo chown -R $USER:$USER /path/to/sberact
chmod -R 755 /path/to/sberact
```

## Оптимизация производительности

### 1. Настройка Node.js
```bash
# Увеличение лимита памяти
export NODE_OPTIONS="--max-old-space-size=4096"
```

### 2. Настройка Python
```bash
# Оптимизация pip
pip config set global.cache-dir ~/.cache/pip
```

### 3. Мониторинг ресурсов
```bash
# Мониторинг использования ресурсов
htop
iotop
```

## Резервное копирование

### 1. Создание бэкапа
```bash
# Создание архива проекта
tar -czf sberact-backup-$(date +%Y%m%d).tar.gz sberact/

# Создание бэкапа виртуального окружения
cd sberact/python-backend
tar -czf venv-backup-$(date +%Y%m%d).tar.gz venv/
```

### 2. Восстановление
```bash
# Восстановление проекта
tar -xzf sberact-backup-YYYYMMDD.tar.gz

# Восстановление виртуального окружения
cd sberact/python-backend
tar -xzf venv-backup-YYYYMMDD.tar.gz
```

## Поддержка

При возникновении проблем:
1. Проверьте логи: `npm run dev`
2. Проверьте статус сервисов: `systemctl status`
3. Проверьте права доступа: `ls -la`
4. Обратитесь к документации Astra Linux
