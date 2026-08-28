from pydantic import BaseModel, Field
from typing import Dict

class UserSettings(BaseModel):
    delivery_mode: str = "digest"
    digest_interval_minutes: int = 60
    timezone_offset: int = 3
    auto_delete_delay_hours: int = 1
    night_mode_enabled: bool = False
    night_start_hour: int = 23
    night_end_hour: int = 7
    ai_text_chat_enabled: bool = True
    ai_suggestions_enabled: bool = True
    ai_category_filters: Dict[str, bool] = Field(default_factory=dict)
