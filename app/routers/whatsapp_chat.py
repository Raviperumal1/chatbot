"""
WhatsApp Cloud API webhook integration — Zenfuture chatbot.

Handles Meta's webhook verification handshake, validates the
X-Hub-Signature-256 HMAC on every incoming event, and processes
messages asynchronously so Meta always gets a fast 200 ack.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass

import requests
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.chat.whatsapp_handler import (
    process_whatsapp_event,
    handle_whatsapp_demo_message,
)
from app.database import get_db

load_dotenv()

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v25.0")

# Set WHATSAPP_DEBUG_SIGNATURES=true in .env temporarily to log received vs
# expected signatures side by side. Leave off in normal operation.
DEBUG_SIGNATURES = os.getenv("WHATSAPP_DEBUG_SIGNATURES", "false").lower() == "true"


# ============================================================
# Configuration
# ============================================================

@dataclass(frozen=True)
class WhatsAppConfig:
    access_token: str | None
    phone_number_id: str | None
    verify_token: str | None
    app_secret: str

    @property
    def is_configured(self) -> bool:
        return bool(self.app_secret and self.phone_number_id and self.verify_token)

    @property
    def messages_url(self) -> str:
        return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{self.phone_number_id}/messages"


CONFIG = WhatsAppConfig(
    access_token=os.getenv("WHATSAPP_ACCESS_TOKEN"),
    phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip() or None,
    verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip() or None,
    app_secret=os.getenv("WHATSAPP_APP_SECRET", "").strip(),
)

if not CONFIG.is_configured:
    missing = [
        name
        for name, val in (
            ("WHATSAPP_APP_SECRET", CONFIG.app_secret),
            ("WHATSAPP_PHONE_NUMBER_ID", CONFIG.phone_number_id),
            ("WHATSAPP_VERIFY_TOKEN", CONFIG.verify_token),
        )
        if not val
    ]
    logger.warning(
        "WhatsApp is not fully configured — missing: %s. "
        "Webhook will reject everything with 403 until these are set.",
        ", ".join(missing),
    )

if not CONFIG.access_token:
    logger.warning("WHATSAPP_ACCESS_TOKEN is not configured — outbound sends will fail")


router = APIRouter(prefix="/api/chat/whatsapp", tags=["whatsapp-chat"])


# ============================================================
# Request models
# ============================================================

class WhatsAppDemoRequest(BaseModel):
    phone: str = "15551234567"
    name: str = "Visitor"
    message: str = ""
    button_id: str | None = None


# ============================================================
# Signature verification
# ============================================================

def verify_signature(payload: bytes, signature: str | None) -> bool:
    """Validate Meta's X-Hub-Signature-256 header using constant-time comparison."""

    if not CONFIG.app_secret:
        logger.error("No WHATSAPP_APP_SECRET configured — cannot verify signature")
        return False

    if not signature:
        logger.warning("No X-Hub-Signature-256 header present")
        return False

    if not signature.startswith("sha256="):
        logger.warning("Signature header missing sha256= prefix")
        return False

    expected_signature = (
        "sha256="
        + hmac.new(CONFIG.app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    )

    if DEBUG_SIGNATURES:
        logger.info("Received signature:  %s", signature)
        logger.info("Expected signature:  %s", expected_signature)

    return hmac.compare_digest(expected_signature, signature)


# ============================================================
# Webhook verification handshake (GET)
# ============================================================

@router.get("/webhook")
async def verify_webhook(
    mode: str | None = Query(None, alias="hub.mode"),
    token: str | None = Query(None, alias="hub.verify_token"),
    challenge: str | None = Query(None, alias="hub.challenge"),
):
    logger.info(
        "Webhook verification request: mode=%s token_ok=%s challenge_present=%s",
        mode,
        token == CONFIG.verify_token,
        bool(challenge),
    )

    if (
        mode == "subscribe"
        and CONFIG.verify_token
        and token == CONFIG.verify_token
        and challenge
    ):
        logger.info("Webhook verification succeeded")
        return Response(content=challenge, media_type="text/plain", status_code=200)

    logger.warning("Webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")


# ============================================================
# Incoming events (POST)
# ============================================================

@router.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    payload_bytes = await request.body()

    if not payload_bytes:
        raise HTTPException(status_code=400, detail="Empty payload")

    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_signature(payload_bytes, signature):
        logger.warning("Signature validation failed on /api/chat/whatsapp/webhook")
        raise HTTPException(status_code=403, detail="Signature verification failed")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Invalid JSON payload on webhook")
        raise HTTPException(status_code=400, detail="Invalid payload")

    logger.info("Webhook received: object=%s", payload.get("object"))

    # Hand off to background processing — Meta expects a fast 200 ack and
    # will retry aggressively (with exponential backoff) if it doesn't get one.
    background_tasks.add_task(process_whatsapp_event, payload)

    return {"status": "ok"}


# ============================================================
# Outbound sending
# ============================================================

def mark_read_with_typing(message_id: str) -> None:
    if not CONFIG.access_token:
        logger.warning("WHATSAPP_ACCESS_TOKEN not configured — skipping typing indicator")
        return

    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"}
    }

    headers = {
        "Authorization": f"Bearer {CONFIG.access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(CONFIG.messages_url, headers=headers, json=payload, timeout=5)
        logger.info("WhatsApp typing indicator: status=%s", response.status_code)
        response.raise_for_status()
    except Exception as exc:
        logger.error("WhatsApp typing indicator failed (non-fatal): %s", exc)

def send_whatsapp_text(phone: str, message: str) -> dict:
    if not CONFIG.access_token:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN is not configured")

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }

    headers = {
        "Authorization": f"Bearer {CONFIG.access_token}",
        "Content-Type": "application/json",
    }

    response = requests.post(CONFIG.messages_url, headers=headers, json=payload, timeout=30)

    logger.info("WhatsApp send: status=%s", response.status_code)
    response.raise_for_status()
    return response.json()


@router.post("/demo")
def whatsapp_demo_chat(req: WhatsAppDemoRequest, db: Session = Depends(get_db)):
    result = handle_whatsapp_demo_message(
        db,
        phone=req.phone,
        name=req.name,
        user_text=req.message,
        button_id=req.button_id,
    )

    logger.info("WhatsApp demo result generated")

    try:
        send_whatsapp_text(phone=req.phone, message=result["reply"])
        result["delivered"] = True
    except (requests.RequestException, RuntimeError) as exc:
        logger.error("WhatsApp demo send failed: %s", exc)
        result["delivered"] = False

    return result