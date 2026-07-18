from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.chat.engine import handle_message
from app.database import get_db
from app.models import Channel
from app.schemas import WebsiteChatRequest, WebsiteChatResponse

router = APIRouter(prefix="/api/chat/website", tags=["website-chat"])


@router.post("", response_model=WebsiteChatResponse)
def website_chat(payload: WebsiteChatRequest, db: Session = Depends(get_db)):
    reply, stage = handle_message(db, Channel.website, payload.session_id, payload.message)
    return WebsiteChatResponse(reply=reply, stage=stage)
