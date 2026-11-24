# 🤖 AGENTS.md — AI Onboarding & Architecture Guide

> **Назначение этого файла:** Это системный контекстный справочник для любых AI-агентов (Cursor, Claude Code, GitHub Copilot, Windsurf, Roo/Cline, ChatGPT, Gemini и др.). При начале работы с репозиторием AI-агент должен в первую очередь прочитать данный файл, чтобы сразу понять архитектуру, правила разработки, структуру данных и ограничения проекта.

---

## 📌 1. Быстрый обзор (Executive Summary)

* **Проект:** `AI Message Aggregator & Buffer System` (Текущая версия: **v2.6**).
* **Суть:** Асинхронный сервис на Python для централизованного сбора, фильтрации спама, классификации через нейросеть и доставки сообщений из разнородных каналов в Telegram-бота.
* **Источники (Adapters):** 
  * ВКонтакте (VK LongPoll API — группы и личные сообщения);
  * Mail.ru / Email (IMAP протокол с поддержкой фильтрации тем);
  * Публичные Telegram-каналы (веб-парсер без риска блокировки аккаунта).
* **Обработка (AI & Logic):**
  * Слой 1 (L1): Мгновенная фильтрация по банвордам (`banwords.py`) без затрат токенов.
  * Слой 2 (L2): Батчинг сообщений и классификация по 11 категориям через **Google Gemini API** (`google-genai`).
  * Слой 3 (L3): Диалоговый ИИ-ассистент с **26 Function Calling инструментами** и веб-поиском через **DuckDuckGo**.
* **Хранилище:** SQLite3 через `aiosqlite` в высокопроизводительном режиме **WAL** (Write-Ahead Logging).
* **Telegram UI:** Построен на **aiogram 3.x** с поддержкой FSM, инлайн-кнопок, автоудаления сообщений и ночного режима.

---

## 🛠️ 2. Технологический стек

| Компонент | Технология | Примечание |
|---|---|---|
| **Язык** | Python 3.10+ (протестировано на 3.14) | Строгая типизация (`typing`, Pydantic v2) |
| **Telegram Framework** | `aiogram 3.x` | Асинхронный роутинг, FSM, Inline-клавиатуры |
| **AI SDK** | `google-genai` (v0.1.1+) | Мультимодальные модели Gemini, Function Calling |
| **База данных** | `SQLite3` + `aiosqlite` | WAL-режим, индексация `msg_uid`, `delete_at` |
| **Схемы данных** | `pydantic v2` | Валидация входных данных и ответов ИИ |
| **Email IMAP** | `aioimaplib` | Асинхронное чтение почтовых ящиков |
| **Веб-поиск** | `duckduckgo-search` | Бесплатный поиск без ключей API в фоновом потоке |
| **DNS / Proxy** | `dnspython`, `aiohttp-socks` | SmartDNS резолвер для обхода гео-блокировок AI |
| **Тестирование** | `unittest`, `pytest`, `pytest-asyncio` | 54 модульных и интеграционных теста |

---

## 🔄 3. Поток данных (Data Flow Pipeline)

```text
[Входящее сообщение] (VK / Email / TG News)
         │
         ▼
 1. ДЕДУПЛИКАЦИЯ ──► Проверка msg_uid в SQLite (is_duplicate). Дубликат? ──► [Пропуск]
         │ (Уникальное)
         ▼
 2. L1: БАНВОРДЫ ──► is_text_spam (banwords.py). Есть совпадение?
         │                │
         │                └──► ДА: Сохранить со статусом FILTERED, в ИИ не слать.
         ▼ (НЕТ)
 3. ОЧЕРЕДЬ (RAW QUEUE) ──► Накопление в raw_message_queue (asyncio.Lock).
         │
         ▼ (Каждые AI_BATCH_INTERVAL_SECONDS или принудительный flush)
 4. L2: AI BATCHING ────► Склейка сообщений в батч (до AI_BATCH_CHUNK_SIZE шт.)
         │                Каскадный fallback Gemini (3.5-lite -> 3.1-lite -> 3.7 -> 3.6 -> 3.5)
         │                Классификация по 11 категориям + краткое резюме.
         ▼
 5. СОХРАНЕНИЕ В БД ────► storage.save_message(...) в SQLite WAL.
         │
         ▼
 6. ДОСТАВКА В TELEGRAM:
         ├─► [Instant Mode]: Немедленная отправка сообщения пользователю.
         └─► [Digest Mode] : Сообщение буферизуется, отправка по расписанию сводки.
         │
         ▼
 7. AUTO-DELETE ────────► Фоновый воркер очищает сообщения по таймштампу delete_at.
```

