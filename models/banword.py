from pydantic import BaseModel
from typing import Optional

class BanwordItem(BaseModel):
    id: Optional[int] = None
    word: str
    scope: str = "global"
    created_at: Optional[str] = None
