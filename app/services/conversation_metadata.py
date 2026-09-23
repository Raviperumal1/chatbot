from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from app.models import Conversation, SenderRole, Message

IST = timezone(timedelta(hours=5, minutes=30))

class LeadMetadata(BaseModel):
    lead_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = "prospect"
    stage: Optional[str] = "ask_name"

class ConversationSummary(BaseModel):
    total_messages: int = 0
    user_messages: int = 0
    bot_messages: int = 0
    started_at: Optional[str] = None
    last_message_at: Optional[str] = None
    language: str = "en"

class ConversationInfo(BaseModel):
    conversation_id: Optional[str] = None
    visitor_id: Optional[str] = None
    channel: Optional[str] = None
    status: Optional[str] = None
    summary: ConversationSummary = Field(default_factory=ConversationSummary)
    messages: List[dict] = []

class ConversationMetadataModel(BaseModel):
    lead: LeadMetadata = Field(default_factory=LeadMetadata)
    conversation: ConversationInfo = Field(default_factory=ConversationInfo)

def _format_time(dt) -> Optional[str]:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None

def get_or_migrate_metadata(conversation: Conversation) -> dict:
    """
    Loads metadata and ensures it matches the exact requested JSON structure.
    """
    raw_meta = conversation.metadata_ or {}
    
    # Check if already in the new exact format
    if "conversation" in raw_meta and "summary" in raw_meta["conversation"]:
        return raw_meta
        
    # Migrate from older formats
    old_lead = raw_meta.get("lead", {})
    old_analytics = raw_meta.get("analytics", {})
    old_state = raw_meta.get("state", {})
    
    name = old_lead.get("name") or raw_meta.get("name")
    email = old_lead.get("email") or raw_meta.get("email")
    phone = old_lead.get("phone") or raw_meta.get("phone")
    stage = old_state.get("stage") or raw_meta.get("stage") or "ask_name"
    
    new_meta = ConversationMetadataModel(
        lead=LeadMetadata(
            lead_id=f"lead_{str(conversation.lead_id)[:8]}" if conversation.lead_id else None,
            name=name,
            email=email,
            phone=phone,
            status="captured" if email else "prospect",
            stage=stage
        ),
        conversation=ConversationInfo(
            conversation_id=f"conv_{str(conversation.id)[:8]}" if conversation.id else None,
            visitor_id=conversation.session_key,
            channel=conversation.channel.value if conversation.channel else None,
            status=conversation.status or "active",
            summary=ConversationSummary(
                total_messages=old_analytics.get("message_count", 0),
                user_messages=old_analytics.get("user_message_count", 0),
                bot_messages=old_analytics.get("assistant_message_count", 0),
                started_at=_format_time(conversation.started_at),
                last_message_at=_format_time(conversation.last_message_at),
                language=conversation.language or "en"
            ),
            messages=[]
        )
    ).model_dump(exclude_none=True)
    
    return new_meta

def _sync_messages_and_summary(conversation: Conversation, meta: dict):
    """Rebuilds the messages array and summary directly from the relational data to keep the JSON perfectly synced."""
    msgs = sorted(conversation.messages, key=lambda x: x.created_at.replace(tzinfo=None) if x.created_at else datetime.min)
    
    json_messages = []
    user_count = 0
    bot_count = 0
    
    for m in msgs:
        is_bot = m.role == SenderRole.bot
        if is_bot:
            bot_count += 1
        else:
            user_count += 1
            
        json_messages.append({
            "message_id": f"msg_{str(m.message_uuid)[:8]}",
            "role": "assistant" if is_bot else "user",
            "content": m.content,
            "message_type": m.message_type,
            "context": m.message_metadata or {},
            "timestamp": _format_time(m.created_at)
        })
        
    meta["conversation"]["messages"] = json_messages
    meta["conversation"]["summary"]["total_messages"] = len(msgs)
    meta["conversation"]["summary"]["user_messages"] = user_count
    meta["conversation"]["summary"]["bot_messages"] = bot_count
    meta["conversation"]["summary"]["started_at"] = _format_time(conversation.started_at)
    meta["conversation"]["summary"]["last_message_at"] = _format_time(conversation.last_message_at)

def update_lead_info(conversation: Conversation, name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None):
    meta = get_or_migrate_metadata(conversation)
    
    if name is not None: meta["lead"]["name"] = name
    if email is not None: 
        meta["lead"]["email"] = email.lower().strip()
        meta["lead"]["status"] = "captured"
    if phone is not None: meta["lead"]["phone"] = phone
        
    conversation.metadata_ = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(conversation, "metadata_")

def update_stage(conversation: Conversation, stage: str):
    meta = get_or_migrate_metadata(conversation)
    meta["lead"]["stage"] = stage
    conversation.metadata_ = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(conversation, "metadata_")

def increment_message_counts(conversation: Conversation, role: SenderRole):
    """Updates the JSON metadata column so it always contains the fully synced exact JSON payload requested."""
    meta = get_or_migrate_metadata(conversation)
    
    # Sync lead ID in case it was created recently
    meta["lead"]["lead_id"] = f"lead_{str(conversation.lead_id)[:8]}" if conversation.lead_id else None
    
    # Sync messages list and summary stats
    _sync_messages_and_summary(conversation, meta)
    
    conversation.metadata_ = meta
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(conversation, "metadata_")

def set_channel_metadata(conversation: Conversation, channel_key: str, data: dict):
    pass # Obsolete with exact schema, ignoring

def serialize_conversation_for_api(conversation: Conversation) -> dict:
    """The JSON in the DB is now perfectly formatted. Just return it!"""
    meta = get_or_migrate_metadata(conversation)
    _sync_messages_and_summary(conversation, meta) # guarantee latest sync
    return meta

