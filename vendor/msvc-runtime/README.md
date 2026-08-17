# MSVC-рантайм для конвертера

Microsoft Visual C++ 2015-2022 Redistributable (x64), файлы взяты из
`C:\Windows\System32` машины сборки, версия 14.44.35211.0.

## Зачем это здесь

Колесо `torch` не везёт с собой системный MSVC-рантайм: в `torch\lib` лежат
только `torch_*.dll`, `c10.dll`, `libiomp5md.dll`, `uv.dll`. Питон, который мы
бандлим в `converter\pyruntime`, приносит из установщика CPython лишь
`vcruntime140.dll` и `vcruntime140_1.dll` — **`msvcp140.dll` (C++ stdlib) нет ни
там, ни там**. На машине сборки она есть в System32 вместе с Visual Studio,
поэтому дефект там не воспроизводится. На чистой Windows без VC++
Redistributable конвертер падает на импорте:

```
OSError: [WinError 126] Не найден указанный модуль.
Error loading "...\torch\lib\torch_python.dll" or one of its dependencies.
```

## Куда они попадают

`package.json` → `build.extraResources` кладёт папку в `resources\msvc-runtime`,
`scripts/installer.nsh` после установки конвертера копирует её содержимое в:

- `resources\converter\pyruntime\` — каталог `python.exe` всегда в путях поиска
  DLL, поэтому рантайм видят все пакеты (torch, llama_cpp, scipy, PIL);
- `resources\converter\.venv\Lib\site-packages\torch\lib\` — torch добавляет эту
  папку через `os.add_dll_directory` (`torch/__init__.py`), страховка на случай,
  если процесс стартовал не из `pyruntime`.

Прав администратора не требуется — в отличие от `vc_redist.x64.exe`, который
чинит систему целиком, но просит UAC. Если админ есть, правильнее поставить
редистрибутив: https://aka.ms/vs/17/release/vc_redist.x64.exe

## Обновление

Пересобрать список из System32 машины с установленным VC++ Redistributable.
Файлы обязаны быть **x64** — 32-битная DLL рядом с 64-битным процессом даёт
«Неподдерживаемое 16-разрядное приложение» (ошибка 193).
