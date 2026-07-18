from sqlalchemy.orm import Session

from app.chat.lead_capture import process_lead_capture, get_session, Stage
from app.config import settings
from app.llm.ollama_client import generate_reply
from app.models import Lead, Conversation, Message, Channel, SenderRole
from app.rag.retriever import get_context


def _get_or_create_conversation(db: Session, channel: Channel, session_key: str) -> Conversation:
    convo = (
        db.query(Conversation)
        .filter(Conversation.channel == channel, Conversation.session_key == session_key)
        .first()
    )
    if convo is None:
        convo = Conversation(channel=channel, session_key=session_key)
        db.add(convo)
        db.commit()
        db.refresh(convo)
    return convo


def _persist_message(db: Session, conversation: Conversation, role: SenderRole, content: str) -> None:
    db.add(Message(conversation_id=conversation.id, role=role, content=content))
    db.commit()


def _save_lead_if_ready(db: Session, conversation: Conversation, channel: Channel, session_key: str) -> None:
    """Once name/email/phone are all captured, create the Lead record and link it."""
    session = get_session(session_key)
    if conversation.lead_id is not None:
        return
    if session["name"] and session["email"] and session["phone"]:
        lead = Lead(
            name=session["name"],
            email=session["email"],
            phone=session["phone"],
            source=channel,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)
        conversation.lead_id = lead.id
        db.commit()


def handle_message(db: Session, channel: Channel, session_key: str, user_message: str) -> tuple[str, str]:
    """
    Main entry point used by both the website .

    Returns (reply_text, stage) where stage is one of the Stage enum values
    (as a string) so callers (e.g. the website widget) can adapt the UI if needed.
    """
    conversation = _get_or_create_conversation(db, channel, session_key)

    if user_message.strip():
        _persist_message(db, conversation, SenderRole.user, user_message)

    reply, still_capturing = process_lead_capture(session_key, user_message, settings.company_name)

    if still_capturing:
        _save_lead_if_ready(db, conversation, channel, session_key)
        _persist_message(db, conversation, SenderRole.bot, reply)
        stage = get_session(session_key)["stage"]
        return reply, stage.value

    # Lead already captured -> answer the actual question via RAG + local LLM
    context = get_context(user_message)
    reply = generate_reply(user_message, context)
    _persist_message(db, conversation, SenderRole.bot, reply)
    return reply, Stage.CHATTING.value
