# Установка и обновления SberAct

Инструкция: как выпускать приложение под Windows и Linux и как
делать обновления. Всё работает **с флешки, без интернета**.

---

## Коротко: две разные вещи

| | Что это | Когда |
|---|---|---|
| **Установка** | полный пакет с конвертером (~6 ГБ) | один раз на новый ПК |
| **Обновление** | только изменения | когда вышла новая версия, без переустановки |

Конвертер (OCR, ~6 ГБ) при обновлениях **не переустанавливается** — экономим время.

---

## Откуда собираем

- Весь код сначала вливается в ветку **`release`**, там проверяется.
- Проверенное уходит в **`main`**.
- **Все сборки и обновления делаем ТОЛЬКО с `main`.**

Перед любой сборкой:
```
git checkout main
git pull
```
Всё, что описано ниже, выполняется из корня проекта в PowerShell.

---

## Правила версий (общее для Win и Linux)

- Версия указана в ДВУХ файлах: `package.json` и `electron-app/package.json`.
- Перед новым релизом **поднимай версию** (напр. `2.0.1` → `2.0.2`), в обоих файлах одинаково.
- Версия обязана расти — иначе обновление «не увидится».
- Туда же, при подъёме версии, добавь строку в `CHANGELOG.md` (сверху) —
  чтобы по номеру было понятно, что в релизе.

---

# WINDOWS

## Сборка артефактов Windows (создать папку `release`)

