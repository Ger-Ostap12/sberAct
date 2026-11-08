# CI/CD SberAct на Windows

Рабочие ветки сливаются в release. В release готовятся версия и CHANGELOG.
Pull request из release в main проходит проверки; после слияния main снова
проверяется и собирается. Версия автоматически не повышается.


Все служебные папки CI размещаются внутри C:\Диск D\Сбер. Runner и снимок
данных лежат рядом с проектом, отдельно от него. В заданиях TEMP/TMP,
кэши npm, Electron и electron-builder также направляются в SberAct-CI.

## Что запускается

| Событие | Результат |
|---|---|
| Push в release | Проверки метаданных, TypeScript, frontend, диагностики, обновления, установщика и всего backend |
| PR в release | Те же проверки объединённого кода |
| PR release → main | Те же проверки; версия должна быть выше версии main |
| Push в main | Те же проверки, затем установщик и полный комплект обновления |
| Ручной запуск | Проверки выбранной ветки release/main; сборка только для main |

Workflow: [.github/workflows/windows.yml](.github/workflows/windows.yml).
Политика запуска проверяется коротким заданием GitHub; тяжёлые задания
исполняет твой Windows runner с дополнительной меткой sberact.
Исходники из внешних fork не передаются этому runner. Право менять ветки
и workflow должно оставаться у доверенных участников: runner выполняет
код репозитория под твоей учётной записью Windows.

## Однократная подготовка ПК

Runner должен работать отдельно от рабочего проекта. Пример расположения:

- C:\Диск D\Сбер\SberActRunner — приложение runner, его отдельный checkout в _work;
- C:\Диск D\Сбер\SberAct-CI\assets — локальный снимок входных данных;
- C:\Диск D\Сбер\SberAct-CI\settings.json — путь к проверенному Python;
- C:\Диск D\Сбер\SberAct-CI\artifacts — готовые сборки;
- C:\Диск D\Сбер\SberAct-CI\reports — отчёты тестов.

Нужны Git for Windows, доступ в интернет для npm/Actions, Node.js 22.21.0
(в workflow устанавливается setup-node), Windows PowerShell 5.1 и Python 3.12.
NSIS подготавливается через закреплённый electron-builder. Базовые DLL
Visual C++ берутся из vendor/msvc-runtime.

Снимок готовится из корня проверенного проекта, где уже собран релиз:

```powershell
node scripts/ci/assets.js prepare
```

Команда копирует исходные заявления из Заявления, готовый OCR из
release/converter и модели из python-backend/models. Состав сравнивается
с scripts/ci/assets.lock.json. Существующий снимок не перезаписывается.
В репозиторий попадают только сводные контрольные суммы; исходные файлы
остаются на этом ПК.

По умолчанию используется Python из текущего python-backend/venv.
Runner не устанавливает пакеты в это окружение; перед каждым запуском
сверяет его с python-backend/requirements-ci.lock. Не удаляй и не переноси
этот venv, пока путь записан в settings.json.

Можно подготовить отдельный Python 3.12 venv и установить в него пакеты:

```powershell
py -3.12 -m venv 'C:\Диск D\Сбер\SberAct-CI\backend-venv'
& 'C:\Диск D\Сбер\SberAct-CI\backend-venv\Scripts\python.exe' -m pip install -r python-backend/requirements-ci.lock
```

Затем указать его python.exe в C:\Диск D\Сбер\SberAct-CI\settings.json и проверить
scripts/ci/check-python.py через этот интерпретатор. Пути в JSON записываются
с двойными обратными слешами или с прямыми слешами.

## Регистрация runner

1. На GitHub открой репозиторий → Settings → Actions → Runners →
   New self-hosted runner → Windows → x64.
2. Выполни предложенные GitHub команды скачивания в C:\Диск D\Сбер\SberActRunner.
   Не используй для этого папку проекта или C:\Диск D\Сбер\SberAct-CI.
3. При конфигурации используй временный токен с этой страницы. Токен не
   записывай в проект и не отправляй в чат.
4. На вопрос о дополнительных labels укажи sberact. Стандартные
   self-hosted, Windows и X64 оставь. Рабочую папку оставь _work.
5. Для первого запуска выполни .\run.cmd в терминале под своей обычной
   учётной записью Windows. Статус runner на GitHub должен стать Idle.

Пока терминал runner открыт, ПК включён и не спит, он принимает задания.
Для службы Windows понадобится та же учётная запись с доступом к assets
и Python; настройку службы можно выполнить после первого успешного прогона.

## Первый запуск и защита веток