---

## 🗂️ 4. Карта структуры проекта

```text
AI_Agregator_messages/
├── adapters/                  # Адаптеры источников входящих сообщений
│   ├── base_adapter.py        # Базовый абстрактный класс BaseAdapter
│   ├── vk_adapter.py          # VK LongPoll API (личные сообщения и группы)
│   ├── email_adapter.py       # IMAP клиент (Mail.ru, Yandex и др.)
│   └── tg_news_adapter.py     # Парсер открытых публичных Telegram-каналов
│
├── bot_handlers/              # Обработчики aiogram 3.x
│   ├── __init__.py
│   └── all_handlers.py        # Все FSM, коллбэки кнопок, диалог и «Умные подсказки»
│
├── config/                    # Конфигурация и промпты
│   ├── __init__.py
│   ├── settings.py            # Класс Config, чтение .env
│   └── prompts.py             # Системные промпты AI (фильтрация, аудио, ассистент)
│
├── models/                    # Pydantic v2 схемы данных
│   ├── __init__.py
│   ├── message.py             # MessageItem, AnalysisResult, DeliveryStatus
│   ├── settings.py            # UserSettings
│   ├── banword.py             # BanwordItem
│   ├── channel.py             # TGChannelItem
│   └── topic.py               # NewsTopicItem
│
├── tests/                     # Тестовый набор (32 теста)
│   ├── unit/                  # Юнит-тесты компонентов
│   └── integration/           # Интеграционные тесты пайплайна и отказоустойчивости
│
├── main.py                    # Главная точка входа, инициализация и цикл батчинга
├── master_bot.py              # Ядро Telegram-бота, планировщики дайджестов, UI
├── updater.py                 # Модуль бесшовного самообновления из GitHub (git pull, pip, systemd restart)
├── ai_engine.py               # Движок Google Gemini (батчи, транскрипция, fallback, SmartDNS)
├── user_agent.py              # Диалоговый ИИ-ассистент, 26 инструментов Function Calling, DuckDuckGo
├── storage.py                 # SQLite хранилище, WAL-режим, миграции схемы
├── settings_manager.py        # Управление настройками пользователя (в БД)
├── banwords.py                # Быстрый L1-фильтр спама по регуляркам (scope: global/email/vk)
├── ui_keyboards.py            # Фабрика инлайн- и реплай-клавиатур Telegram
├── logger_config.py           # Логгер с маскированием паролей и токенов
├── .env.example               # Образец конфигурационных переменных
├── requirements.txt           # Python-зависимости
├── Dockerfile / compose       # Контейнеризация проекта
├── deploy.sh / update.sh      # Скрипты для деплоя на Linux VPS (systemd)
├── AGENTS.md                  # Данный документ (контекст для ИИ)
├── ROADMAP.md                 # Дорожная карта развития проекта
└── README.md                  # Пользовательская документация
```

---

## 🧠 5. Особенности AI-движка (`ai_engine.py`)

1. **Каскад моделей при ошибках лимитов (429/ResourceExhausted):**
   Приоритетный порядок:
   1. `gemini-3.5-flash-lite` (500 RPD, 15 RPM)
   2. `gemini-3.1-flash-lite`
   3. `gemini-3.7-flash` (20 RPD, 5 RPM)
   4. `gemini-3.6-flash`
   5. `gemini-3.5-flash`
   Если модель вернула 429 по минутному лимиту — включается cooldown. Если по суточному — модель отправляется в `exhausted_models` до конца суток.
