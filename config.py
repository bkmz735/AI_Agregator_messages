import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

def _get_int_env(key: str, default: int = 0) -> int:
    val = os.getenv(key, "").strip()
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default

class Config:
    AI_API_KEY: str = os.getenv("AI_API_KEY", os.getenv("GEMINI_API_KEY", "")).strip()
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_PROXY: str = os.getenv("TELEGRAM_PROXY", "").strip()
    MASTER_CHAT_ID: int = _get_int_env("MASTER_CHAT_ID", 0)
    
    VK_TOKEN: str = os.getenv("VK_TOKEN", "").strip()
    VK_GROUP_ID: int = _get_int_env("VK_GROUP_ID", 0)
    
    IMAP_SERVER: str = os.getenv("IMAP_SERVER", "imap.mail.ru").strip()
    IMAP_PORT: int = _get_int_env("IMAP_PORT", 993)
    IMAP_USER: str = os.getenv("IMAP_USER", "").strip()
    IMAP_PASSWORD: str = os.getenv("IMAP_PASSWORD", "").strip()
    TG_NEWS_POLL_INTERVAL_SECONDS: int = _get_int_env("TG_NEWS_POLL_INTERVAL_SECONDS", 120)
    
    # ==========================================
    # ⏱️ TIME & INTERVAL CONFIGURATION
    # ==========================================
    DELIVERY_MODE: str = os.getenv("DELIVERY_MODE", "digest").strip()
    DIGEST_INTERVAL_MINUTES: int = _get_int_env("DIGEST_INTERVAL_MINUTES", 60)
    AI_BATCH_INTERVAL_SECONDS: int = _get_int_env("AI_BATCH_INTERVAL_SECONDS", 60)
    VK_POLL_INTERVAL_SECONDS: int = _get_int_env("VK_POLL_INTERVAL_SECONDS", 60)
    EMAIL_POLL_INTERVAL_SECONDS: int = _get_int_env("EMAIL_POLL_INTERVAL_SECONDS", 60)
    AUTO_DELETE_DELAY_HOURS: int = _get_int_env("AUTO_DELETE_DELAY_HOURS", 1)
    DB_PURGE_DAYS: int = _get_int_env("DB_PURGE_DAYS", 7)
    
    # 🤖 AI LIMITS
    AI_MAX_RPM: int = _get_int_env("AI_MAX_RPM", 3)
    AI_BATCH_CHUNK_SIZE: int = _get_int_env("AI_BATCH_CHUNK_SIZE", 3)
    
    # Night Mode (Quiet Hours - Pause AI & Notifications during sleep to save tokens)
    NIGHT_MODE_ENABLED: bool = os.getenv("NIGHT_MODE_ENABLED", "false").strip().lower() in ("true", "1", "yes")
    NIGHT_START_HOUR: int = _get_int_env("NIGHT_START_HOUR", 23)
    NIGHT_END_HOUR: int = _get_int_env("NIGHT_END_HOUR", 7)
    
    DB_PATH: str = os.getenv("DB_PATH", "messages_database.db").strip()
    
    # System prompt for AI spam/importance classification
    AI_FILTER_PROMPT: str = """
Ты — умный личный ассистент и фильтр спама.
Твоя задача — проанализировать входящее сообщение из мессенджера или email-уведомления и вернуть структурированный JSON-ответ.

Входящие данные представляют собой JSON-массив объектов, каждый из которых содержит `id` (числовой индекс) и `text` (содержимое сообщения).

Правила классификации category:
1. "spam" — реклама, нежелательные предложения, рассылки, спам, финансовые пирамиды, мошенничество.
2. "urgent" — срочные вопросы по работе/сделкам, клиенты готовые купить, проблемы, требующие быстрого решения.
3. "important" — важные личные или рабочие сообщения, вопросы клиентов, детали заказов.
4. "gov_debt" — государственные уведомления о задолженностях: штрафы, налоги, пени, судебные приставы. (ОБЯЗАТЕЛЬНО извлекай сумму, срок оплаты и причину и включай в summary).
5. "gov_service" — прочие государственные уведомления, Госуслуги, статусы заявлений, официальные органы.
6. "news" — новости, информационные рассылки, статьи, анонсы.
7. "media" — медиаконтент, ссылки на видео (YouTube, Rutube, VK Видео), подкасты, аудиозаписи.
8. "general" — обычные сообщения, не имеющие специфического приоритета.
9. "politics" — новости про политику, геополитику, законы, выборы, войны.
10. "interesting" — интересные новости, технологии, наука, важные события в мире.
11. "bullshit" — мусорные новости, слухи, "фигня", желтая пресса, неинтересная чепуха, мемчики.

⚠️ ВАЖНОЕ ПРАВИЛО ДЛЯ ГОЛОСОВЫХ СООБЩЕНИЙ:
Если текст сообщения начинается с "[Голосовое]", КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО делать краткую выжимку или перефразировать его! Ты ОБЯЗАН скопировать в поле `summary` весь текст голосового сообщения ДОСЛОВНО (слово в слово), убрав только приписку "[Голосовое]".

⚠️ ВАЖНОЕ ПРАВИЛО ДЛЯ НОВОСТЕЙ (tg_news):
Если сообщение пришло из канала "tg_news", ему КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО ставить категории "urgent", "important", "gov_debt" или "gov_service". Новости — это просто новости, они не бывают срочными для пользователя. Для "tg_news" используй ТОЛЬКО категории: "news", "politics", "interesting", "bullshit" или "media".

Ответ ДОЛЖЕН БЫТЬ строго в формате JSON, представляющий собой массив объектов со следующими полями для каждого сообщения. ВАЖНО: сохраняй оригинальный порядок сообщений и ОБЯЗАТЕЛЬНО возвращай тот же `id`!
{
  "id": 0,
  "category": "spam" | "urgent" | "important" | "gov_debt" | "gov_service" | "news" | "media" | "general" | "politics" | "interesting" | "bullshit",
  "summary": "Краткая суть (3-4 предложения). Пиши законченные предложения без многоточий. СРАЗУ переходи к сути БЕЗ вводных фраз вроде 'Сообщение от...' или 'Новость от...'.",
  "action_required": true | false,
  "suggested_reply": "Предлагаемый вариант черновика ответа (или null, если не требуется)"
}
"""

config = Config()