Одной командой из корня проекта:
```
npm run dist:win
```
Она делает всё по цепочке: собирает фронт → бэкенд (PyInstaller) → конвертер
(pyruntime) → установщик (electron-builder) → кладёт конвертер в `release\converter`.
На выходе в папке `release\`:
```
SberAct-Setup-<версия>.exe
converter\                     (~6 ГБ)
latest.yml, *.blockmap         (для обновлений)
```

По шагам (если нужно по отдельности) — то же, что внутри `dist:win`:
```
npm run build            # фронт
npm run pack:backend     # бэкенд
npm run pack:converter   # конвертер (pyruntime)
npx electron-builder --win
npm run stage:converter  # конвертер -> release\converter
```

> Первый раз перед сборкой подними версию в `package.json` и
> `electron-app/package.json` (см. «Правила версий»).

## 1. Первая установка (новый ПК)

Что кладём на флешку (в ОДНУ папку):
```
SberAct-Setup-2.0.1.exe        (из папки release)
converter\                     (папка целиком, из release, ~6 ГБ)
```
Пользователь запускает `SberAct-Setup-2.0.1.exe` → обычная установка. Конвертер
копируется автоматически. На рабочем столе и в меню — ярлык.

## 2. Обновление приложения (анализ/генерация/интерфейс)

1. `git checkout main` и подними версию в двух package.json.
2. Собери:
   ```
   npm run build
   npm run pack:backend
   npx electron-builder --win
   ```
3. Собери папку обновления:
   ```
   npm run build:update
   ```
4. Скопируй на флешку папку **`release\SberAct-Update`**.
5. У пользователя: открыть приложение → значок обновления (⭱ в шапке) →
   «Выбрать папку…» → `SberAct-Update` на флешке → «Установить и перезапустить».

Конвертер при этом сохраняется.

## 3. Обновление конвертера

1. Подтяни новую версию конвертера:
   ```
   git submodule update --remote converter
   npm run pack:converter
   npm run stage:converter
   ```
2. Собери дельту (скопируются только изменённые файлы конвертера):
   ```
   npm run build:update -- -IncludeConverter
   ```
3. Скопируй `release\SberAct-Update` на флешку.
4. У пользователя: значок ⭱ → «Установить». Докопируется только изменённое.

> **Важно:** папку `release` между релизами конвертера НЕ УДАЛЯТЬ — в ней хранится
> эталон (`converter-manifest.baseline.json`), по которому считается дельта. Если
> удалить — следующее обновление конвертера уедет целиком (6 ГБ).

---

# LINUX (Ubuntu / Astra)

Артефакты Linux собираются в Docker на твоей **Windows-машине разработчика**
(нативно с Windows не собрать). Docker Desktop должен быть запущен.

## Сборка артефактов Linux

1. `git checkout main`, подними версию в двух package.json.
2. Приложение (AppImage):
   ```
   npm run build            # фронт
   npm run build:linux      # AppImage в release-linux\ (первый раз ~30 мин)
   ```
3. Конвертер (окружение под Linux):
   ```
   npm run build:linux-converter   # converter-linux.tar.gz в release-linux\
   ```
4. Модели (один раз, потом переиспользуются):
   ```
   robocopy "converter\models" "release-linux\models" /E /NFL /NDL
   ```

## 1. Первая установка (новый ПК)

На флешку — 4 объекта:
```
SberAct-2.0.1-x86_64.AppImage      (из release-linux)
converter-linux.tar.gz             (из release-linux)
models\                            (из release-linux, ~4.6 ГБ)
install-linux.sh                   (из scripts)
```
На Linux-машине пользователя (терминал, в папке с флешки):
```bash
chmod +x install-linux.sh
./install-linux.sh SberAct-2.0.1-x86_64.AppImage converter-linux.tar.gz models
```
Появится ярлык **«SberAct Document Generator»** в меню приложений. Всё офлайн:
приложение, конвертер, tesseract и модели — внутри.

## 2. Обновление приложения (Linux)

Обновления на Linux ставятся **повторным запуском `install-linux.sh`** (кнопка ⭱
внутри приложения — только для Windows).

1. Собери новый AppImage с `main` (шаги «Сборка артефактов Linux», п.1-2).
2. На флешку — только новый `SberAct-X.Y.Z-x86_64.AppImage`.
3. У пользователя:
   ```bash
   ./install-linux.sh SberAct-2.0.2-x86_64.AppImage
   ```
   Приложение обновится, **конвертер и модели сохранятся автоматически** (передавать
   их повторно не нужно).

## 3. Обновление конвертера (Linux)

1. Обнови конвертер и пересобери окружение:
   ```
   git submodule update --remote converter
   npm run build:linux-converter
   ```
2. На флешку — новый `converter-linux.tar.gz` (и `models\`, если менялись модели).
3. У пользователя:
   ```bash
   ./install-linux.sh SberAct-2.0.2-x86_64.AppImage converter-linux.tar.gz models
   ```
   Конвертер переустановится новой версией.

Удаление на Linux:
```bash
rm -rf ~/.local/opt/SberAct ~/.local/share/applications/sberact.desktop
```

---

# БЕЗ КОНВЕРТЕРА (урезанная версия)

Если OCR-конвертер не нужен — ставится только приложение (анализ + генерация).
Легче и быстрее: без 6 ГБ конвертера и моделей. На флешке под это уже есть папки
**«Установка SberAct Windows Урезанная»** и **«Установка SberAct Linux Урезанная»**.

> В урезанной версии экран «Конвертация» выдаёт «конвертер не найден» — это
> нормально, приложение не падает, анализ и генерация работают.

## Windows (урезанная)

На флешку — ТОЛЬКО установщик, **без папки `converter\`**:
```
SberAct-Setup-2.0.1.exe
```
Пользователь запускает `.exe` → приложение ставится без конвертера. Установщик
сам видит, что папки `converter\` рядом нет, и пропускает её.

## Linux (урезанная)

На флешку — AppImage + скрипт, **без `converter-linux.tar.gz` и `models\`**:
```
SberAct-2.0.1-x86_64.AppImage
install-linux.sh
```
Установка — БЕЗ аргументов конвертера:
```bash
chmod +x install-linux.sh
./install-linux.sh SberAct-2.0.1-x86_64.AppImage
```

Обновление урезанной версии — так же, как полной (Windows — кнопка ⭱; Linux —
повторный запуск `install-linux.sh` с новым AppImage).

Из урезанной можно сделать полную позже: до-положить конвертер (Windows —
переустановить с папкой `converter\`; Linux — `./install-linux.sh <AppImage>
converter-linux.tar.gz models`).

---

## Памятка «что на флешке»

| Случай | Файлы на флешке |
|---|---|
| Windows, установка (полная) | `SberAct-Setup-X.Y.Z.exe` + `converter\` |
| Windows, установка (урезанная) | только `SberAct-Setup-X.Y.Z.exe` |
| Windows, обновление | папка `SberAct-Update\` |
| Linux, установка (полная) | `AppImage` + `converter-linux.tar.gz` + `models\` + `install-linux.sh` |
| Linux, установка (урезанная) | `AppImage` + `install-linux.sh` |
| Linux, обновление приложения | новый `AppImage` (+ `install-linux.sh`) |
| Linux, обновление конвертера | новый `AppImage` + `converter-linux.tar.gz` + `models\` + `install-linux.sh` |
