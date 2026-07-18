import re
from enum import Enum


class Stage(str, Enum):
    ASK_NAME = "ask_name"
    ASK_EMAIL = "ask_email"
    ASK_PHONE = "ask_phone"
    CHATTING = "chatting"


EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_RE = re.compile(r"[\d+][\d\s\-()]{6,}\d")

# session_key -> {"stage": Stage, "name": str, "email": str, "phone": str}
SESSION_STORE: dict[str, dict] = {}

WELCOME_MESSAGE = "Greetings from Zenfuture. Let's get started. May I have your name?"

ASK_EMAIL_MESSAGE = "Thanks, {name}. What is your work email?"

ASK_PHONE_MESSAGE = "And a contact number for a quick follow-up?"

READY_MESSAGE = (
    "Configuration complete. How can I help you scale with Zenfuture today, {name}? "
    "I can provide details on our tech stack, custom solutions, or schedule a demo."
)

INVALID_EMAIL_MESSAGE = "That email format doesn't look right. Please provide a valid address."

INVALID_PHONE_MESSAGE = "Please enter a valid phone number so we can ensure connectivity."


def get_session(session_key: str) -> dict:
    if session_key not in SESSION_STORE:
        SESSION_STORE[session_key] = {
            "stage": Stage.ASK_NAME,
            "name": None,
            "email": None,
            "phone": None,
        }
    return SESSION_STORE[session_key]


def process_lead_capture(session_key: str, message: str, company_name: str) -> tuple[str, bool]:
    """
    Advances the lead-capture state machine by one turn.

    Returns (reply_text, is_still_capturing).
    is_still_capturing = True means the caller should NOT run the RAG/LLM step
    yet - we're still collecting name/email/phone.
    """
    session = get_session(session_key)
    stage = session["stage"]
    message = message.strip()

    if stage == Stage.ASK_NAME:
        # First message ever in this session: nothing to validate, just greet.
        if session["name"] is None and message == "":
            return WELCOME_MESSAGE.format(company_name=company_name), True
        session["name"] = message or "there"
        session["stage"] = Stage.ASK_EMAIL
        return ASK_EMAIL_MESSAGE.format(name=session["name"]), True

    if stage == Stage.ASK_EMAIL:
        if not EMAIL_RE.search(message):
            return INVALID_EMAIL_MESSAGE, True
        session["email"] = EMAIL_RE.search(message).group(0)
        session["stage"] = Stage.ASK_PHONE
        return ASK_PHONE_MESSAGE, True

    if stage == Stage.ASK_PHONE:
        if not PHONE_RE.search(message):
            return INVALID_PHONE_MESSAGE, True
        session["phone"] = PHONE_RE.search(message).group(0)
        session["stage"] = Stage.CHATTING
        return READY_MESSAGE.format(name=session["name"]), True

    # Stage.CHATTING - lead already captured, let the caller run the RAG/LLM step
    return "", False
