# Первый запуск облачного CI

## Готово локально

Пользователь загрузил корпус в приватный репозиторий
Andrew09127/data-for-verification-CI-CD, коммит
29930862660b3da94c7c477789ceef30a6b968e7, и добавил секрет CI_DATA_SSH_KEY.
Workflow переведён на windows-2022 GitHub Actions. OCR подготовлен частями.
Агент файлы на GitHub не загружал и Git-команды не выполнял.

## 1. Один раз загрузить исходный OCR

В основном публичном репозитории Ger-Ostap12/sberAct открой
Releases → Draft a new release.

Новый тег: ci-ocr-7dc90fd871184668.
Target: release. Title: OCR assets 7dc90fd871184668.
Отметь Set as a pre-release, чтобы технический комплект не считался
последней пользовательской версией.

Прикрепи все ШЕСТЬ файлов из папки:

```text
C:\Диск D\Сбер\SberAct-CI\exports\ci-ocr-7dc90fd871184668
```

```text
converter.zip.part-000
converter.zip.part-001
converter.zip.part-002
converter.zip.part-003
converter-manifest.json
ocr-assets.json
```

Три части по 1 610 612 736 байт и последняя 117 290 224 байта.
Каждая меньше 2 GiB. Дождись загрузки всех файлов, затем Publish release.
Для скачивания используются публичные URL: черновика недостаточно.

Не копируй целиком SberAct-CI: там есть SSH-ключи и закрытые документы.
Проверки release могут работать до загрузки OCR, но полная сборка main
без опубликованного технического комплекта остановится.

## 2. Отправить подготовленный CI в release

Пользователь самостоятельно делает commit и push. Вариант сообщения:

```text
Перевести CI на серверы GitHub и подготовить облачный выпуск
```

В Actions → SberAct Windows проверить Repository policy, Windows checks,
Backend checks. Старый ожидающий self-hosted запуск можно отменить.
Новый workflow личного runner не ожидает.

Первый серверный прогон ещё не выполнен. Он должен подтвердить доступ
к закрытым данным, установку закреплённых Python-пакетов и ресурсы runner.

## 3. Подготовить выпуск main

После зелёного CI пользователь создаёт PR release → main.
Версия должна превышать main, оба package.json и lock-файлы согласованы,
CHANGELOG содержит описание этой версии. Текущая подготовка: 2.1.3.

После слияния повторяются проверки, собираются backend/установщик,
объединяется OCR, проверяется каждый файл архива.
Результат — черновик Release v2.1.3 на проверенном коммите.
GitHub при необходимости создаёт тег. Агент из чата ничего не коммитит
и не публикует. Опубликованный выпуск не перезаписывается; продолжить
незавершённый CI-черновик можно только на том же коммите.

## 4. Проверить скачанный комплект

Обычное обновление установленной программы:
скачать только SberAct-App-Update-2.1.3.zip, распаковать и выбрать папку
в приложении. OCR сохраняется.

Первая установка/замена OCR:
скачать установщик, feed/blockmap, update-package.json,
converter-manifest.json, ocr-assets.json, Assemble-Update.ps1 и части
converter.zip.part-*. Запустить Assemble-Update.ps1 в этой папке.
Полученный комплект проверить установкой/обновлением.
Дополнительный малый ZIP для полной установки не нужен.

После проверки пользователь публикует черновик.
Обновление отдельных файлов OCR будет следующим этапом.

## Закрытые данные

Ключ используется только для private checkout в backend job.
Внешние fork отклоняются, persist-credentials=false.
Сырой вывод pytest и XML остаются внутри VM. Публично выводятся только
счётчики; подробности ошибок воспроизводятся локально.
Не добавляй ключи, документы и сырой вывод тестов в публичные артефакты.

Справка:
[Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases),
[runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[оплата](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
