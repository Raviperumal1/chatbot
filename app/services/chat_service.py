import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models import Channel, Conversation, Message, SenderRole, Lead
from app.chat.lead_capture import process_lead_capture, get_session, Stage
from app.chat.engine import _mark_notified_if_new, send_enquiry_email_async
from app.rag.retriever import get_context
from app.llm.ollama_client import generate_reply, generate_reply_stream
import os

IST = timezone(timedelta(hours=5, minutes=30))
COMPANY_NAME = os.getenv("COMPANY_NAME", "Zenfuture Technologies")


class ChatService:
    @staticmethod
    def get_or_create_conversation(db: Session, channel: Channel, session_key: str,
                                   language: str = "en") -> Conversation:
        convo = db.query(Conversation).filter(
            Conversation.channel == channel,
            Conversation.session_key == session_key
        ).with_for_update().first()

        if not convo:
            convo = Conversation(
                channel=channel,
                session_key=session_key,
                language=language,
                status="active"
            )
            db.add(convo)
            db.commit()
            db.refresh(convo)

        return convo

    @staticmethod
    def get_conversation_history(db: Session, conversation_id, limit: int = 10) -> list[dict]:
        msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        history = []
        for m in reversed(msgs):
            role = "assistant" if m.role == SenderRole.bot else "user"
            history.append({"role": role, "content": m.content})
        return history

    @staticmethod
    def handle_incoming_message(
            db: Session,
            channel: Channel,
            session_key: str,
            user_message: str,
            language: str = "en",
            external_message_id: str | None = None
    ) -> tuple[str, dict]:
        """
        Unified method to handle an incoming message from any channel.
        Returns a tuple: (reply_text, metadata_dict)
        """
        # Idempotency Check
        if external_message_id:
            existing = db.query(Message).filter(Message.external_message_id == external_message_id).first()
            if existing:
                return "", {"status": "duplicate", "message": "Message already processed."}

        convo = ChatService.get_or_create_conversation(db, channel, session_key, language)
        history = ChatService.get_conversation_history(db, convo.id, limit=10)

        # Save User Message
        user_msg_id = uuid.uuid4()
        user_msg = Message(
            message_uuid=user_msg_id,
            conversation_id=convo.id,
            role=SenderRole.user,
            channel=channel,
            external_message_id=external_message_id,
            content=user_message,
        )
        db.add(user_msg)
        convo.last_message_at = datetime.now(IST)
        convo.updated_at = datetime.now(IST)
        db.commit()

        metadata_dict = {"conversation_id": str(convo.id), "user_message_id": str(user_msg_id)}

        # Workflow execution
        reply_text = ""
        stage_val = Stage.CHATTING.value

        if channel == Channel.website:
            # Execute lead capture logic
            reply, still_capturing = process_lead_capture(convo, user_message, COMPANY_NAME)
            if still_capturing:
                reply_text = reply
                stage_val = get_session(convo)["stage"]
            else:
                # Lead is captured, trigger email and LLM
                session = get_session(convo)
                if not convo.lead_id:
                    email = session.get("email")
                    if email:
                        # Find existing lead by email
                        existing_lead = db.query(Lead).filter(Lead.email == email).first()
                        if existing_lead:
                            convo.lead_id = existing_lead.id
                        else:
                            new_lead = Lead(
                                name=session.get("name"),
                                email=email,
                                phone=session.get("phone"),
                                source=channel
                            )
                            db.add(new_lead)
                            db.flush()
                            convo.lead_id = new_lead.id
                        db.commit()

                if _mark_notified_if_new(session_key):
                    send_enquiry_email_async(session, user_message)

                context = get_context(user_message)
                reply_text = generate_reply(user_message, context, history=history)
        else:
            # WhatsApp or other channel skips lead capture
            context = get_context(user_message)
            reply_text = generate_reply(user_message, context, history=history)

        # Save Assistant Message
        bot_msg_id = uuid.uuid4()
        bot_msg = Message(
            message_uuid=bot_msg_id,
            conversation_id=convo.id,
            role=SenderRole.bot,
            channel=channel,
            content=reply_text,
        )
        db.add(bot_msg)
        convo.last_message_at = datetime.now(IST)
        convo.updated_at = datetime.now(IST)
        db.commit()

        metadata_dict["assistant_message_id"] = str(bot_msg_id)
        metadata_dict["stage"] = stage_val

        return reply_text, metadata_dict

    @staticmethod
    def stream_incoming_message(
            db: Session,
            channel: Channel,
            session_key: str,
            user_message: str,
            language: str = "en",
            external_message_id: str | None = None
    ):
        convo = ChatService.get_or_create_conversation(db, channel, session_key, language)
        history = ChatService.get_conversation_history(db, convo.id, limit=10)

        if user_message.strip():
            user_msg_id = uuid.uuid4()
            user_msg = Message(
                message_uuid=user_msg_id,
                conversation_id=convo.id,
                role=SenderRole.user,
                channel=channel,
                external_message_id=external_message_id,
                content=user_message,
            )
            db.add(user_msg)
            convo.last_message_at = datetime.now(IST)
            convo.updated_at = datetime.now(IST)
            db.commit()

        if channel == Channel.website:
            reply, still_capturing = process_lead_capture(convo, user_message, COMPANY_NAME)
            if still_capturing:
                bot_msg_id = uuid.uuid4()
                bot_msg = Message(
                    message_uuid=bot_msg_id,
                    conversation_id=convo.id,
                    role=SenderRole.bot,
                    channel=channel,
                    content=reply,
                )
                db.add(bot_msg)
                convo.last_message_at = datetime.now(IST)
                convo.updated_at = datetime.now(IST)
                db.commit()
                yield reply
                return

            session = get_session(convo)
            if not convo.lead_id:
                email = session.get("email")
                if email:
                    existing_lead = db.query(Lead).filter(Lead.email == email).first()
                    if existing_lead:
                        convo.lead_id = existing_lead.id
                    else:
                        new_lead = Lead(
                            name=session.get("name"),
                            email=email,
                            phone=session.get("phone"),
                            source=channel
                        )
                        db.add(new_lead)
                        db.flush()
                        convo.lead_id = new_lead.id
                    db.commit()

            if _mark_notified_if_new(session_key):
                send_enquiry_email_async(session, user_message)

        context = get_context(user_message)
        full_reply_parts = []
        for chunk in generate_reply_stream(user_message, context, history=history):
            full_reply_parts.append(chunk)
            yield chunk

        full_reply = "".join(full_reply_parts).strip()
        bot_msg_id = uuid.uuid4()
        bot_msg = Message(
            message_uuid=bot_msg_id,
            conversation_id=convo.id,
            role=SenderRole.bot,
            channel=channel,
            content=full_reply,
        )
        db.add(bot_msg)
        convo.last_message_at = datetime.now(IST)
        convo.updated_at = datetime.now(IST)
        db.commit()
