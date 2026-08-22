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
    TG_API_ID: int = _get_int_env("TG_API_ID", 0)
    TG_API_HASH: str = os.getenv("TG_API_HASH", "").strip()
    TG_NEWS_CHANNELS: str = os.getenv("TG_NEWS_CHANNELS", "").strip()
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
    
    # Night Mode (Quiet Hours - Pause AI & Notifications during sleep to save tokens)
    NIGHT_MODE_ENABLED: bool = os.getenv("NIGHT_MODE_ENABLED", "false").strip().lower() in ("true", "1", "yes")
    NIGHT_START_HOUR: int = _get_int_env("NIGHT_START_HOUR", 23)
    NIGHT_END_HOUR: int = _get_int_env("NIGHT_END_HOUR", 7)
    
    DB_PATH: str = os.getenv("DB_PATH", "messages_database.db").strip()
    
    # System prompt for AI spam/importance classification
    AI_FILTER_PROMPT: str = """
Ты — умный личный ассистент и фильтр спама.
Твоя задача — проанализировать входящее сообщение из мессенджера или email-уведомления и вернуть структурированный JSON-ответ.

Входящие данные представляют собой JSON-массив объектов, каждый из которых содержит `msg_uid`, канал, отправителя и текст.

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

Ответ ДОЛЖЕН БЫТЬ строго в формате JSON, представляющий собой массив объектов со следующими полями для каждого сообщения. ВАЖНО: сохраняй оригинальный порядок сообщений и ОБЯЗАТЕЛЬНО копируй msg_uid!
{
  "msg_uid": "СТРОГО скопируй точный msg_uid из исходного входящего сообщения!",
  "category": "spam" | "urgent" | "important" | "gov_debt" | "gov_service" | "news" | "media" | "general" | "politics" | "interesting" | "bullshit",
  "summary": "Краткое резюме сообщения на русском языке (1-2 предложения, для задолженностей - укажи сумму и срок)",
  "action_required": true | false,
  "suggested_reply": "Предлагаемый вариант черновика ответа (или null, если не требуется)"
}
"""

config = Config()
