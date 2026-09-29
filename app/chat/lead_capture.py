

from __future__ import annotations

import logging
import re
from enum import Enum
from functools import lru_cache

import requests

from app.models import Conversation
from app.services.conversation_metadata import get_or_migrate_metadata, update_lead_info, update_stage
from app.services.email_validation import validate_email_address

logger = logging.getLogger(__name__)


class Stage(str, Enum):
    ASK_NAME = "ask_name"
    ASK_EMAIL = "ask_email"
    ASK_PHONE = "ask_phone"
    CHATTING = "chatting"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# Unanchored on purpose: pulls an email out of free-form text like
# "my email is tharun@infogymka.in" instead of demanding the message be
# *exactly* the email and nothing else.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Matches a 10-digit Indian mobile number (starts 6-9), with an optional
# "+91"/"91" prefix, embedded anywhere in the (whitespace/punctuation
# stripped) text. Group 1 is always the clean 10-digit number.
PHONE_RE = re.compile(r"(?:\+?91)?([6-9]\d{9})")

MAX_NAME_LENGTH = 80
MAX_INPUT_LENGTH = 320  # generous upper bound for a single email/phone reply

# ---------------------------------------------------------------------------
# Disposable-email checking
# ---------------------------------------------------------------------------

# Domains you want blocked regardless of what the public API says (e.g. a
# domain you've identified as a lead-farm, competitor, or spam source).
# The public disposable-email API only knows about well-known throwaway
# services (mailinator, tempmail, ...) - it can't and won't block a domain
# just because it's obscure or newly registered, so this is the escape
# hatch for everything else.
BANNED_DOMAINS: set[str] = set()

_DISPOSABLE_API_URL = "https://disposable.debounce.io/"
_DISPOSABLE_API_TIMEOUT_S = 3


@lru_cache(maxsize=512)
def _check_disposable_api(domain: str) -> bool:
    """Queries the debounce.io disposable-domain API. Cached per-domain
    for the lifetime of the process, since the same domain is checked
    repeatedly across different leads and the result rarely changes."""
    try:
        response = requests.get(
            _DISPOSABLE_API_URL,
            params={"domain": domain},
            timeout=_DISPOSABLE_API_TIMEOUT_S,
        )
        response.raise_for_status()
        data = response.json()
        disposable = data.get("disposable")
        # The API has been observed to return either the string "true"/"false"
        # or a real JSON boolean depending on endpoint/version - handle both.
        return disposable is True or disposable == "true"
    except Exception:
        # Network hiccup or API outage: log it so it's visible in monitoring,
        # but don't block a legitimate lead over a third-party API being down.
        logger.warning("Disposable-email API check failed for domain=%s", domain, exc_info=True)
        return False


def is_disposable_email(email: str) -> bool:
    """Returns True if the email should be rejected: either it's on our
    own BANNED_DOMAINS list, or the public API flags the domain as a
    known throwaway/disposable provider."""
    if "@" not in email:
        return False

    domain = email.rsplit("@", 1)[-1].strip().lower()
    if not domain:
        return False

    if domain in BANNED_DOMAINS:
        return True

    return _check_disposable_api(domain)


def _extract_email(text: str) -> str | None:
    match = EMAIL_RE.search(text)
    return match.group(0).lower() if match else None


def _extract_phone(text: str) -> str | None:
    cleaned = re.sub(r"[\s\-()]", "", text)
    match = PHONE_RE.search(cleaned)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------

WELCOME_MESSAGE = "Welcome to {company_name}! May I know your name?"

ASK_EMAIL_MESSAGE = "Thank you, {name}. Could you please share your work email address?"

ASK_PHONE_MESSAGE = "Thank you! Could you also share your contact number?"

READY_MESSAGE = (
    "Thank you, {name}. You're all set! How can I help you today? "
    "I can help you explore our technology solutions, build a custom solution, "
    "or schedule a demo with our team."
)

INVALID_EMAIL_MESSAGE = "That email format doesn't look right. Please provide a valid address."

INVALID_PHONE_MESSAGE = "Please enter a valid 10-digit Indian phone number so we can ensure connectivity."

DISPOSABLE_EMAIL_MESSAGE = "Disposable email addresses are not allowed. Please use a valid work email."


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

def get_session(conversation: Conversation) -> dict:
    """Backward-compatible flat-dict view of lead info + stage. Used by
    the email sender and other legacy callers."""
    meta = get_or_migrate_metadata(conversation)
    lead = meta.get("lead", {})

    return {
        "name": lead.get("name"),
        "email": lead.get("email"),
        "phone": lead.get("phone"),
        "stage": lead.get("stage", Stage.ASK_NAME.value),
    }


def process_lead_capture(conversation: Conversation, message: str, company_name: str) -> tuple[str, bool]:
    """
    Advances the lead-capture state machine by one turn.

    Returns (reply_text, is_still_capturing). is_still_capturing = True
    means the caller should NOT run the RAG/LLM step yet - we're still
    collecting name/email/phone.
    """
    session = get_session(conversation)
    stage = session["stage"]
    message = message.strip()[:MAX_INPUT_LENGTH]

    if stage == Stage.ASK_NAME.value:
        if not message:
            if session["name"] is None:
                return WELCOME_MESSAGE.format(company_name=company_name), True
            # Defensive: stage is ASK_NAME but we already have a name on
            # file (shouldn't normally happen). Re-ask for email instead
            # of silently overwriting the stored name with "there".
            return ASK_EMAIL_MESSAGE.format(name=session["name"]), True

        name = message[:MAX_NAME_LENGTH]
        update_lead_info(conversation, name=name)
        update_stage(conversation, Stage.ASK_EMAIL.value)
        return ASK_EMAIL_MESSAGE.format(name=name), True

    if stage == Stage.ASK_EMAIL.value:
        candidate = _extract_email(message)
        if not candidate:
            return INVALID_EMAIL_MESSAGE, True

        # Real validation: RFC-compliant syntax + a live MX/DNS lookup to
        # confirm the domain can actually receive mail. Catches typos
        # (gmial.com) and dead/nonexistent domains that a regex can't.
        validation = validate_email_address(candidate, check_deliverability=True)
        if not validation.is_valid:
            if validation.suggestion:
                return f"That domain doesn't look deliverable. Did you mean @{validation.suggestion}?", True
            return INVALID_EMAIL_MESSAGE, True

        email = validation.normalized_email

        if is_disposable_email(email):
            return DISPOSABLE_EMAIL_MESSAGE, True

        update_lead_info(conversation, email=email)
        update_stage(conversation, Stage.ASK_PHONE.value)
        return ASK_PHONE_MESSAGE, True

    if stage == Stage.ASK_PHONE.value:
        phone = _extract_phone(message)
        if not phone:
            return INVALID_PHONE_MESSAGE, True

        update_lead_info(conversation, phone=phone)
        update_stage(conversation, Stage.CHATTING.value)
        return READY_MESSAGE.format(name=session.get("name") or "there"), True

    # Stage.CHATTING - lead already captured, let the caller run the RAG/LLM step.
    if message == "":
        return f"Welcome back, {session.get('name') or 'there'}! How can I assist you today?", True

    return "", False