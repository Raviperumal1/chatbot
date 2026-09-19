from sqlalchemy.orm import Session

from app.chat.lead_capture import process_lead_capture, get_session, Stage
import uuid
import os
from app.llm.ollama_client import generate_reply, generate_reply_stream

COMPANY_NAME = os.getenv("COMPANY_NAME", "Zenfuture Technologies")
from app.models import Lead, Conversation, Message, Channel, SenderRole
from app.rag.retriever import get_context


def _get_or_create_conversation(db: Session, channel: Channel, session_key: str) -> Conversation:
    convo = (
        db.query(Conversation)
        .filter(Conversation.channel == channel, Conversation.session_key == session_key)
        .with_for_update()
        .first()
    )
    if convo is None:
        convo = Conversation(channel=channel, session_key=session_key)
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # If session_key corresponds to an existing Lead (persistent user), link it.
    try:
        lead_id = uuid.UUID(session_key)
    except Exception:
        lead_id = None

    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead and convo.lead_id is None:
            convo.lead_id = lead.id
            db.commit()

    return convo


def _persist_message(
        db: Session,
        conversation: Conversation,
        role: SenderRole,
        content: str,
        message_type: str = "text",
        message_metadata: dict | None = None,
) -> None:
    # generate a stable message uuid for tracing
    message_uuid = uuid.uuid4()
    msg = Message(
        message_uuid=message_uuid,
        conversation_id=conversation.id,
        role=role,
        content=content,
        message_type=message_type,
        message_metadata=message_metadata,
    )
    db.add(msg)
    db.commit()


def _get_conversation_history(db: Session, conversation_id, limit: int = 10) -> list[dict]:
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


def _save_lead_if_ready(db: Session, conversation: Conversation, channel: Channel) -> None:
    """Once name/email/phone are all captured, create the Lead record and link it."""
    session = get_session(conversation)
    if conversation.lead_id is not None:
        return
    if session["name"] and session["email"] and session["phone"]:
        # If the client supplied a stable UUID as session_key, use it as Lead.id
        lead_kwargs = dict(
            name=session["name"],
            email=session["email"],
            phone=session["phone"],
            source=channel,
        )
        try:
            lead_id = uuid.UUID(conversation.session_key)
        except Exception:
            lead_id = None

        if lead_id:
            # avoid duplicate if lead already exists
            existing = db.query(Lead).filter(Lead.id == lead_id).first()
            if existing is None:
                lead = Lead(id=lead_id, **lead_kwargs)
                db.add(lead)
                db.commit()
                db.refresh(lead)
            else:
                lead = existing
        else:
            lead = Lead(**lead_kwargs)
            db.add(lead)
            db.commit()
            db.refresh(lead)

        conversation.lead_id = lead.id
        db.commit()


import os
import smtplib
import ssl
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# SMTP config (same pattern you already had)
# ---------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv(
    "SMTP_FROM",
    SMTP_USERNAME or "noreply@medqueue.example",
)
# Where enquiry notifications land - your team's inbox, NOT the lead's inbox.
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")

# ---------------------------------------------------------------------------
# In-memory "already notified" tracker
# ---------------------------------------------------------------------------
# Key: session_key -> True once the enquiry email has been sent for that
# session. Resets on process restart (acceptable tradeoff for no DB change).
_notified_sessions: set[str] = set()
_notified_lock = threading.Lock()


def _mark_notified_if_new(session_key: str) -> bool:
    """
    Atomically checks-and-marks a session as notified.
    Returns True if this call is the FIRST time (i.e. you should send the email).
    Returns False if it was already notified before (skip sending).
    """
    with _notified_lock:
        if session_key in _notified_sessions:
            return False
        _notified_sessions.add(session_key)
        return True


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def _build_enquiry_email_html(
    name: str,
    email: str,
    contact: str,
    first_question: str,
    company_name: str,
) -> str:
    """Build a clean, full-width, responsive HTML enquiry email."""

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>

<body style="
    margin:0;
    padding:0;
    background:#f5f6f8;
    font-family:Arial, Helvetica, sans-serif;
    color:#1f2937;
">

<table
    width="100%"
    cellpadding="0"
    cellspacing="0"
    border="0"
    style="
        width:100%;
        margin:0;
        padding:24px;
        background:#f5f6f8;
    "
