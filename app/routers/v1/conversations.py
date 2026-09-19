import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Conversation, Message
from app.schemas_v1 import (
    StandardResponse, 
    StandardMeta, 
    StandardError,
    ConversationDetail,
    MessageDetail
)

router = APIRouter(prefix="/conversations", tags=["v1-conversations"])

@router.get("", response_model=StandardResponse)
def list_conversations(request: Request, channel: str = Query(None), db: Session = Depends(get_db)):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    meta = StandardMeta(request_id=req_id)
    
    query = db.query(Conversation)
    if channel:
        query = query.filter(Conversation.channel == channel)
        
    conversations = query.order_by(Conversation.updated_at.desc()).all()
    
    data = [ConversationDetail.model_validate(c).model_dump() for c in conversations]
    return StandardResponse(success=True, data={"conversations": data}, meta=meta)

@router.get("/{conversation_id}", response_model=StandardResponse)
def get_conversation(conversation_id: str, request: Request, db: Session = Depends(get_db)):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    meta = StandardMeta(request_id=req_id)
    
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except:
        conv_uuid = None
        
    convo = db.query(Conversation).filter(
        (Conversation.id == conv_uuid) | (Conversation.session_key == conversation_id)
    ).first()
    
    if not convo:
        return StandardResponse(
            success=False,
            error=StandardError(code="CONVERSATION_NOT_FOUND", message="Conversation not found."),
            meta=meta
        )
        
    data = ConversationDetail.model_validate(convo).model_dump()
    return StandardResponse(success=True, data={"conversation": data}, meta=meta)

@router.get("/{conversation_id}/messages", response_model=StandardResponse)
def get_conversation_messages(
    conversation_id: str, 
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    meta = StandardMeta(request_id=req_id)
    
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except:
        conv_uuid = None
        
    convo = db.query(Conversation).filter(
        (Conversation.id == conv_uuid) | (Conversation.session_key == conversation_id)
    ).first()
    
    if not convo:
        return StandardResponse(
            success=False,
            error=StandardError(code="CONVERSATION_NOT_FOUND", message="Conversation not found."),
            meta=meta
        )
        
    messages_query = db.query(Message).filter(Message.conversation_id == convo.id).order_by(Message.created_at.asc())
    
    total = messages_query.count()
    messages = messages_query.offset((page - 1) * page_size).limit(page_size).all()
    
    data = {
        "messages": [MessageDetail.model_validate(m).model_dump() for m in messages],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total
        }
    }
    
    return StandardResponse(success=True, data=data, meta=meta)
