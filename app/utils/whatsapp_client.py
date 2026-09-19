import logging
import re
import requests
from typing import Any

import os

logger = logging.getLogger(__name__)

WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v25.0")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "1261531117043165")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")


def _get_api_url() -> str:
    version = WHATSAPP_API_VERSION or "v19.0"
    phone_id = WHATSAPP_PHONE_NUMBER_ID

    print(f"phone id: {phone_id} , version: {version}")

    print(f"https://graph.facebook.com/{version}/{phone_id}/messages")
    return f"https://graph.facebook.com/{version}/{phone_id}/messages"


def _get_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _normalize_phone_number(phone: str) -> str:
    """Normalize a WhatsApp recipient number for Meta Cloud API.

    Meta expects the recipient phone number in international digits only,
    without a leading plus sign.
    """
    cleaned = re.sub(r"[^0-9+]", "", phone or "")
    if not cleaned:
        return phone
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    elif cleaned.startswith("00"):
        cleaned = cleaned[2:]
    return cleaned


def send_whatsapp_text(to: str, text: str) -> dict[str, Any]:
    """
    Send a plain text message to a WhatsApp user via Meta WhatsApp Cloud API.
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.warning(
            f"[MOCK WHATSAPP SEND to {to}]: {text}\n"
            "(Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID in .env to send real messages)"
        )
        return {"status": "mocked", "to": to, "text": text}

    url = _get_api_url()
    recipient = _normalize_phone_number(to)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }

    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to send WhatsApp text to {to}: {e}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"Response body: {e.response.text}")
        return {"error": str(e)}


def send_whatsapp_interactive_buttons(
    to: str,
    body: str,
    buttons: list[dict[str, str]],
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """
    Send an interactive button message to a WhatsApp user (up to 3 buttons).
    
    `buttons` should be a list of dicts: `[{"id": "btn_1", "title": "Title 1"}, ...]`
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.warning(
            f"[MOCK WHATSAPP BUTTONS to {to}]: {body} | Buttons: {[b['title'] for b in buttons]}"
        )
        return {"status": "mocked", "to": to, "body": body, "buttons": buttons}

    formatted_buttons = []
    for btn in buttons[:3]:  # WhatsApp API limits to max 3 reply buttons
        formatted_buttons.append(
            {
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20],  # Title limit is 20 chars
                },
            }
        )

    action: dict[str, Any] = {"buttons": formatted_buttons}

    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": action,
    }

    if header:
        interactive["header"] = {"type": "text", "text": header[:60]}
    if footer:
        interactive["footer"] = {"text": footer[:60]}

    recipient = _normalize_phone_number(to)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "interactive",
        "interactive": interactive,
    }

    url = _get_api_url()
    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to send WhatsApp interactive buttons to {to}: {e}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"Response body: {e.response.text}")
        return {"error": str(e)}


def send_whatsapp_interactive_list(
    to: str,
    body: str,
    button_text: str,
    sections: list[dict[str, Any]],
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """
    Send an interactive list message to a WhatsApp user.
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.warning(f"[MOCK WHATSAPP LIST to {to}]: {body}")
        return {"status": "mocked", "to": to, "body": body}

    interactive: dict[str, Any] = {
        "type": "list",
        "body": {"text": body},
        "action": {
            "button": button_text[:20],
            "sections": sections,
        },
    }

    if header:
        interactive["header"] = {"type": "text", "text": header[:60]}
    if footer:
        interactive["footer"] = {"text": footer[:60]}

    recipient = _normalize_phone_number(to)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "interactive",
        "interactive": interactive,
    }

    url = _get_api_url()
    try:
        response = requests.post(url, headers=_get_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to send WhatsApp interactive list to {to}: {e}")
        return {"error": str(e)}
