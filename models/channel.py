from pydantic import BaseModel
from typing import Optional

class TGChannelItem(BaseModel):
    id: Optional[int] = None
    username: str
    added_at: Optional[str] = None
