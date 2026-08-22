# 🤖 AI Message Aggregator & Buffer System

Единый умный фильтр и агрегатор входящих сообщений (VK, Mail.ru / Авито / Instagram, Telegram News) с классификацией спама и выжимками через **AI (LLM)**.

## 🚀 Особенности
- **Интеграция каналов**: VK LongPoll (личные сообщения и группы), Mail.ru IMAP (email-уведомления от Авито/Insta), Парсинг Telegram Каналов (прямое чтение t.me без авторизации).
- **AI-фильтрация (LLM API)**: Определение категории (`spam`, `urgent`, `important`, `general`, `gov_debt`, `gov_service`), подготовка выжимок и черновиков ответов. Поддержка любого современного AI через подмену ключа.
- **Интерактивное автоудаление**: Кнопка "Прочитано" под сообщениями в Telegram мгновенно стирает уведомление, поддерживая чат в полной чистоте. Резервный таймер удаляет старые оповещения через 1 час.
- **Буферизация & Дайджесты (Сводки)**: Режим работы можно переключать одной кнопкой в меню:
  * `⚡ СРАЗУ`: Уведомления приходят мгновенно по одному.
  * `📥 СВОДКА`: Сообщения собираются в буфер и приходят раз в час единым отчетом.
- **24/7 На Linux VPS**: Готовые скрипты установки `deploy.sh` и обновления `update.sh` одной командой.

## 🛠️ Запуск на Linux VPS
```bash
git clone https://github.com/bkmz735/AI_Agregator_messages.git /opt/ai-message-aggregator
cd /opt/ai-message-aggregator
cp .env.example .env
# заполните ключи в .env
chmod +x deploy.sh update.sh
./deploy.sh
```

## 🔄 Обновление сервера
Наберите следующую команду в консоли сервера для быстрого обновления:
```bash
bot-update
```
Для просмотра логов в реальном времени:
```bash
bot-logs
```

## 📂 Структура проекта
```text
📦 ai-message-aggregator
 ┣ 📂 adapters/          # Адаптеры для получения сообщений
 ┃ ┣ 📜 base_adapter.py    # Базовый класс адаптера
 ┃ ┣ 📜 email_adapter.py   # IMAP (Mail.ru, Авито и др.)
 ┃ ┣ 📜 tg_news_adapter.py # Парсер открытых TG-каналов
 ┃ ┗ 📜 vk_adapter.py      # VK LongPoll (ЛС и группы)
 ┣ 📂 bot_handlers/      # Обработчики Telegram бота (aiogram)
 ┃ ┗ 📜 all_handlers.py    # Клавиатуры, кнопки, команды, ИИ-диалог
 ┣ 📜 main.py            # Точка входа (запуск бота и адаптеров)
 ┣ 📜 master_bot.py      # Главный класс управления ботом (MasterBot)
 ┣ 📜 user_agent.py      # ConversationalAgent (Gemini API и вызовы функций)
 ┣ 📜 ai_engine.py       # Провайдер нейросетей (Gemini)
 ┣ 📜 storage.py         # Работа с базой данных (SQLite)
 ┣ 📜 settings_manager.py# Централизованное управление динамическими настройками
 ┣ 📜 config.py          # Статические настройки и ключи (загрузка из .env)
 ┣ 📜 logger_config.py   # Настройка логирования
 ┣ 📜 ui_keyboards.py    # Генерация UI клавиатур бота
 ┗ 📜 .env               # Файл с секретными токенами (не коммитится)
```
