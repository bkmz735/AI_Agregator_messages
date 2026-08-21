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

echo "Подтягивание свежего кода из Git..."
git pull origin main

# Re-apply execution permissions after pull
chmod +x *.sh *.py 2>/dev/null || true

echo "Обновление зависимостей Python..."
./venv/bin/pip install -r requirements.txt

echo "Перезапуск фоновой службы systemd..."
systemctl restart ai-aggregator

# Setup convenient bash aliases if not already added
if ! grep -q "bot-status" ~/.bashrc 2>/dev/null; then
    cat << 'EOF' >> ~/.bashrc

# AI Aggregator Short Aliases
alias bot-status='systemctl status ai-aggregator'
alias bot-logs='journalctl -u ai-aggregator -f'
alias bot-restart='systemctl restart ai-aggregator'
alias bot-update='bash /opt/ai-message-aggregator/update.sh'
EOF
fi

echo "=================================================="
echo "✅ Проект обновлен и успешно перезапущен!"
echo "Короткие команды консоли:"
echo "  bot-status  - Статус службы"
echo "  bot-logs    - Логи в реальном времени"
echo "  bot-restart - Перезапуск бота"
echo "  bot-update  - Обновление из GitHub"
echo "=================================================="
