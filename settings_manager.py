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
        val = await self.storage.get_setting("night_mode_enabled", "false")
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