После регистрации runner самостоятельно закоммить изменения CI и отправь
их в release. Push запустит SberAct Windows. До этого серверный прогон
не считается проверенным: локальная проверка YAML не заменяет запуск Actions.

После первого успешного запуска в настройках защиты main включи:

- Require a pull request before merging;
- обязательные проверки Repository policy и Windows checks;
- актуальность ветки перед слиянием.

Аналогичные проверки можно включить для PR в release. Доступность защиты
приватных репозиториев зависит от плана GitHub. Если остаёшься единственным
разработчиком, требовать одобрение второго человека не нужно.

В main переносится только PR из release. Автоматического commit, push,
создания тегов и GitHub Release в workflow нет. Тег выпуска ставишь сам
после проверки готового комплекта.

## Где искать результат

После успешной сборки main:

```text
C:\Диск D\Сбер\SberAct-CI\artifacts\<версия>\<run-id>-<attempt>-<commit>\
```

Внутри полный комплект SberAct-Update: установщик, latest.yml, blockmap,
converter.zip, манифесты, build-info.json и отчёт проверки OCR.
Эту папку можно выбрать в приложении как источник обновления.
Для первой установки установщик и converter.zip уже находятся рядом.

Тестовые отчёты сохраняются локально в reports/<run-id>-<attempt>.
Полный OCR и исходные заявления по умолчанию не загружаются в артефакты GitHub.

Если нужен установщик в интерфейсе Actions, добавь repository variable
SBERACT_UPLOAD_INSTALLER со значением true. Загрузятся только EXE,
blockmap и latest.yml со сроком хранения семь дней; OCR остаётся локально.

При другом расположении CI-home задай repository variable SBERACT_CI_HOME.
Не направляй его внутрь checkout. Старые artifacts/reports автоматически
не удаляются; после проверки их можно переносить или удалять вручную.

## Изменение входных данных

При намеренном изменении корпуса, OCR или моделей сначала проверь их локально,
затем из проверенного проекта выполни:

```powershell
node scripts/ci/assets.js lock
```

Это обновит только контрольные суммы в assets.lock.json. После проверки
изменений подготовь новый снимок в новой CI-папке:

```powershell
$env:SBERACT_CI_HOME = 'C:\Диск D\Сбер\SberAct-CI-v2'
node scripts/ci/assets.js prepare
```

Обнови repository variable SBERACT_CI_HOME на тот же путь. Предыдущий снимок
сохраняется. Нельзя обновлять lock автоматически при каждом push:
иначе проверка перестанет замечать случайную замену входных данных.

## Локальные проверки инфраструктуры

```powershell
$env:TEMP = 'C:\Диск D\Сбер\SberAct-CI\temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
node scripts/ci/release-metadata.js
node --test scripts/tests/ci-contract.test.js
python-backend\venv\Scripts\python.exe scripts/ci/check-python.py
npm run test:installer
```

Полный backend запускается с --require-golden-corpus. Пропавший корпус
останавливает CI, вместо пропуска golden-проверок. Ни одна обязательная
проверка не имеет continue-on-error.

Production frontend собирается с CI=false, как при обычной локальной
сборке CRA: предупреждения CRA остаются предупреждениями. TypeScript и
полные frontend-тесты до этого выполняются отдельно и обязаны пройти.

Справка: [добавление runner](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners),
[защита веток](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches),
[безопасность self-hosted runner](https://docs.github.com/en/actions/reference/security/secure-use),
[артефакты](https://github.com/actions/upload-artifact).


## Другой ПК и резервный runner

Запустить workflow через интерфейс GitHub можно с любого компьютера.
Фактические проверки и сборка выполняются на подключённом Windows runner.

Для второго ПК нужно:
- установить Windows runner для этого репозитория с теми же метками
  self-hosted, Windows, X64 и sberact;
- перенести assets и assets.lock.json согласованной версии;
- установить Python 3.12 и пакеты из requirements-ci.lock в новый venv;
- указать местный python.exe в settings.json. Копировать готовый venv
  между компьютерами не следует;
- использовать то же расположение SberAct-CI либо согласованно настроить путь.

Задание сможет получить любой свободный подключённый runner с этими метками.
Если основной ПК выключен, его может выполнить резервный. Если подходящих
runner онлайн нет, задание будет ожидать доступного исполнителя.

Полный комплект остаётся на том ПК, который выполнил сборку; его имя
сохраняется в build-info.json. Установщик можно дополнительно получать
из GitHub Actions через SBERACT_UPLOAD_INSTALLER=true. Полный OCR по-прежнему
остаётся на ПК. Для постоянной доступности позже можно использовать
отдельный Windows-сервер или виртуальную машину.
