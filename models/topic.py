from pydantic import BaseModel
from typing import Optional

class NewsTopicItem(BaseModel):
    id: Optional[int] = None
    topic: str
    preference: str = "liked"  # "liked" or "disliked"
    created_at: Optional[str] = None
