import re
from enum import Enum
from app.models import Conversation
from app.services.conversation_metadata import get_or_migrate_metadata, update_lead_info, update_stage

class Stage(str, Enum):
    ASK_NAME = "ask_name"
    ASK_EMAIL = "ask_email"
    ASK_PHONE = "ask_phone"
    CHATTING = "chatting"

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_RE = re.compile(r"[\d+][\d\s\-()]{6,}\d")

WELCOME_MESSAGE = "Welcome to Zenfuture! May I know your name?"

ASK_EMAIL_MESSAGE = "Thank you, {name}. Could you please share your work email address?"

ASK_PHONE_MESSAGE = "Thank you! Could you also share your contact number?"

READY_MESSAGE = (
    "Thank you, {name}. You're all set! How can I help you today? "
    "I can help you explore our technology solutions, build a custom solution, "
    "or schedule a demo with our team."
)

INVALID_EMAIL_MESSAGE = "That email format doesn't look right. Please provide a valid address."

INVALID_PHONE_MESSAGE = "Please enter a valid phone number so we can ensure connectivity."


def get_session(conversation: Conversation) -> dict:
    """
    Backward-compatible method to get lead info and stage as a flat dict.
    Used by email sender and other legacy callers.
    """
    meta = get_or_migrate_metadata(conversation)
    lead = meta.get("lead", {})
    
    return {
        "name": lead.get("name"),
        "email": lead.get("email"),
        "phone": lead.get("phone"),
        "stage": lead.get("stage", Stage.ASK_NAME.value)
    }

def process_lead_capture(conversation: Conversation, message: str, company_name: str) -> tuple[str, bool]:
    """
    Advances the lead-capture state machine by one turn using the Conversation database record.

    Returns (reply_text, is_still_capturing).
    is_still_capturing = True means the caller should NOT run the RAG/LLM step
    yet - we're still collecting name/email/phone.
    """
    session = get_session(conversation)
    stage = session["stage"]
    message = message.strip()

    if stage == Stage.ASK_NAME.value:
        if session["name"] is None and message == "":
            return WELCOME_MESSAGE.format(company_name=company_name), True
        
        name = message or "there"
        update_lead_info(conversation, name=name)
        update_stage(conversation, Stage.ASK_EMAIL.value)
        return ASK_EMAIL_MESSAGE.format(name=name), True

    if stage == Stage.ASK_EMAIL.value:
        if not EMAIL_RE.search(message):
            return INVALID_EMAIL_MESSAGE, True
        
        email = EMAIL_RE.search(message).group(0)
        update_lead_info(conversation, email=email)
        update_stage(conversation, Stage.ASK_PHONE.value)
        return ASK_PHONE_MESSAGE, True

    if stage == Stage.ASK_PHONE.value:
        if not PHONE_RE.search(message):
            return INVALID_PHONE_MESSAGE, True
            
        phone = PHONE_RE.search(message).group(0)
        update_lead_info(conversation, phone=phone)
        update_stage(conversation, Stage.CHATTING.value)
        return READY_MESSAGE.format(name=session.get("name", "there")), True

    # Stage.CHATTING - lead already captured, let the caller run the RAG/LLM step
    if message == "":
        return f"Welcome back, {session.get('name', 'there')}! How can I assist you today?", True
        
    return "", False