>
    <tr>
        <td align="center">

            <!-- Full-width email container -->
            <table
                width="100%"
                cellpadding="0"
                cellspacing="0"
                border="0"
                style="
                    width:100%;
                    background:#ffffff;
                    border:1px solid #e5e7eb;
                    border-radius:8px;
                "
            >

                <!-- Header -->
                <tr>
                    <td style="
                        padding:24px 28px 20px;
                    ">

                        <div style="
                            font-size:20px;
                            line-height:28px;
                            font-weight:600;
                            color:#111827;
                        ">
                            New Website Enquiry
                        </div>

                        <div style="
                            margin-top:5px;
                            font-size:13px;
                            line-height:20px;
                            color:#6b7280;
                        ">
                            Received through {company_name} AI Assistant
                        </div>

                    </td>
                </tr>


                <!-- Divider -->
                <tr>
                    <td style="padding:0 28px;">
                        <div style="
                            height:1px;
                            background:#e5e7eb;
                        "></div>
                    </td>
                </tr>


                <!-- Customer Details -->
                <tr>
                    <td style="
                        padding:24px 28px 10px;
                    ">

                        <div style="
                            margin-bottom:14px;
                            font-size:13px;
                            line-height:18px;
                            font-weight:600;
                            color:#374151;
                        ">
                            Customer Details
                        </div>


                        <!-- Name -->
                        <table
                            width="100%"
                            cellpadding="0"
                            cellspacing="0"
                            border="0"
                            style="width:100%;"
                        >
                            <tr>
                                <td style="
                                    width:100px;
                                    padding:7px 0;
                                    font-size:14px;
                                    color:#6b7280;
                                    vertical-align:top;
                                ">
                                    Name
                                </td>

                                <td style="
                                    padding:7px 0;
                                    font-size:14px;
                                    font-weight:600;
                                    color:#111827;
                                    vertical-align:top;
                                ">
                                    {name}
                                </td>
                            </tr>
                        </table>


                        <!-- Email -->
                        <table
                            width="100%"
                            cellpadding="0"
                            cellspacing="0"
                            border="0"
                            style="width:100%;"
                        >
                            <tr>
                                <td style="
                                    width:100px;
                                    padding:7px 0;
                                    font-size:14px;
                                    color:#6b7280;
                                    vertical-align:top;
                                ">
                                    Email
                                </td>

                                <td style="
                                    padding:7px 0;
                                    font-size:14px;
                                    vertical-align:top;
                                ">
                                    <a
                                        href="mailto:{email}"
                                        style="
                                            color:#2563eb;
                                            text-decoration:none;
                                        "
                                    >
                                        {email}
                                    </a>
                                </td>
                            </tr>
                        </table>


                        <!-- Contact -->
                        <table
                            width="100%"
                            cellpadding="0"
                            cellspacing="0"
                            border="0"
                            style="width:100%;"
                        >
                            <tr>
                                <td style="
                                    width:100px;
                                    padding:7px 0;
                                    font-size:14px;
                                    color:#6b7280;
                                    vertical-align:top;
                                ">
                                    Contact
                                </td>

                                <td style="
                                    padding:7px 0;
                                    font-size:14px;
                                    font-weight:600;
                                    color:#111827;
                                    vertical-align:top;
                                ">
                                    {contact}
                                </td>
                            </tr>
                        </table>

                    </td>
                </tr>


                <!-- Enquiry -->
                <tr>
                    <td style="
                        padding:18px 28px 24px;
                    ">

                        <div style="
                            margin-bottom:10px;
                            font-size:13px;
                            line-height:18px;
                            font-weight:600;
                            color:#374151;
                        ">
                            Enquiry
                        </div>

                        <div style="
                            padding:14px 16px;
                            background:#f9fafb;
                            border:1px solid #e5e7eb;
                            border-radius:6px;
                            font-size:14px;
                            line-height:22px;
                            color:#374151;
                            word-break:break-word;
                        ">
                            {first_question}
                        </div>

                    </td>
                </tr>


                <!-- Reply Button -->
                <tr>
                    <td style="
                        padding:0 28px 28px;
                    ">

                        <a
                            href="mailto:{email}"
                            style="
                                display:inline-block;
                                padding:10px 18px;
                                background:#2563eb;
                                color:#ffffff;
                                font-size:13px;
                                line-height:18px;
                                font-weight:600;
                                text-decoration:none;
                                border-radius:5px;
                            "
                        >
                            Reply to {name}
                        </a>

                    </td>
                </tr>


                <!-- Footer -->
                <tr>
                    <td style="
                        padding:16px 28px;
                        border-top:1px solid #e5e7eb;
                        font-size:11px;
                        line-height:18px;
                        color:#9ca3af;
                    ">
                        Automated notification from
                        {company_name} AI Assistant.
                    </td>
                </tr>

            </table>

        </td>
    </tr>
