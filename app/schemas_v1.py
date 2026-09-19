from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

# Common Standard Response Schema
class StandardMeta(BaseModel):
    request_id: str

class StandardError(BaseModel):
    code: str
    message: str

class StandardResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[StandardError] = None
    meta: StandardMeta

# API V1 Request Schemas
class ChatRequestV1(BaseModel):
    conversation_id: Optional[str] = Field(default=None, description="Provide an existing UUID or None for a new conversation.")
    message: str = Field(..., min_length=1, max_length=2000)
    channel: str = Field(..., description="E.g., 'web', 'whatsapp'")
    language: str = Field(default="en")
    external_message_id: Optional[str] = None
    external_user_id: Optional[str] = None

# Message Output Schema
class MessageDetail(BaseModel):
    message_uuid: UUID
    conversation_id: UUID
    role: str
    channel: str
    content: str
    message_type: str
    message_metadata: Optional[Dict[str, Any]] = None
    external_message_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# Conversation Output Schema
class ConversationDetail(BaseModel):
    id: UUID
    channel: str
    status: str
    language: str
    external_user_id: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="metadata")
    started_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        populate_by_name = True

class ConversationMessagesResponse(BaseModel):
    messages: List[MessageDetail]

class ConversationListResponse(BaseModel):
    conversations: List[ConversationDetail]
