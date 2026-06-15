#!/bin/bash
# Упаковка исходного кода для GitHub Release (отдельно от build.sh)
# Запуск: ./package-source-release.sh
# Результат: release/SberAct-<version>-source.tar.gz и .zip

set -e
cd "$(dirname "$0")"

RELEASE_VERSION="${RELEASE_VERSION:-1.0.4}"
STAGING="release/source-staging"
ARCHIVE_BASE="SberAct-${RELEASE_VERSION}-source"

echo "=== Упаковка исходников для релиза ${RELEASE_VERSION} ==="

rm -rf "$STAGING"
mkdir -p "$STAGING" release

rsync -a \
  --exclude node_modules \
  --exclude electron-app/node_modules \
  --exclude electron-app/build \
  --exclude dist \
  --exclude build \
  --exclude release \
  --exclude realise \
  --exclude sber \
  --exclude venv \
  --exclude .venv \
  --exclude .venv-linux \
  --exclude __pycache__ \
  --exclude .git \
  --exclude '*.pyc' \
  --exclude python-backend/generated \
  --exclude .env \
  \
  electron-app \
  python-backend \
  emplates \
  .gitignore \
  build.sh \
  build.bat \
  Dockerfile \
  install.sh \
  install-astralinux.sh \
  install-astralinux-deps.sh \
  LICENSE \
  package.json \
  package-lock.json \
  SberAct.spec \
  start.sh \
  test_document.txt \
  "$STAGING"/ 2>/dev/null || true

# Опциональные файлы (если есть)
for f in README.md README astralinux-config; do
  [[ -e "$f" ]] && cp -a "$f" "$STAGING/"
done

tar -czf "release/${ARCHIVE_BASE}.tar.gz" -C "$STAGING" .
if command -v zip &>/dev/null; then
  (cd "$STAGING" && zip -rq "../../release/${ARCHIVE_BASE}.zip" .)
else
  echo "Предупреждение: zip не установлен, создаётся только .tar.gz"
fi

rm -rf "$STAGING"

ls -lh "release/${ARCHIVE_BASE}.tar.gz" 2>/dev/null || true
ls -lh "release/${ARCHIVE_BASE}.zip" 2>/dev/null || true

echo ""
echo "=== Готово ==="
echo "Linux:   release/${ARCHIVE_BASE}.tar.gz"
echo "Windows: release/${ARCHIVE_BASE}.zip"
echo ""
echo "Загрузка в релиз:"
echo "  cd $(pwd)"
echo "  gh release upload ${RELEASE_VERSION} \\"
echo "    release/${ARCHIVE_BASE}.tar.gz \\"
echo "    release/${ARCHIVE_BASE}.zip \\"
echo "    --clobber"
