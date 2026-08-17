#!/usr/bin/env bash
# Установка SberAct «в один клик»: обёртка над install-linux.sh для комплекта
# на флешке. Её зовёт ярлык «Установить SberAct.desktop», лежащий рядом.
#
# Зачем отдельный файл: файловый менеджер запускает ярлык с рабочим каталогом
# в домашней папке, а не там, где лежит комплект. Ярлык умеет лишь передать
# сюда путь, всё остальное (поиск AppImage, проверка целостности, вызов
# установщика, пауза в конце) делается здесь.
#
# Можно запускать и руками:
#   bash install-flash.sh
# Бит исполнения не нужен: на флешке (NTFS/exFAT) его всё равно не бывает.

set -u

HERE="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
if [ -z "$HERE" ] || [ ! -d "$HERE" ]; then
  echo "Не удалось определить папку с комплектом."
  exit 1
fi
cd "$HERE" || exit 1

# Терминал, открытый ярлыком, закрывается вместе с процессом — без паузы
# пользователь не увидит ни ошибки, ни «Готово».
pause_exit() {
  echo
  printf 'Нажмите Enter, чтобы закрыть окно... '
  read -r _ || true
  exit "${1:-0}"
}

echo "SberAct — установка из папки:"
echo "  $HERE"
echo

APPIMAGE="$(ls -1 SberAct-*.AppImage 2>/dev/null | head -1)"
if [ -z "$APPIMAGE" ]; then
  echo "ОШИБКА: рядом нет файла SberAct-*.AppImage."
  echo "Запускайте скрипт из папки с комплектом (там же Readme-linux.txt)."
  pause_exit 1
fi
if [ ! -f install-linux.sh ]; then
  echo "ОШИБКА: рядом нет install-linux.sh — комплект неполный."
  pause_exit 1
fi

# Проверка целостности до установки: битый носитель обязан отсеяться здесь, а
# не всплыть при первой конвертации у пользователя.
if [ -f SHA256SUMS ] && command -v sha256sum >/dev/null 2>&1; then
  echo "Проверка целостности комплекта (2-3 минуты)..."
  if ! sha256sum -c SHA256SUMS; then
    echo
    echo "ОШИБКА: файлы повреждены — комплект доехал неполностью."
    echo "Перезапишите флешку и повторите; устанавливать такой комплект нельзя."
    pause_exit 1
  fi
  echo "Целостность в порядке."
  echo
fi

# Конвертер и модели необязательны: без них ставится «урезанная» версия
# (анализ и генерация работают, экран конвертации — нет).
ARGS=("$APPIMAGE")
if [ -f converter-linux.tar.gz ]; then
  ARGS+=("converter-linux.tar.gz")
  if [ -d models ]; then
    ARGS+=("models")
  else
    echo "ВНИМАНИЕ: папки models рядом нет — конвертер встанет без моделей."
  fi
else
  echo "ВНИМАНИЕ: converter-linux.tar.gz рядом нет — ставим только приложение."
fi
echo

if bash ./install-linux.sh "${ARGS[@]}"; then
  echo
  echo "Установка завершена. Ярлык «SberAct Document Generator» — в меню приложений."
  pause_exit 0
else
  code=$?
  echo
  echo "Установка прервана с ошибкой (код $code)."
  pause_exit "$code"
fi