2. **SmartDNS и AI Proxy:**
   Для пользователей из РФ подключен обход блокировок `googleapis.com` через подмену DNS (`dnspython` + Comss/Xbox SmartDNS) или `AI_PROXY`. Не удаляйте этот функционал.
3. **Батчинг сообщений:**
   Сообщения пакуются в формат `JSON` со списком объектов `[{msg_uid, channel, sender, text}]`. Модель классифицирует всю пачку за 1 сетевой запрос, отвечая строгим `AnalysisBatchResponse`.

---

## 🛠️ 6. Система Function Calling (`user_agent.py`)

Ассистент поддерживает **26 инструментов**:
* **Просмотр списков:** `list_tg_channels`, `list_banwords`, `list_news_topics`, `list_dns_servers`, `get_settings_summary`, `get_bot_stats`.
* **Управление списками:** `add_banword`, `remove_banword`, `add_news_topic`, `remove_news_topic`, `add_tg_channel`, `remove_tg_channel`.
* **Настройки SmartDNS:** `add_dns_server`, `remove_dns_server`, `toggle_smart_dns`, `reset_dns_servers`.
* **Настройки доставки:** `set_timezone`, `set_digest_interval`, `set_delivery_mode`, `toggle_night_mode`, `set_night_hours`, `toggle_category_filter`.
* **Обновление и обслуживание:** `check_for_updates`, `update_bot`.
* **Веб-поиск:** `web_search` (через DuckDuckGo).
* **Служебные:** `clear_chat`.

### Правило добавления нового инструмента:
1. Объявить функцию-заглушку в `user_agent.py` с полным docstring и аннотациями типов.
2. Включить её в список `_get_tools()`.
3. Добавить обработчик вызова в `ConversationalAgent.run_step` или в подтверждение FSM в `bot_handlers/all_handlers.py`.
4. Написать юнит-тест в `tests/unit/test_all_14_tools.py` (или соответствующем тест-сьюте).

---

## ⚠️ 7. Критические правила для AI-агентов (Do's and Don'ts)

### ❌ Что категорически НЕЛЬЗЯ делать:
* **Не блокировать Event Loop:** Все операции с диском, сетью или БД должны быть строго асинхронными (`await`, `asyncio.to_thread` для тяжелых вычислений/DuckDuckGo).
* **Не отключать режим WAL в SQLite:** База `storage.py` работает конкурентно из нескольких корутин (прием сообщений, фоновый батчер, Telegram-хэндлеры). `PRAGMA journal_mode=WAL` обязателен.
* **Не хардкодить API-ключи и токены:** Все секреты читаются строго через `config.py` из `.env`.
* **Не ломать дедупликацию:** Каждое сообщение обязано иметь уникальный детерминированный `msg_uid`.
* **Не слать запросы в Gemini по одному сообщению:** Входящие сообщения должны идти через очередь `raw_message_queue` и метод `_flush_raw_queue`.

### ✅ Что ОБЯЗАТЕЛЬНО делать:
* Перед коммитом или завершением задачи запускать полный набор тестов:
  ```powershell
  python -m unittest discover -s tests
  ```
  Все 54 теста должны проходить со статусом `OK`.
* При изменении схемы БД в `storage.py` не забывать добавлять миграции с `IF NOT EXISTS` или `ALTER TABLE` блоками.
* При добавлении новых настроек обновлять Pydantic-схему `models/settings.py` и дефолты в `config/settings.py`.

---

## 🧪 8. Инструкция по тестированию

Для проверки кодовой базы используется стандартный `unittest`:

```bash
# Запуск всех тестов
python -m unittest discover -s tests

# Запуск конкретного модуля
python -m unittest tests/unit/test_banwords.py
python -m unittest tests/integration/test_pipeline.py
```

При работе с `pytest` (если установлен):
```bash
pytest tests/
```

---

## 🗺️ 9. Дорожная карта (Roadmap)
Планы развития проекта, будущие интеграции (WhatsApp, Max, Discord, RAG, Web Dashboard) подробно описаны в файле [ROADMAP.md](file:///c:/projects/AI_Agregator_messages/ROADMAP.md).
