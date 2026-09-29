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
    MessageDetail,
    AdminConversationDetail,
    ConversationWithMessagesDetail
)
from sqlalchemy.orm import selectinload
from app.routers.leads import require_admin

router = APIRouter(prefix="/conversations", tags=["v1-conversations"], dependencies=[Depends(require_admin)])

@router.get("", response_model=StandardResponse)
def list_conversations(
    request: Request, 
    channel: str = Query(None),
    status: str = Query(None),
    visitor_id: str = Query(None),
    user_id: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    meta = StandardMeta(request_id=req_id)
    query = db.query(Conversation).options(selectinload(Conversation.lead), selectinload(Conversation.messages))
    if channel:
        query = query.filter(Conversation.channel == channel)
    if status:
        query = query.filter(Conversation.status == status)
    if visitor_id:
        query = query.filter(Conversation.session_key == visitor_id)
    if user_id:
        try:
            user_uuid = uuid.UUID(user_id)
            query = query.filter(Conversation.lead_id == user_uuid)
        except ValueError:
            pass
            
    if search:
        # Search by session_key or joined lead's fields
        from app.models import Lead
        query = query.outerjoin(Lead, Conversation.lead_id == Lead.id)
        search_filter = (
            (Conversation.session_key.ilike(f"%{search}%")) |
            (Lead.name.ilike(f"%{search}%")) |
            (Lead.email.ilike(f"%{search}%")) |
            (Lead.phone.ilike(f"%{search}%"))
        )
        try:
            conv_search_uuid = uuid.UUID(search)
            search_filter = search_filter | (Conversation.id == conv_search_uuid)
        except ValueError:
            pass
            
        query = query.filter(search_filter)

    total = query.count()
    conversations = query.order_by(Conversation.updated_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    items = []
    for c in conversations:
        # Get message count and last message efficiently since we eagerly loaded messages
        msgs = sorted(c.messages, key=lambda m: m.created_at)
        last_msg = msgs[-1] if msgs else None
        
        items.append(
            AdminConversationDetail(
                id=c.id,
                visitor_id=c.session_key,
                user_id=c.lead.id if c.lead else None,
                user_name=c.lead.name if c.lead else None,
                email=c.lead.email if c.lead else None,
                phone=c.lead.phone if c.lead else None,
                channel=c.channel.value if hasattr(c.channel, 'value') else c.channel,
                message_count=len(msgs),
                last_message=last_msg.content if last_msg else None,
                last_message_at=last_msg.created_at if last_msg else c.last_message_at,
                created_at=c.created_at
            ).model_dump()
        )
    
    data = {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": (total + limit - 1) // limit
    }
    return StandardResponse(success=True, data=data, meta=meta)

@router.get("/{conversation_id}", response_model=StandardResponse)
def get_conversation(conversation_id: str, request: Request, db: Session = Depends(get_db)):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    meta = StandardMeta(request_id=req_id)
    
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except:
        conv_uuid = None
        
    convo = db.query(Conversation).options(selectinload(Conversation.lead), selectinload(Conversation.messages)).filter(
        (Conversation.id == conv_uuid) | (Conversation.session_key == conversation_id)
    ).first()
    
    if not convo:
        return StandardResponse(
            success=False,
            error=StandardError(code="CONVERSATION_NOT_FOUND", message="Conversation not found."),
            meta=meta
        )
        
    msgs = sorted(convo.messages, key=lambda m: m.created_at)
    last_msg = msgs[-1] if msgs else None

    # Construct the response matching the requested schema
    response_data = ConversationWithMessagesDetail(
        id=convo.id,
        visitor_id=convo.session_key,
        user_id=convo.lead.id if convo.lead else None,
        user_name=convo.lead.name if convo.lead else None,
        email=convo.lead.email if convo.lead else None,
        phone=convo.lead.phone if convo.lead else None,
        channel=convo.channel.value if hasattr(convo.channel, 'value') else convo.channel,
        message_count=len(msgs),
        last_message=last_msg.content if last_msg else None,
        last_message_at=last_msg.created_at if last_msg else convo.last_message_at,
        created_at=convo.created_at,
        messages=msgs
    )
        
    data = response_data.model_dump()
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

@router.delete("/{conversation_id}", response_model=StandardResponse)
def delete_conversation(conversation_id: str, request: Request, db: Session = Depends(get_db)):
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
        
    try:
        # Delete all messages first
        db.query(Message).filter(Message.conversation_id == convo.id).delete(synchronize_session=False)
        # Delete the conversation
        db.delete(convo)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error during deletion")
        
    return StandardResponse(
        success=True, 
        data={"success": True, "message": "Conversation deleted successfully", "conversation_id": str(convo.id)}, 
        meta=meta
    )
