from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import uuid
from sqlalchemy.orm import Session

from app.services.chat_service import ChatService
from app.services.conversation_metadata import serialize_conversation_for_api
from app.database import get_db
from app.models import Channel
from app.models import Lead, Conversation
from app.schemas import WebsiteChatRequest, WebsiteChatResponse, ChatLoadResponse

router = APIRouter(prefix="/api/chat/website", tags=["website-chat"])


@router.post("", response_model=WebsiteChatResponse)
def website_chat(
    payload: WebsiteChatRequest,
    stream: bool = Query(False, description="Stream the bot response as chunks"),
    db: Session = Depends(get_db),
):
    if stream:
        return StreamingResponse(
            ChatService.stream_incoming_message(db, Channel.website, payload.session_id, payload.message),
            media_type="text/plain; charset=utf-8",
        )

    reply_text, metadata_dict = ChatService.handle_incoming_message(db, Channel.website, payload.session_id, payload.message)
    stage = metadata_dict.get("stage", "chatting")
    print(f" reply: {reply_text}, stage: {stage}")
    return WebsiteChatResponse(reply=reply_text, stage=stage)


@router.get("/load", response_model=ChatLoadResponse)
def load_chat(session_id: str, db: Session = Depends(get_db)):
    """Load existing lead and conversation messages for this session/user."""
    convo = (
        db.query(Conversation)
        .filter(Conversation.channel == Channel.website, Conversation.session_key == session_id)
        .first()
    )
    if convo:
        data = serialize_conversation_for_api(convo)
        return ChatLoadResponse(**data)

    return ChatLoadResponse()
