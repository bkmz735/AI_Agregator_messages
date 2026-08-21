#!/bin/bash
set -e

echo "=================================================="
echo "🔄 Обновление AI Message Aggregator из GitHub"
echo "=================================================="

APP_DIR="/opt/ai-message-aggregator"
cd "$APP_DIR"

# Enable persistent password/token storage in Git
git config credential.helper store

# Discard local file edits on server (preserves .env and database)
git checkout -- .

echo "Подтягивание свежего кода из Git..."
git pull origin main

echo "Обновление зависимостей Python..."
./venv/bin/pip install -r requirements.txt

echo "Перезапуск фоновой службы systemd..."
systemctl restart ai-aggregator

echo "=================================================="
echo "✅ Проект обновлен и успешно перезапущен!"
echo "Посмотреть статус: systemctl status ai-aggregator"
echo "=================================================="
