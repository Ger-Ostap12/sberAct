# SberAct - Автоматизация юридических документов

Приложение для автоматического анализа заявлений и генерации судебных актов с использованием AI/ML технологий.

## 🚀 Возможности

- **Автоматический анализ заявлений**: AI определяет тип заявления и извлекает ключевые данные
- **Генерация судебных актов**: Создание документов в форматах Word и PDF
- **Оптимизировано для Astra Linux**: Полная поддержка отечественного дистрибутива
- **Современный интерфейс**: Стильный и интуитивный UI на Material-UI
- **AI/ML интеграция**: Использование spaCy и других NLP библиотек

## 📋 Требования

### Системные требования
- **Astra Linux 1.7+** (рекомендуется)
- **Python 3.10+** (рекомендуется)
- **Node.js 18+**
- **8 GB RAM** (рекомендуется)
- **2 GB свободного места**

### Системные библиотеки (Electron для Astra Linux)
Установите необходимые системные зависимости:
```bash
sudo bash ./install-astralinux-deps.sh
```

### Python зависимости
См. `python-backend/requirements.txt`

### Node.js зависимости
- Electron
- React
- Material-UI
- TypeScript

## 🛠️ Установка на Astra Linux

### 1. Клонирование репозитория
```bash
git clone https://github.com/your-username/sberact.git
cd sberact
```

### 2. Установка системных зависимостей
```bash
# Установка системных библиотек
sudo bash ./install-astralinux-deps.sh

# Установка Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### 3. Установка зависимостей проекта
```bash
# Корневые зависимости (Electron builder и т.п.)
npm install

# Зависимости фронтенда (React/MUI/TS)
cd electron-app
npm install
cd ..

# Python-зависимости
cd python-backend
pip3 install -r requirements.txt
python3 -m spacy download ru_core_news_sm || true
cd ..
```

## 🚀 Запуск

### Режим разработки
```bash
npm run dev
```
Это запустит React-приложение на `http://localhost:3000` и Electron, а также поднимет Python backend на `http://localhost:8000`.

### Продакшн сборка
```bash
# Сборка React
cd electron-app
npm run build
cd ..

# Сборка Electron (AppImage и DEB)
npm run dist:linux
```
Сборка создаст артефакты в папке `dist/`:
- `SberAct.AppImage`
- `sberact_1.0.0_amd64.deb`

## 📦 Конфигурация сборки
Ключевые параметры заданы в корневом `package.json`:
- `asarUnpack`: распаковка `python-backend/**`
- `extraResources`: копирование `python-backend/` в ресурсы приложения
- Linux-таргеты: `AppImage` и `deb`

Python backend в продакшне запускается из распакованного ресурса: `resources/app.asar.unpacked/python-backend/app/main.py`.

## 🏗️ Архитектура
```
sberAct/
├── electron-app/          # Electron + React frontend
│   ├── src/
│   │   ├── components/    # React компоненты
│   │   ├── types.ts       # TypeScript типы
│   │   └── App.tsx        # Главный компонент
│   ├── public/            # Статические файлы (иконка и т.п.)
│   └── package.json       # Frontend зависимости
├── python-backend/        # Python backend (FastAPI)
│   ├── app/
│   │   ├── main.py        # FastAPI приложение
│   │   └── services/      # Бизнес-логика
│   └── requirements.txt   # Python зависимости
├── install-astralinux-deps.sh  # Установка системных либ для Astra Linux
├── install.sh             # Скрипт установки зависимостей
└── package.json           # Electron builder и скрипты
```

## 🔧 Настройки для Astra Linux

### Electron
```javascript
// electron-app/main.js
// Продакшн: backend запускается из resources/app.asar.unpacked/python-backend/app/main.py
// Поддержка python3 для Astra Linux
```

### Backend
- Порт: `8000`
- Healthcheck: `/health`
- Поддержка виртуальных окружений Python

## 🐛 Отладка

### Логи Electron
```bash
npm run dev
```

### Логи Python backend
```bash
cd python-backend
python3 -m uvicorn app.main:app --reload --log-level debug
```

## 📊 Тестирование и сборка
```bash
# Frontend тесты
cd electron-app
npm test

# Backend тесты
cd ../python-backend
python3 -m pytest

# Полная сборка (Astra Linux)
cd ..
npm run build
npm run dist:linux
```

## 🔒 Безопасность для Astra Linux

- **Сертификация**: Совместимость с требованиями ФСТЭК
- **Изоляция процессов**: Electron и Python работают отдельно
- **Валидация данных**: Проверка всех входных данных
- **Логирование**: Отслеживание всех операций

## 📞 Поддержка
- Документация API: `http://localhost:8000/docs`
- Совместимость с Astra Linux 1.7+

## 📄 Лицензия
MIT License - см. файл `LICENSE` для подробностей.
