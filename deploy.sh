#!/usr/bin/env bash
set -e

echo "=================================================="
echo "🚀 Развертывание AI Message Aggregator на Linux VPS"
echo "=================================================="

# Install Python & minimal system dependencies
apt-get update
apt-get install -y python3 python3-pip python3-venv wget unzip curl

# Directory setup
APP_DIR="/opt/ai-message-aggregator"
mkdir -p "$APP_DIR"

# Copy files if executing from project folder
if [ "$PWD" != "$APP_DIR" ]; then
    echo "Копирование файлов проекта в $APP_DIR..."
    cp -r . "$APP_DIR/"
fi

cd "$APP_DIR"

# Grant permanent execution permissions to all scripts
chmod +x *.sh *.py 2>/dev/null || true

# Virtual environment
if [ ! -d "venv" ]; then
    echo "Создание virtualenv..."
    python3 -m venv venv
fi

echo "Установка зависимостей..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Systemd service setup
echo "Настройка фоновой службы systemd (24/7)..."
cp ai-aggregator.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable ai-aggregator
systemctl restart ai-aggregator

echo "=================================================="
echo "✅ Проект успешно развернут и запущен в фоне 24/7!"
echo "Проверить статус службы: systemctl status ai-aggregator"
echo "Посмотреть логи: journalctl -u ai-aggregator -f"
echo "=================================================="
