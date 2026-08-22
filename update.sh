#!/bin/bash
set -e

echo "=================================================="
echo "🔄 Обновление AI Message Aggregator из GitHub"
echo "=================================================="

APP_DIR="/opt/ai-message-aggregator"
cd "$APP_DIR"

# Grant permanent execution permissions to scripts
chmod +x *.sh *.py 2>/dev/null || true

# Enable persistent password/token storage in Git
git config credential.helper store

# Discard local file edits on server (preserves .env and database)
git checkout -- .

OLD_REQ_HASH=$(md5sum requirements.txt 2>/dev/null)

echo "Подтягивание свежего кода из Git..."
git pull origin main

# Re-apply execution permissions after pull
chmod +x *.sh *.py 2>/dev/null || true

NEW_REQ_HASH=$(md5sum requirements.txt 2>/dev/null)

if [ "$OLD_REQ_HASH" != "$NEW_REQ_HASH" ]; then
    echo "Обновление зависимостей (requirements.txt изменен)..."
    ./venv/bin/pip install -r requirements.txt
else
    echo "Зависимости актуальны, пропускаем pip..."
fi

echo "Обновление конфигурации systemd..."
cp -f ai-aggregator.service /etc/systemd/system/ai-aggregator.service
systemctl daemon-reload

echo "Перезапуск службы (это может занять пару секунд)..."
systemctl restart ai-aggregator

# Setup convenient bash aliases and bot-help in ~/.bashrc
if ! grep -q "bot-help" ~/.bashrc 2>/dev/null; then
    cat << 'EOF' >> ~/.bashrc

# AI Aggregator Console Cheat Sheet & Aliases
alias bot-status='systemctl status ai-aggregator'
alias bot-logs='journalctl -u ai-aggregator -f'
alias bot-restart='systemctl restart ai-aggregator'
alias bot-update='bash /opt/ai-message-aggregator/update.sh'

bot-help() {
    echo "=================================================="
    echo "🛠️  AI Message Aggregator — Шпаргалка команд Linux"
    echo "=================================================="
    echo "  bot-status  - Посмотреть статус службы и RAM/CPU"
    echo "  bot-logs    - Логи работы в реальном времени"
    echo "  bot-restart - Перезапустить фоновую службу"
    echo "  bot-update  - Обновить код из GitHub и перезапустить"
    echo "  bot-help    - Показать эту справку"
    echo "=================================================="
}
EOF
fi

echo "=================================================="
echo "✅ Проект обновлен и успешно перезапущен!"
echo "Наберите bot-help в консоли для вызова справки!"
echo "=================================================="