</table>

</body>
</html>
"""
def send_enquiry_email(session: dict, first_question: str) -> None:

    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD:
        print("[email] SMTP not configured, skipping enquiry email")
        return
    if not NOTIFY_EMAIL:
        print("[email] NOTIFY_EMAIL not set, skipping enquiry email")
        return

    name = session.get("name") or "Unknown"
    email = session.get("email") or "Unknown"
    contact = session.get("phone") or "Unknown"
    company_name = COMPANY_NAME

    subject = f"New Enquiry — {name} started a conversation"

    html_body = _build_enquiry_email_html(name, email, contact, first_question, company_name)
    plain_body = (
        f"New enquiry from {name}\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Contact: {contact}\n\n"
        f"First question: {first_question}"
    )

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    # Attach plain text first (fallback), then HTML (preferred) - clients render the last part that they support.
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls(context=context)
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [NOTIFY_EMAIL], msg.as_string())
        print(f"[email] Enquiry email sent for lead: {email}")
    except Exception as e:
        print("[email] Enquiry email failed:", e)


def send_enquiry_email_async(session: dict, first_question: str) -> None:
    """
    Fire-and-forget wrapper so a slow SMTP server never delays the chat
    response. Safe to call from the request thread.
    """
    t = threading.Thread(
        target=send_enquiry_email,
        args=(session, first_question),
        daemon=True,
    )
    t.start()


def handle_message(
        db: Session,
        channel: Channel,
        session_key: str,
        user_message: str,
) -> tuple[str, str]:
    conversation = _get_or_create_conversation(db, channel, session_key)
    history = _get_conversation_history(db, conversation.id)

    if user_message.strip():
        _persist_message(db, conversation, SenderRole.user, user_message)

    reply, still_capturing = process_lead_capture(
        conversation, user_message, COMPANY_NAME
    )

    if still_capturing:
        # Still collecting name / email / contact -> never send email here.
        _save_lead_if_ready(db, conversation, channel)
        _persist_message(db, conversation, SenderRole.bot, reply)
        stage = get_session(conversation)["stage"]
        return reply, stage

    # --- Lead already captured -> this is a real question ---

    # Send the one-time enquiry email, only on the first question after
    # lead capture completes for this session.
    if _mark_notified_if_new(session_key):
        session = get_session(conversation)
        send_enquiry_email_async(session, user_message)

    context = get_context(user_message)
    reply = generate_reply(user_message, context)
    _persist_message(db, conversation, SenderRole.bot, reply)
    return reply, Stage.CHATTING.value


def stream_handle_message(
        db: Session,
        channel: Channel,
        session_key: str,
        user_message: str,
):
    conversation = _get_or_create_conversation(db, channel, session_key)
    history = _get_conversation_history(db, conversation.id)

    if user_message.strip():
        _persist_message(db, conversation, SenderRole.user, user_message)

    reply, still_capturing = process_lead_capture(
        conversation, user_message, COMPANY_NAME
    )

    if still_capturing:
        _save_lead_if_ready(db, conversation, channel)
        _persist_message(db, conversation, SenderRole.bot, reply)
        yield reply
        return

    if _mark_notified_if_new(session_key):
        session = get_session(conversation)
        send_enquiry_email_async(session, user_message)

    context = get_context(user_message)
    full_reply_parts = []
    for chunk in generate_reply_stream(user_message, context, history=history):
        full_reply_parts.append(chunk)
        yield chunk

    full_reply = "".join(full_reply_parts).strip()
    _persist_message(db, conversation, SenderRole.bot, full_reply)


def handle_whatsapp_message_direct(db: Session, session_key: str, user_message: str) -> str:
    conversation = _get_or_create_conversation(db, Channel.whatsapp, session_key)
    history = _get_conversation_history(db, conversation.id)

    if user_message.strip():
        _persist_message(db, conversation, SenderRole.user, user_message)

    # Skip lead capture entirely - go directly to RAG + LLM
    context = get_context(user_message)
    reply = generate_reply(user_message, context, history=history)
    _persist_message(db, conversation, SenderRole.bot, reply)

    return reply