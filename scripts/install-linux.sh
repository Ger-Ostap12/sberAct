#!/usr/bin/env bash
# Установка/обновление SberAct на Linux из AppImage (+ опционально OCR-конвертер).
#
# Распаковывает AppImage в ~/.local/opt/SberAct, ставит .desktop-ярлык. Конвертер
# (если передан) разворачивается в resources/converter вместе с моделями — туда,
# где его ждёт бэкенд. Sandbox отключён в сборке, FUSE не нужен, интернет не нужен.
#
# Первая установка (приложение + конвертер):
#   chmod +x install-linux.sh
#   ./install-linux.sh SberAct-2.0.1-x86_64.AppImage converter-linux.tar.gz models
#
# Обновление ТОЛЬКО приложения (конвертер сохраняется автоматически):
#   ./install-linux.sh SberAct-2.0.2-x86_64.AppImage
#
# Обновление конвертера (переустановит его новой версией):
#   ./install-linux.sh SberAct-2.0.2-x86_64.AppImage converter-linux.tar.gz models
#
# Удаление: rm -rf ~/.local/opt/SberAct ~/.local/share/applications/sberact.desktop

set -e

APPIMAGE="${1:-}"
CONV_TAR="${2:-}"
MODELS_DIR="${3:-}"

if [ -z "$APPIMAGE" ] || [ ! -f "$APPIMAGE" ]; then
  echo "Использование: $0 /путь/SberAct-*.AppImage [converter-linux.tar.gz] [models/]"
  exit 1
fi
APPIMAGE="$(readlink -f "$APPIMAGE")"

DEST="$HOME/.local/opt/SberAct"
APPS="$HOME/.local/share/applications"
RES="$DEST/resources"
KEEP="$DEST.converter-keep"

# Сохраняем уже установленный конвертер (перенос на том же диске — мгновенно),
# чтобы обновление приложения его не стёрло.
if [ -d "$RES/converter" ]; then
  rm -rf "$KEEP"
  mv "$RES/converter" "$KEEP"
fi

echo "[1/4] Распаковка AppImage..."
TMP="$(mktemp -d)"
# Копируем во временную папку и делаем исполняемым: на флешке (exFAT/FAT) бит
# запуска может не ставиться, а --appimage-extract требует исполняемый файл
# (FUSE при этом не нужен — это встроенная команда рантайма AppImage).
cp "$APPIMAGE" "$TMP/app.AppImage"
chmod +x "$TMP/app.AppImage"
( cd "$TMP" && ./app.AppImage --appimage-extract >/dev/null )
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$TMP/squashfs-root" "$DEST"
rm -rf "$TMP"
mkdir -p "$RES"

# --- Конвертер ---
if [ -n "$CONV_TAR" ]; then
  # Передан новый конвертер — ставим его (старую сохранённую копию выбрасываем).
  if [ ! -f "$CONV_TAR" ]; then echo "Не найден: $CONV_TAR"; exit 1; fi
  rm -rf "$KEEP"
  echo "[2/4] Разворачивание конвертера..."
  tar -xzf "$CONV_TAR" -C "$RES"          # даёт $RES/converter (pyruntime/.venv/код/tesseract)
  chmod +x "$RES/converter/pyruntime/bin/"* 2>/dev/null || true
  if [ -x "$RES/converter/vendor-linux/tesseract/bin/tesseract" ]; then
    chmod +x "$RES/converter/vendor-linux/tesseract/bin/tesseract" \
             "$RES/converter/vendor-linux/tesseract/bin/tesseract.real" 2>/dev/null || true
    echo "     tesseract вшит (офлайн)."
  fi
  if [ -n "$MODELS_DIR" ]; then
    if [ ! -d "$MODELS_DIR" ]; then echo "Не найдена папка моделей: $MODELS_DIR"; exit 1; fi
    echo "[3/4] Копирование моделей (~4.6 ГБ, может занять время)..."
    mkdir -p "$RES/converter/models"
    cp -r "$MODELS_DIR/." "$RES/converter/models/"
  else
    echo "[3/4] Модели не переданы — конвертер без моделей работать не будет."
  fi
elif [ -d "$KEEP" ]; then
  # Нового конвертера нет, но был установлен раньше — возвращаем на место.
  echo "[2/4] Конвертер сохранён от прошлой установки."
  mv "$KEEP" "$RES/converter"
  echo "[3/4] Модели сохранены."
else
  echo "[2/4] Конвертер не передан — только приложение (анализ+генерация)."
fi

# --- Ярлык ---
echo "[4/4] Ярлык в меню..."
ICON="$DEST/sberact-document-generator.png"
if [ ! -f "$ICON" ]; then
  ICON="$(find "$DEST" -path '*icons*' -name '*.png' 2>/dev/null | head -1)"
fi
mkdir -p "$APPS"
cat > "$APPS/sberact.desktop" <<EOF
[Desktop Entry]
Name=SberAct Document Generator
Comment=Генератор судебных актов
Exec=$DEST/AppRun
Icon=$ICON
Type=Application
Categories=Office;
Terminal=false
EOF
chmod +x "$APPS/sberact.desktop"
update-desktop-database "$APPS" 2>/dev/null || true

echo ""
echo "Готово. Ярлык «SberAct Document Generator» — в меню приложений."
