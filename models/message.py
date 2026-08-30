from pydantic import BaseModel
from typing import Optional, List

class DeliveryStatus:
    PENDING = 0    # In buffer waiting for digest
    DELIVERED = 1  # Delivered to user (instant or in digest)
    FILTERED = 2   # Filtered/muted by rules or category filters

class MessageItem(BaseModel):
    msg_uid: str
    channel: str
    sender: str
    text: str
    category: str = "general"
    summary: str = ""
    action_required: bool = False
    suggested_reply: Optional[str] = None
    is_delivered: int = DeliveryStatus.PENDING
    created_at: Optional[str] = None

class AnalysisResult(BaseModel):
    msg_uid: str
    category: str
    summary: str
    action_required: bool
    suggested_reply: Optional[str] = None

class AnalysisBatchResponse(BaseModel):
    results: List[AnalysisResult]

class AudioAnalysisResult(BaseModel):
    transcription: str
    category: str
    summary: str
    action_required: bool
    suggested_reply: Optional[str] = None
