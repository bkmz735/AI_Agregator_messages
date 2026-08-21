# 🤖 AI Message Aggregator & Buffer System

Единый умный фильтр и агрегатор входящих сообщений (Telegram, VK, Mail.ru / Авито / Instagram) с классификацией спама и выжимками через **Gemini AI** и встроенным **Xray VLESS Reality туннелем**.

## 🚀 Особенности
- **Интеграция каналов**: VK LongPoll, Mail.ru IMAP (email-уведомления от Авито/Insta), Telegram Bot API.
- **AI-фильтрация (Gemini 2.5/3.6 Flash)**: Определение категории (`spam`, `urgent`, `important`, `general`), подготовка выжимок и черновиков ответов.
- **Буферизация & Дайджесты**: Срочные вопросы приходят мгновенно, остальные накапливаются в SQLite буфере и отправляются по расписанию.
- **Изолированный VLESS Туннель**: Встроенная поддержка `xray` для защиты Telegram-трафика без разрыва соединений VK.
- **24/7 На Linux VPS**: Готовые скрипты установки `deploy.sh` и обновления `update.sh` одной командой.

## 🛠️ Запуск на Linux VPS
```bash
git clone https://github.com/ВАШ_НИК/AI_Agregator_messages.git /opt/ai-message-aggregator
cd /opt/ai-message-aggregator
cp .env.example .env
# заполните ключи в .env
chmod +x deploy.sh update.sh
./deploy.sh
```

## 🔄 Обновление сервера
```bash
/opt/ai-message-aggregator/update.sh
```
