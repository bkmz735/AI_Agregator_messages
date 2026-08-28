import os
from pathlib import Path
from dotenv import load_dotenv
from config.prompts import AI_FILTER_PROMPT

# Load .env if present
env_path = Path(__file__).parent.parent / ".env"
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
    
    # ⏱️ TIME & INTERVAL CONFIGURATION
    DELIVERY_MODE: str = os.getenv("DELIVERY_MODE", "digest").strip()
    DIGEST_INTERVAL_MINUTES: int = _get_int_env("DIGEST_INTERVAL_MINUTES", 60)
    AI_BATCH_INTERVAL_SECONDS: int = _get_int_env("AI_BATCH_INTERVAL_SECONDS", 60)
    VK_POLL_INTERVAL_SECONDS: int = _get_int_env("VK_POLL_INTERVAL_SECONDS", 60)
    EMAIL_POLL_INTERVAL_SECONDS: int = _get_int_env("EMAIL_POLL_INTERVAL_SECONDS", 60)
    AUTO_DELETE_DELAY_HOURS: int = _get_int_env("AUTO_DELETE_DELAY_HOURS", 1)
    AUTO_DELETE_ACTION_DELAY: int = _get_int_env("AUTO_DELETE_ACTION_DELAY", 7)
    LIST_RESPONSE_KEEP_SECONDS: int = _get_int_env("LIST_RESPONSE_KEEP_SECONDS", 60)
    DB_PURGE_DAYS: int = _get_int_env("DB_PURGE_DAYS", 7)
    
    # 🤖 AI LIMITS
    AI_MAX_RPM: int = _get_int_env("AI_MAX_RPM", 15)
    AI_BATCH_CHUNK_SIZE: int = _get_int_env("AI_BATCH_CHUNK_SIZE", 5)
    
    # Night Mode
    NIGHT_MODE_ENABLED: bool = os.getenv("NIGHT_MODE_ENABLED", "false").strip().lower() in ("true", "1", "yes")
    NIGHT_START_HOUR: int = _get_int_env("NIGHT_START_HOUR", 23)
    NIGHT_END_HOUR: int = _get_int_env("NIGHT_END_HOUR", 7)
    
    DB_PATH: str = os.getenv("DB_PATH", "messages_database.db").strip()
    
    AI_FILTER_PROMPT: str = AI_FILTER_PROMPT

config = Config()
