from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel


class WebsiteChatRequest(BaseModel):
    session_id: str  # generated client-side (e.g. localStorage UUID) per visitor
    message: str


class WebsiteChatResponse(BaseModel):
    reply: str
    stage: str  # e.g. "collecting_name" | "collecting_email" | "collecting_phone" | "chat"


class LeadOut(BaseModel):
    id: UUID
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class LeadDetailOut(LeadOut):
    messages: List[MessageOut] = []
