from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func

import os

from app.database import get_db
from app.models import Lead, Conversation, Message
from app.schemas import LeadOut, LeadDetailOut, PaginatedLeadOut, LeadListOut

router = APIRouter(prefix="/api/leads", tags=["leads"])


def require_admin(x_api_key: str = Header(...)):
    admin_key = os.getenv("ADMIN_API_KEY", "change_me")
    if x_api_key != admin_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")


@router.get("", response_model=PaginatedLeadOut, dependencies=[Depends(require_admin)])
def list_leads(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    channel: str = Query(None)
):
    """Paginated list of all leads captured, most recent first."""
    query = db.query(Lead).options(selectinload(Lead.conversations))
    
    if channel:
        query = query.filter(Lead.source == channel)
        
    if search:
        search_filter = (
            (Lead.name.ilike(f"%{search}%")) |
            (Lead.email.ilike(f"%{search}%")) |
            (Lead.phone.ilike(f"%{search}%"))
        )
        query = query.filter(search_filter)
        
    total = query.count()
    leads = query.order_by(Lead.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
    
    items = []
    for lead in leads:
        # Aggregation for counts and channels. Could be optimized, but using relationships for simplicity if list size is small.
        convs = lead.conversations
        items.append(
            LeadListOut(
                id=lead.id,
                name=lead.name,
                email=lead.email,
                phone=lead.phone,
                visitor_ids=list(set(c.session_key for c in convs)),
                channels=list(set(c.channel.value for c in convs)),
                conversation_count=len(convs),
                last_conversation_at=max([c.last_message_at for c in convs]) if convs else None,
                created_at=lead.created_at
            )
        )
        
    return PaginatedLeadOut(
        items=items,
        page=page,
        limit=limit,
        total=total,
        total_pages=(total + limit - 1) // limit
    )


@router.get("/{lead_id}", response_model=LeadDetailOut, dependencies=[Depends(require_admin)])
def get_lead(lead_id: str, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    messages = []
    for convo in lead.conversations:
        messages.extend(convo.messages)
    lead_out = LeadDetailOut.model_validate(lead)
    lead_out.messages = messages
    return lead_out

@router.delete("/{lead_id}", dependencies=[Depends(require_admin)])
def delete_lead(lead_id: str, db: Session = Depends(get_db)):
    import uuid
    try:
        lead_uuid = uuid.UUID(lead_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
        
    lead = db.query(Lead).filter(Lead.id == lead_uuid).first()
    if not lead:
        raise HTTPException(status_code=404, detail="User not found")
        
    try:
        # Find all conversations for this lead
        convos = db.query(Conversation).filter(Conversation.lead_id == lead.id).all()
        convo_ids = [c.id for c in convos]
        
        if convo_ids:
            # Delete all related messages
            db.query(Message).filter(Message.conversation_id.in_(convo_ids)).delete(synchronize_session=False)
            # Delete all related conversations
            db.query(Conversation).filter(Conversation.id.in_(convo_ids)).delete(synchronize_session=False)
            
        # Delete the lead
        db.delete(lead)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error during deletion")
        
    return {
        "success": True,
        "message": "User and associated conversations/messages deleted successfully",
        "lead_id": str(lead.id)
    }
