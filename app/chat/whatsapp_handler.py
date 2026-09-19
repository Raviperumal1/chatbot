import logging
from sqlalchemy.orm import Session

from app.services.chat_service import ChatService
from app.database import SessionLocal
from app.models import Channel
from app.utils.whatsapp_client import (
    send_whatsapp_text,
)

logger = logging.getLogger(__name__)


def process_whatsapp_event(
    payload: dict,
    db: Session | None = None
) -> None:

    close_db = False

    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        entries = payload.get("entry", [])

        for entry in entries:

            changes = entry.get("changes", [])

            for change in changes:

                value = change.get("value", {})

                # ---------------------------------
                # Ignore delivery/read statuses
                # ---------------------------------

                messages = value.get("messages", [])

                if not messages:
                    continue

                # ---------------------------------
                # Process every incoming message
                # ---------------------------------

                for message in messages:

                    sender_phone = message.get("from")

                    if not sender_phone:
                        continue

                    message_type = message.get("type")

                    # For now process text only
                    if message_type != "text":
                        continue

                    user_message = (
                        message
                        .get("text", {})
                        .get("body", "")
                        .strip()
                    )

                    if not user_message:
                        continue

                    print("\n========== WHATSAPP MESSAGE ==========")
                    print("FROM:", sender_phone)
                    print("MESSAGE:", user_message)
                    print("======================================\n")

                    message_id = message.get("id")
                    if message_id:
                        try:
                            from app.routers.whatsapp_chat import mark_read_with_typing
                            mark_read_with_typing(message_id)
                        except Exception as e:
                            logger.error(f"Error calling mark_read_with_typing: {e}")

                    # ---------------------------------
                    # Send directly to RAG + LLM
                    # (skip lead capture for WhatsApp)
                    # ---------------------------------

                    reply_text, _ = ChatService.handle_incoming_message(
                        db=db,
                        channel=Channel.whatsapp,
                        session_key=sender_phone,
                        user_message=user_message,
                        external_message_id=message.get("id")
                    )
                    
                    if not reply_text:
                        # Duplicate message, skip replying
                        continue

                    print("\n========== CHATBOT REPLY ==========")
                    print("REPLY:", reply_text)
                    print("===================================\n")

                    # ---------------------------------
                    # Return response to WhatsApp
                    # ---------------------------------

                    result = send_whatsapp_text(
                        to=sender_phone,
                        text=reply_text
                    )

                    print("\n========== META SEND TEXT ==========")
                    print(result)
                    print("===================================\n")

    except Exception as e:

        logger.error(
            f"WhatsApp webhook error: {e}",
            exc_info=True
        )

    finally:

        if close_db:
            db.close()


def handle_whatsapp_demo_message(db: Session, phone: str, name: str, user_text: str, button_id: str | None = None) -> dict:
    """
    Direct synchronous handler for the web WhatsApp Simulator.
    Runs pipeline directly using the unified ChatService.
    """
    user_text = (user_text or "").strip()

    # Send directly to LLM
    if user_text:
        reply_text, _ = ChatService.handle_incoming_message(
            db=db,
            channel=Channel.whatsapp,
            session_key=phone,
            user_message=user_text
        )
    else:
        reply_text = "Please ask a question."

    return {
        "type": "text",
        "reply": reply_text
    }
