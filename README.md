# 🤖 AI Message Aggregator & Buffer System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-green.svg)](https://docs.aiogram.dev/)
[![Google Gemini API](https://img.shields.io/badge/Google%20GenAI-3.x%20Ready-orange.svg)](https://ai.google.dev/)
[![SQLite WAL](https://img.shields.io/badge/SQLite-WAL%20Mode-lightgrey.svg)](https://www.sqlite.org/wal.html)

**AI Message Aggregator** — автономная высокопроизводительная асинхронная система сбора, фильтрации, классификации и интеллектуальной доставки входящих сообщений из различных каналов (**VK**, **Mail.ru / Email**, **Telegram-каналы**).

Бот укомплектован мультимодальным нейросетевым движком на базе **Google Gemini API**, интерактивным диалоговым ИИ-ассистентом с поддержкой 14 инструментов **Function Calling**, веб-поиском Google Search, автоматической транскрипцией голосовых сообщений и встроенным планировщиком дайджестов.

> ⚠️ **Версия системы:** v2.5 (Рефакторинг `models/`, `config/`, `tests/`, 100% покрытие 14 ИИ-инструментов, полная синхронизация SQLite ➔ RAM).

---

## 🌟 Ключевые возможности

### 1. 📬 Мультиканальный сбор сообщений (Adapters)
* **ВКонтакте (VK LongPoll API)**: Сбор личных сообщений и постов групп, обработка текста, вложений и голосовых заметок.
* **Mail.ru / Email (IMAP)**: Чтение почтовых ящиков по безопасному протоколу IMAP. Удобно для автоматического сбора уведомлений от Авито, маркетплейсов и сервисов.
* **Telegram News Channels**: Парсинг открытых публичных каналов через веб-интерфейс без риска бана аккаунта Telegram.

### 2. 🧠 Нейросетевой классификатор (Gemini AI Engine)
* **11 Категорий контента**:
  * `spam` — реклама, мошенники, казино, финансовые пирамиды;
  * `urgent` — срочные вопросы клиентов, заказы, сделки;
  * `important` — важные личные и рабочие диалоги;
  * `gov_debt` — задолженности, штрафы ГИБДД, налоги ФНС, судебные приставы (с автоматическим извлечением сумм и сроков);
  * `gov_service` — Госуслуги, статусы заявлений, извещения;
  * `news` / `media` — новости, статьи, видео (YouTube, Rutube, VK Video);
  * `general` / `politics` / `interesting` / `bullshit` — прочие новости, геополитика и мусорные анонсы.
* **Каскадный перебор 5 fallback-моделей**: Автоматическое переключение между `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-2.5-flash` при исчерпании лимитов (429 RPM/RPD).
* **Батч-обработка (Token Saving)**: Сообщения объединяются в пачки (чанки) и отправляются в ИИ единым запросом, сокращая расход токенов до 80%.
* **Мультимодальная транскрипция аудио**: Дословная транскрипция голосовых сообщений через Gemini Multimodal API с последующей категоризацией и подготовкой черновика ответа.

### 3. 💬 Умный ИИ-Ассистент (Conversational Agent & 14 Tools)
* Ведение диалога в чате Telegram с сохранением контекста разговора.
* Живой поиск актуальной информации в сети через **Google Search**.
* Управление настройками бота на естественном языке с вызовом 14 Function Calling инструментов:
  * Управление банвордами, Telegram-каналами и темами новостей.
  * Установка часового пояса, интервала сводок, режима доставки, Ночного режима и фильтра категорий.
  * Очистка истории и просмотр живой статистики.

### 4. 🎛️ Режимы доставки и UI-Управление
* **Режимы доставки**:
  * `⚡ МГНОВЕННЫЙ`: Немедленная отправка сообщений пользователю.
  * `📥 СВОДКА`: Буферизация сообщений с отправкой структурированного дайджеста (интервалы: 15м, 30м, 1ч, 2ч, 4ч).
* **Часы тишины (Ночной режим)**: Заморозка ИИ и накопление сообщений в буфере в ночные часы для сохранения токенов и тишины.
* **Автоудаление сообщений (`AUTO_DELETE_DELAY_HOURS`)**: Фоновый сервис автоматической очистки прочитанных уведомлений в Telegram.
* **Маскирование логов**: Автоматическое скрытие паролей и прокси-токенов (`http://admin:****@host:port`) в диагностической панели.

---

## 🛠️ Технологический стек

* **Язык**: Python 3.10+
* **Telegram Framework**: `aiogram 3.x` (Async IO, Router, FSM Middleware)
* **AI & LLM**: `google-genai` (SDK 0.1.1+, Gemini Function Calling, Multimodal Audio)
* **База данных**: `SQLite3` + `aiosqlite` (Режим `WAL`, PRAGMA synchronous=NORMAL, индексы)
* **Схемы данных**: `Pydantic v2` (UserSettings, MessageItem, AnalysisResult и др.)
* **Сеть и HTTP**: `aiohttp`, `aioimaplib`, `BeautifulSoup4`, `dnspython`
* **Тестирование**: `unittest`, `pytest`, `pytest-asyncio`

---

## 📁 Актуальная структура проекта

```text
AI_Agregator_messages/
├── config/                        # Пакет конфигурации и промптов
│   ├── __init__.py
│   ├── settings.py                # Загрузка .env и параметры Config
│   └── prompts.py                 # Системные промпты (AI_FILTER_PROMPT, Audio, Agent instruction)
│
├── models/                        # Pydantic-схемы данных
│   ├── __init__.py
│   ├── settings.py                # UserSettings
│   ├── message.py                 # MessageItem, AnalysisResult, AudioAnalysisResult
│   ├── banword.py                 # BanwordItem
│   ├── channel.py                 # TGChannelItem
│   └── topic.py                   # NewsTopicItem
│
├── tests/                         # Модульные и интеграционные тесты
│   ├── unit/                      # Юнит-тесты (banwords, input_states, ui_callbacks, all_14_tools)
│   └── integration/               # Интеграционные тесты (pipeline, resilience, autodelete, subsystems)
│
├── adapters/                      # Адаптеры сбора входящих сообщений
│   ├── base_adapter.py            # Базовый абстрактный класс
│   ├── email_adapter.py           # IMAP Email адаптер (Mail.ru)
│   ├── tg_news_adapter.py         # Парсер публичных Telegram-каналов
│   └── vk_adapter.py              # VK LongPoll адаптер (группы и л/с)
│
├── bot_handlers/                  # Обработчики Telegram
│   ├── __init__.py
│   └── all_handlers.py            # Маршрутизация 67 Inline-кнопок, FSM и AI confirm
│
├── main.py                        # Точка входа приложения, цикл обработки очереди
├── master_bot.py                  # Главный класс MasterBot (планировщики, ночной режим, UI-баннер)
├── ai_engine.py                   # Движок ИИ Gemini (классификация батчей, транскрипция, fallback)
├── user_agent.py                  # Диалоговый ИИ-ассистент с 14 инструментами
├── storage.py                     # SQLite WAL база данных и SQL-индексы
├── settings_manager.py            # Управление пользовательскими настройками
├── banwords.py                    # Локальный Layer-1 фильтр спама и стоп-слов
├── ui_keyboards.py                # Генератор Inline и Reply клавиатур
├── logger_config.py               # Настройка логов с маскированием паролей
├── config.py                      # Совместимый прокси-модуль конфигурации
│
├── .env.example                   # Шаблон переменных окружения
├── requirements.txt               # Зависимости Python
├── Dockerfile                     # Docker-контейнеризация
├── docker-compose.yml             # Запуск через Docker Compose
├── deploy.sh / update.sh          # Скрипты авторазвертывания на Linux VPS
└── README.md                      # Документация проекта
```

---

## 🔄 Архитектура и поток данных (Data Flow Pipeline)

```text
[Входящее сообщение] (VK / Email / Telegram News)
         │
         ▼
1. BANWORD FILTER (Layer 1) ── (Совпадение) ──► 🚫 [Блокировка без обращения к ИИ]
         │ (Пропущено)
         ▼
2. RAW MESSAGE QUEUE ───────► 3. AI BATCHING (Gemini API) 
                                     │
                                     ▼ (Классификация по 11 категориям)
4. SQLITE WAL BUFFER ◄──────────────┘
   (messages table)
         │
         ▼
5. DELIVERY SYSTEM ─────────► [Instant] ──► 📤 Отправка в Telegram немедленно
         │                    [Digest]  ──► 📥 Буферизация ➔ Сводка по таймеру
         ▼
6. AUTO-DELETE ENGINE ──────► 🗑️ Очистка устаревших уведомлений по delete_at
```

---

## 🛠️ Установка и запуск

### 1. Локальный запуск (Local Environment)

```bash
# 1. Клонирование репозитория
git clone https://github.com/bkmz735/AI_Agregator_messages.git
cd AI_Agregator_messages

# 2. Создание и активация виртуального окружения
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Установка зависимостей
pip install -r requirements.txt

# 4. Создание файла настроек .env
cp .env.example .env
```

### 2. Запуск приложения
```bash
python main.py
```

### 3. Автоматический деплой на Linux VPS (Systemd)
```bash
chmod +x deploy.sh update.sh
./deploy.sh
```
Скрипт развернёт `systemd`-службу `ai-aggregator.service` и добавит служебные алиасы:
* `bot-status` — проверка статуса службы.
* `bot-logs` — просмотр живого лога событий.
* `bot-update` — подтягивание изменений из Git и перезапуск.

---

## ⚙️ Настройка переменных окружения (`.env`)

| Переменная | Описание | Значение по умолчанию |
|---|---|---|
| `AI_API_KEY` / `GEMINI_API_KEY` | API-ключ Google AI Studio (Gemini) | *(Обязательно)* |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота от @BotFather | *(Обязательно)* |
| `MASTER_CHAT_ID` | Ваш Telegram ID для получения уведомлений | *(Обязательно)* |
| `VK_TOKEN` | Токен пользователя/сообщества VK API | *Необязательно* |
| `VK_GROUP_ID` | ID группы ВКонтакте | `0` |
| `IMAP_SERVER` | IMAP-сервер электронной почты | `imap.mail.ru` |
| `IMAP_USER` / `IMAP_PASSWORD` | Логин и пароль приложения Mail.ru | *Необязательно* |
| `DELIVERY_MODE` | Режим доставки (`instant` / `digest`) | `digest` |
| `DIGEST_INTERVAL_MINUTES` | Интервал дайджеста в минутах | `60` |
| `AUTO_DELETE_DELAY_HOURS` | Время жизни уведомлений в чате (в часах) | `1` |
| `NIGHT_MODE_ENABLED` | Включение Ночного режима (`true`/`false`) | `false` |
| `NIGHT_START_HOUR` / `NIGHT_END_HOUR` | Границы Ночного режима (часы) | `23` / `7` |

---

## 🧪 Инструкция по тестированию

Все тесты структурированы в директории `tests/`. Для проверки всей системы выполните:

```bash
# Запуск полного тестового пакета через unittest
python -m unittest discover -s tests -p "test_*.py"

# Запуск через pytest
pytest tests/
```

### Наборы тестов:
* `tests/unit/test_banwords.py` — юнит-тесты локальной фильтрации спама.
* `tests/unit/test_input_states.py` — проверка FSM-состояний и сброса команд.
* `tests/unit/test_ui_callbacks.py` — тестирование 67 Inline-обработчиков UI.
* `tests/unit/test_all_14_tools.py` — проверка схем и регистрации 14 ИИ-инструментов.
* `tests/integration/test_pipeline.py` — интеграционный тест цикла обработки сообщений.
* `tests/integration/test_resilience.py` — тестирование сетевых таймаутов и рестарта.
* `tests/integration/test_autodelete.py` — интеграционный тест автоудаления сообщений.
* `tests/integration/test_subsystems.py` — проверка аудио-транскрипции и маскирования логов.

---

## 🤖 Справочник 14 Инструментов ИИ-Ассистента

ИИ-ассистент в чате с ботом поддерживает 14 инструментов (Function Calling) для управления настройками на естественном языке:

| Инструмент (Tool) | Описание | Пример запроса пользователя |
|---|---|---|
| `add_banword` | Добавляет банворд (scope: `global`, `email`, `vk`) | *«Заблокируй слово казино для почты»* |
| `remove_banword` | Удаляет слово из черного списка | *«Удали банворд 1xbet»* |
| `add_news_topic` | Добавляет тему новостей (`liked` / `disliked`) | *«Добавь тему ИИ и нейросети»* |
| `remove_news_topic` | Удаляет тему новостей из настроек | *«Забудь тему Криптовалюта»* |
| `add_tg_channel` | Добавляет Telegram-канал в отслеживаемые | *«Добавь канал @mash»* |
| `remove_tg_channel` | Удаляет Telegram-канал из отслеживания | *«Удали канал Mash»* |
| `get_bot_stats` | Возвращает свежую статистику сообщений | *«Покажи статистику бота»* |
| `set_timezone` | Изменяет часовой пояс пользователя (в часах от UTC) | *«Поставь часовой пояс Екатеринбург (+5)»* |
| `set_digest_interval` | Изменяет интервал сводки в минутах | *«Присылай сводку раз в 2 часа»* |
| `set_delivery_mode` | Переключает режим (`instant` / `digest`) | *«Включи мгновенную доставку»* |
| `toggle_night_mode` | Включает/выключает Ночной режим (`True`/`False`) | *«Включи ночной режим»* |
| `set_night_hours` | Настраивает часы тишины | *«Установи часы тишины с 23:00 до 7:00»* |
| `toggle_category_filter` | Включает/отключает фильтр категории ИИ | *«Отключи фильтрацию новостей»* |
| `clear_chat` | Очищает историю диалога и базу сообщений | *«Очисти историю чата»* |

---

## 👨‍💻 Расширение проекта (Developer Guide)

### Добавление нового адаптера входящих сообщений
1. Создайте модуль в `adapters/my_adapter.py`, отнаследовавшись от `BaseAdapter`:
   ```python
   from adapters.base_adapter import BaseAdapter

   class MyAdapter(BaseAdapter):
       def __init__(self):
           super().__init__(name="MySource")
       
       async def start(self):
           # Логика подключения и получения сообщений
           # При получении вызовите: await self.emit_message(sender, text, msg_uid)
   ```
2. Подключите адаптер в `main.py` в методе `_init_adapters()`.

### Добавление нового ИИ-инструмента
1. Объявите функцию-схему в [`user_agent.py`](file:///c:/projects/AI_Agregator_messages/user_agent.py) и добавьте её в `_get_tools()`.
2. Добавьте логику обработки действия в метод `process_ai_action_confirm` в [`bot_handlers/all_handlers.py`](file:///c:/projects/AI_Agregator_messages/bot_handlers/all_handlers.py).

---

## 📄 Лицензия

Проект распространяется под открытой лицензией **MIT**.
