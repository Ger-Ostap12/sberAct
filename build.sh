#!/bin/bash
# SberAct: сборка one-file для Linux (sigma / Astra / WSL)
# npm НЕ нужен — фронтенд должен быть уже собран в electron-app/build/
#
# Минимальная структура проекта:
#   build.sh, SberAct.spec
#   python-backend/requirements.txt, python-backend/app/
#   electron-app/build/index.html, electron-app/build/static/
#   emplates/  (шаблоны .docx)
#
# Запуск: ./build.sh

set -e
cd "$(dirname "$0")"

RELEASE_VERSION="${RELEASE_VERSION:-1.0.5}"
LINUX_NAME="SberAct-linux-x64"

echo "=== SberAct: сборка (one-file, без npm) ==="

# --- Проверка структуры проекта ---
_missing=0
for path in SberAct.spec python-backend/requirements.txt python-backend/app/main.py; do
    if [[ ! -e "$path" ]]; then
        echo "Ошибка: не найден $path"
        _missing=1
    fi
done

if [[ ! -f "electron-app/build/index.html" ]]; then
    echo "Ошибка: не найден electron-app/build/index.html"
    echo ""
    echo "Соберите фронт на машине с Node.js (один раз):"
    echo "  cd electron-app && npm install && npm run build"
    echo "Скопируйте папку electron-app/build/ в этот проект и запустите ./build.sh снова."
    _missing=1
fi

if [[ ! -d "electron-app/build/static" ]]; then
    echo "Ошибка: не найден electron-app/build/static (UI не откроется в браузере)"
    _missing=1
fi

if [[ ! -d "emplates" ]]; then
    echo "Предупреждение: папка emplates/ не найдена — шаблоны не попадут в бинарник"
elif [[ -z "$(find emplates -name '*.docx' 2>/dev/null | head -1)" ]]; then
    echo "Предупреждение: в emplates/ нет .docx — проверьте шаблоны"
fi

if [[ "$_missing" -eq 1 ]]; then
    exit 1
fi

echo "Фронтенд: electron-app/build/ (готов, npm не используется)"

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "Ошибка: Python не найден. Активируйте venv: source act_venv_3.9/bin/activate"
    exit 1
fi
PYTHON=$(command -v python3 2>/dev/null || command -v python)
echo "Python: $("$PYTHON" --version) ($PYTHON)"

echo ""
echo "Установка зависимостей из python-backend/requirements.txt..."
"$PYTHON" -m pip install --upgrade pip -q 2>/dev/null || true
"$PYTHON" -m pip install -r python-backend/requirements.txt -q
"$PYTHON" -m pip install pyinstaller -q
"$PYTHON" -m spacy download ru_core_news_sm 2>/dev/null || echo "Предупреждение: $PYTHON -m spacy download ru_core_news_sm"

echo ""
echo "Запуск PyInstaller (one-file)..."
"$PYTHON" -m PyInstaller --clean --noconfirm SberAct.spec

if [[ ! -f "dist/SberAct" ]]; then
    echo "Ошибка: dist/SberAct не найден после сборки"
    exit 1
fi

echo ""
echo "Подготовка релиза (бинарник + Templates рядом)..."
mkdir -p release
cp -f "dist/SberAct" "release/${LINUX_NAME}"
chmod +x "release/${LINUX_NAME}"

# Внешние шаблоны рядом с бинарником — можно менять без пересборки
TAR_ITEMS=("${LINUX_NAME}")
if [[ -d "emplates" ]]; then
    rm -rf dist/Templates release/Templates
    mkdir -p dist/Templates release/Templates
    cp -a emplates/. dist/Templates/
    cp -a emplates/. release/Templates/
    TAR_ITEMS+=("Templates")
    echo "Шаблоны: dist/Templates/ и release/Templates/ (рядом с бинарником)"
else
    echo "Предупреждение: emplates/ нет — внешняя папка Templates не создана"
fi

tar -czf "release/SberAct-${RELEASE_VERSION}-linux-x64.tar.gz" -C release "${TAR_ITEMS[@]}"

SIZE_MB=$(du -m "release/SberAct-${RELEASE_VERSION}-linux-x64.tar.gz" | cut -f1)
echo "Архив: release/SberAct-${RELEASE_VERSION}-linux-x64.tar.gz (${SIZE_MB} MB)"

echo ""
echo "=== Готово ==="
echo "Бинарник: dist/SberAct"
if [[ -d "dist/Templates" ]]; then
    echo "Шаблоны:  dist/Templates/  (редактируйте без пересборки)"
fi
echo "Релиз:    release/SberAct-${RELEASE_VERSION}-linux-x64.tar.gz"
echo ""
echo "Запуск (откроется в браузере http://127.0.0.1:8000):"
echo "  cd dist && ./SberAct"
