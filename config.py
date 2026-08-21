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
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_PROXY: str = os.getenv("TELEGRAM_PROXY", "").strip()
    VLESS_LINK: str = os.getenv("VLESS_LINK", "").strip()
    MASTER_CHAT_ID: int = _get_int_env("MASTER_CHAT_ID", 0)
    
    VK_TOKEN: str = os.getenv("VK_TOKEN", "").strip()
    VK_GROUP_ID: int = _get_int_env("VK_GROUP_ID", 0)
    
    IMAP_SERVER: str = os.getenv("IMAP_SERVER", "imap.mail.ru").strip()
    IMAP_PORT: int = _get_int_env("IMAP_PORT", 993)
    IMAP_USER: str = os.getenv("IMAP_USER", "").strip()
    IMAP_PASSWORD: str = os.getenv("IMAP_PASSWORD", "").strip()
    
    # Delivery Mode: "instant" or "digest" (urgent instant, rest buffered)
    DELIVERY_MODE: str = os.getenv("DELIVERY_MODE", "digest").strip()
    DIGEST_INTERVAL_MINUTES: int = _get_int_env("DIGEST_INTERVAL_MINUTES", 60)
    AI_BATCH_INTERVAL_SECONDS: int = _get_int_env("AI_BATCH_INTERVAL_SECONDS", 60)
    
    DB_PATH: str = os.getenv("DB_PATH", "messages_database.db").strip()
    
    # System prompt for Gemini spam/importance classification
    AI_FILTER_PROMPT: str = """
Ты — умный личный ассистент и фильтр спама.
Твоя задача — проанализировать входящее сообщение из мессенджера или email-уведомления и вернуть структурированный JSON-ответ.

Входящие данные представляют собой JSON-массив объектов, каждый из которых содержит `msg_uid`, канал, отправителя и текст.

Правила классификации category:
1. "spam" — реклама, нежелательные предложения, рассылки, спам, финансовые пирамиды, мошенничество.
2. "urgent" — срочные вопросы по работе/сделкам, клиенты готовые купить, проблемы, требующие быстрого решения.
3. "important" — важные личные или рабочие сообщения, вопросы клиентов, детали заказов.
4. "general" — обычные сообщения, новости или флуд, не имеющие высокого приоритета.

Ответ ДОЛЖЕН БЫТЬ строго в формате JSON, представляющий собой массив объектов со следующими полями для каждого сообщения. ВАЖНО: сохраняй оригинальный порядок сообщений и ОБЯЗАТЕЛЬНО копируй msg_uid!
{
  "msg_uid": "СТРОГО скопируй точный msg_uid из исходного входящего сообщения!",
  "category": "spam" | "urgent" | "important" | "general",
  "summary": "Краткое резюме сообщения на русском языке (1-2 предложения)",
  "action_required": true | false,
  "suggested_reply": "Предлагаемый вариант черновика ответа (или null, если не требуется)"
}
"""

config = Config()
