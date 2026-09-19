import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Channel
from app.services.chat_service import ChatService
from app.schemas_v1 import StandardResponse, ChatRequestV1, StandardMeta, StandardError

router = APIRouter(prefix="/chat", tags=["v1-chat"])
logger = logging.getLogger(__name__)

@router.post("", response_model=StandardResponse)
def unified_chat(request: Request, payload: ChatRequestV1, db: Session = Depends(get_db)):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    meta = StandardMeta(request_id=req_id)
    
    try:
        channel_enum = Channel(payload.channel.lower())
    except ValueError:
        return StandardResponse(
            success=False,
            error=StandardError(code="INVALID_CHANNEL", message=f"Invalid channel '{payload.channel}'"),
            meta=meta
        )

    # Use session_key as conversation_id essentially if provided, else generate one
    session_key = payload.conversation_id or str(uuid.uuid4())

    try:
        reply_text, metadata_dict = ChatService.handle_incoming_message(
            db=db,
            channel=channel_enum,
            session_key=session_key,
            user_message=payload.message,
            language=payload.language,
            external_message_id=payload.external_message_id
        )
        
        if reply_text == "" and metadata_dict.get("status") == "duplicate":
            return StandardResponse(
                success=True,
                data={"status": "duplicate", "conversation_id": session_key},
                meta=meta
            )
            
        return StandardResponse(
            success=True,
            data={
                "conversation_id": metadata_dict.get("conversation_id", session_key),
                "message": {
                    "message_id": metadata_dict.get("assistant_message_id"),
                    "role": "assistant",
                    "message_type": "text",
                    "content": reply_text
                }
            },
            meta=meta
        )
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        return StandardResponse(
            success=False,
            error=StandardError(code="CHAT_ERROR", message="An error occurred processing the chat."),
            meta=meta
        )
