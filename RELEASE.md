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

### Если на системном диске мало места

`release\converter` весит ~3–6 ГБ. Обе команды умеют работать с другого диска:
```
powershell -File scripts\stage-usb.ps1 -Destination "D:\SberAct-dist\converter"
powershell -File scripts\build-update.ps1 -BaselineOnly -ConverterDir "D:\SberAct-dist\converter"
```
Эталон (`converter-manifest.baseline.json`) ляжет рядом — в `D:\SberAct-dist\`.

### Если сборочная машина не та, где делали `.venv` конвертера

`pack:converter` берёт базовый Python из `converter\.venv\pyvenv.cfg`, а там
записан путь машины, где venv создавали. На другом ПК укажи свой Python явно:
```
powershell -File scripts\assemble-converter.ps1 -BasePython "C:\Users\<ты>\AppData\Local\Programs\Python\Python312"
```
Нужен **Python 3.12 x64**; скрипт сам проверит версию и разрядность, а в конце
убедится, что собранный `pyruntime` действительно импортирует torch/llama-cpp.

### Проверка перед раздачей — обязательна

`stage-usb.ps1` теперь сам сверяет собранную папку с исходной (состав + объём) и
падает, если копия оборвалась. **Не игнорируй его ошибку** — именно тихо
неполная папка `converter\` даёт у пользователя «Конвертер не найден в …».
После копирования на флешку сверь размер глазами: папка `converter\` на флешке
должна весить столько же, сколько `release\converter` (±0).

## 1. Первая установка (новый ПК)

Что кладём на флешку (в ОДНУ папку):
```
SberAct-Setup-2.0.1.exe        (из папки release)
converter.zip                  (архив конвертера, ~2-3 ГБ)
```
Пользователь запускает `SberAct-Setup-2.0.1.exe` → обычная установка. Установщик
сам распакует конвертер. На рабочем столе и в меню — ярлык.

> **Почему архив, а не папка.** Конвертер — это ~37 000 файлов. На флешке (exFAT)
> они пишутся со скоростью ~0.14 МБ/с (часы!), а любой обрыв оставляет
> полупустую папку, которую установщик молча принимал за целую — пользователь
> узнавал об этом только при первой конвертации («Конвертер не найден»). Один
> архив пишется последовательно (на порядок быстрее), несёт CRC на каждый файл и
> «наполовину установленным» быть не может.
>
> Собрать архив: `npm run stage:converter -- -Zip` (или
> `powershell -File scripts\stage-usb.ps1 -Destination "D:\SberAct-dist\converter" -Zip`).
>
> Старый формат — папка `converter\` рядом с exe — по-прежнему поддерживается
> установщиком, менять уже нарезанные флешки не обязательно.

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

### Одной командой (обычный путь)

```
npm run dist:linux -- -Destination F:\
```

Это Linux-аналог `dist:win`: фронт → AppImage в Docker → конвертер в Docker →
модели → запись комплекта на носитель → **перечитывание записанного мимо кэша
ОС** и сверка хешей (`scripts/build-dist-linux.ps1`). На носитель кладутся
AppImage, `converter-linux.tar.gz`, `models\`, `install-linux.sh`,
`Readme-linux.txt` и `SHA256SUMS`.

Проверка мимо кэша — не формальность: `Get-FileHash` сразу после записи читает
из кэша Windows и подтверждает целостность даже на неисправной флешке (02.08 на
этом потерян день). Скрипт читает с `FILE_FLAG_NO_BUFFERING`.

Ключи: `-SkipApp` и `-SkipConverter` (не пересобирать готовое), `-Staging` (где
держать промежуточные артефакты, по умолчанию `release-linux\`), `-NoVerify`.

`-Destination` может быть и обычной папкой — тогда комплект просто собирается на
диск (`-Destination D:\SberAct-linux`).

### По шагам (когда нужен только один артефакт)

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
   robocopy "converter\models" "release-linux\models" /E /XF *.part* /NFL /NDL
   ```

## 1. Первая установка (новый ПК)

На флешку — 4 объекта (при сборке через `npm run dist:linux` они уже там,
вместе с `Readme-linux.txt` и `SHA256SUMS`):
```
SberAct-2.0.1-x86_64.AppImage      (из release-linux)
converter-linux.tar.gz             (из release-linux)
models\                            (из release-linux, ~1.4 ГБ)
install-linux.sh                   (из scripts, ОБЯЗАТЕЛЬНО с LF-переводами строк)
```
Если комплект собран не скриптом, а руками: `install-linux.sh` должен доехать с
переводами строк LF. С CRLF bash отвечает `bad interpreter: /usr/bin/env bash^M`
и не запускается (в репозитории LF закреплён `.gitattributes`).

Целостность на целевой машине проверяется одной командой:
```bash
sha256sum -c SHA256SUMS
```

У пользователя на Linux — два способа, оба ставят одно и то же:

1. **Ярлыком, без терминала**: двойной клик по «Установить SberAct». Рабочие
   столы не доверяют ярлыкам с внешних носителей, поэтому в первый раз может
   потребоваться правая кнопка → «Разрешить запуск».
2. **Одной командой** (работает всегда): открыть папку в терминале и выполнить
   ```bash
   bash install-flash.sh
   ```
   `chmod` не нужен: запуск через `bash` не требует бита исполнения, которого
   на флешке не бывает.

Обёртка `install-flash.sh` сама проверяет `SHA256SUMS`, находит AppImage и
зовёт `install-linux.sh` с нужными аргументами. Прямой вызов тоже никуда не
делся:
```bash
bash install-linux.sh SberAct-2.0.1-x86_64.AppImage converter-linux.tar.gz models
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
| Windows, установка (полная) | `SberAct-Setup-X.Y.Z.exe` + `converter.zip` (или папка `converter\`) |
| Windows, установка (урезанная) | только `SberAct-Setup-X.Y.Z.exe` |
| Windows, обновление | папка `SberAct-Update\` |
| Linux, установка (полная) | `AppImage` + `converter-linux.tar.gz` + `models\` + `install-linux.sh` |
| Linux, установка (урезанная) | `AppImage` + `install-linux.sh` |
| Linux, обновление приложения | новый `AppImage` (+ `install-linux.sh`) |
| Linux, обновление конвертера | новый `AppImage` + `converter-linux.tar.gz` + `models\` + `install-linux.sh` |
