import logging
from config import config

logger = logging.getLogger(__name__)

class SettingsManager:
    """Centralizes dynamic settings fetched from the database."""
    def __init__(self, storage):
        self.storage = storage

    # --- Time & Interval Settings ---
    async def get_timezone_offset(self) -> int:
        val = await self.storage.get_setting("timezone_offset", "3")
        return int(val)

    async def update_timezone_offset(self, offset: int):
        await self.storage.set_setting("timezone_offset", str(offset))

    async def get_digest_interval_minutes(self) -> int:
        val = await self.storage.get_setting("digest_interval_minutes", str(config.DIGEST_INTERVAL_MINUTES))
        return int(val)

    async def update_digest_interval_minutes(self, mins: int):
        await self.storage.set_setting("digest_interval_minutes", str(mins))

    async def get_ai_batch_interval_seconds(self) -> int:
        val = await self.storage.get_setting("ai_batch_interval_seconds", str(config.AI_BATCH_INTERVAL_SECONDS))
        return int(val)

    async def update_ai_batch_interval_seconds(self, secs: int):
        await self.storage.set_setting("ai_batch_interval_seconds", str(secs))

    async def get_email_poll_interval_seconds(self) -> int:
        val = await self.storage.get_setting("email_poll_interval_seconds", str(config.EMAIL_POLL_INTERVAL_SECONDS))
        return int(val)

    async def update_email_poll_interval_seconds(self, secs: int):
        await self.storage.set_setting("email_poll_interval_seconds", str(secs))

    async def get_tg_news_poll_interval_seconds(self) -> int:
        val = await self.storage.get_setting("tg_news_poll_interval_seconds", str(config.TG_NEWS_POLL_INTERVAL_SECONDS))
        return int(val)

    async def update_tg_news_poll_interval_seconds(self, secs: int):
        await self.storage.set_setting("tg_news_poll_interval_seconds", str(secs))

    async def get_db_purge_days(self) -> int:
        val = await self.storage.get_setting("db_purge_days", str(config.DB_PURGE_DAYS))
        return int(val)

    async def update_db_purge_days(self, days: int):
        await self.storage.set_setting("db_purge_days", str(days))

    async def get_auto_delete_delay_hours(self) -> int:
        val = await self.storage.get_setting("auto_delete_delay_hours", str(config.AUTO_DELETE_DELAY_HOURS))
        return int(val)

    async def update_auto_delete_delay_hours(self, hours: int):
        await self.storage.set_setting("auto_delete_delay_hours", str(hours))

    async def get_delivery_mode(self) -> str:
        return await self.storage.get_setting("delivery_mode", config.DELIVERY_MODE)

    async def update_delivery_mode(self, mode: str):
        await self.storage.set_setting("delivery_mode", mode)

    # --- Night Mode Settings ---
    async def get_night_mode_enabled(self) -> bool:
        default_str = "true" if config.NIGHT_MODE_ENABLED else "false"
        val = await self.storage.get_setting("night_mode_enabled", default_str)
        return val.lower() in ("true", "1", "yes")

    async def update_night_mode_enabled(self, enabled: bool):
        await self.storage.set_setting("night_mode_enabled", "true" if enabled else "false")

    async def get_night_start_hour(self) -> int:
        val = await self.storage.get_setting("night_start_hour", str(config.NIGHT_START_HOUR))
        return int(val)

    async def update_night_start_hour(self, hour: int):
        await self.storage.set_setting("night_start_hour", str(hour))

    async def get_night_end_hour(self) -> int:
        val = await self.storage.get_setting("night_end_hour", str(config.NIGHT_END_HOUR))
        return int(val)

    async def update_night_end_hour(self, hour: int):
        await self.storage.set_setting("night_end_hour", str(hour))

    # --- UI & Bot State Settings ---
    async def get_master_chat_id(self) -> int:
        val = await self.storage.get_setting("master_chat_id")
        return int(val) if val else config.MASTER_CHAT_ID

    async def update_master_chat_id(self, chat_id: int):
        await self.storage.set_setting("master_chat_id", str(chat_id))

    async def get_last_ui_msg_id(self) -> int:
        val = await self.storage.get_setting("last_ui_msg_id")
        if not val:
            val = await self.storage.get_setting("last_status_msg_id")
        return int(val) if val else 0

    async def update_last_ui_msg_id(self, msg_id: int):
        await self.storage.set_setting("last_ui_msg_id", str(msg_id))

    # --- AI & Stats Settings ---
    async def get_stats_total_processed(self) -> int:
        val = await self.storage.get_setting("stats_total_processed", "0")
        return int(val)

    async def get_stats_spam_blocked(self) -> int:
        val = await self.storage.get_setting("stats_spam_blocked", "0")
        return int(val)

    async def get_ai_text_chat_enabled(self) -> bool:
        val = await self.storage.get_setting("ai_text_chat_enabled", "true")
        return val.lower() in ("true", "1", "yes")

    async def update_ai_text_chat_enabled(self, enabled: bool):
        await self.storage.set_setting("ai_text_chat_enabled", "true" if enabled else "false")

    async def get_ai_suggestions_enabled(self) -> bool:
        val = await self.storage.get_setting("ai_suggestions_enabled", "true")
        return val.lower() in ("true", "1", "yes")

    async def update_ai_suggestions_enabled(self, enabled: bool):
        await self.storage.set_setting("ai_suggestions_enabled", "true" if enabled else "false")

    async def get_ai_category_filters(self) -> dict:
        import json
        val = await self.storage.get_setting("ai_category_filters")
        if val:
            try:
                return json.loads(val)
            except:
                pass
        # Default: spam and bullshit are filtered (False = filtered, True = passed)
        return {
            "spam": False,
            "bullshit": False,
            "urgent": True,
            "important": True,
            "gov_debt": True,
            "gov_service": True,
            "news": True,
            "media": True,
            "general": True,
            "politics": True,
            "interesting": True
        }

    async def update_ai_category_filters(self, filters: dict):
        import json
        await self.storage.set_setting("ai_category_filters", json.dumps(filters))

    async def toggle_ai_category_filter(self, category: str):
        filters = await self.get_ai_category_filters()
        # Toggle the boolean value
        if category in filters:
            filters[category] = not filters[category]
        else:
            # If not in dict, assume default was True, so toggle to False
            filters[category] = False
        await self.update_ai_category_filters(filters)

    async def get_ai_max_rpm(self) -> int:
        val = await self.storage.get_setting("ai_max_rpm", str(config.AI_MAX_RPM))
        return max(int(val), 15)

    async def update_ai_max_rpm(self, rpm: int):
        await self.storage.set_setting("ai_max_rpm", str(rpm))

    async def get_ai_batch_chunk_size(self) -> int:
        val = await self.storage.get_setting("ai_batch_chunk_size", str(config.AI_BATCH_CHUNK_SIZE))
        return int(val)

    async def update_ai_batch_chunk_size(self, size: int):
        await self.storage.set_setting("ai_batch_chunk_size", str(size))
