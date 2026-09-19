from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

import os

from app.database import get_db
from app.models import Lead
from app.schemas import LeadOut, LeadDetailOut

router = APIRouter(prefix="/api/leads", tags=["leads"])


def require_admin(x_api_key: str = Header(...)):
    admin_key = os.getenv("ADMIN_API_KEY", "change_me")
    if x_api_key != admin_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")


@router.get("", response_model=list[LeadOut], dependencies=[Depends(require_admin)])
def list_leads(db: Session = Depends(get_db)):
    """All leads captured from both the website, most recent first."""
    return db.query(Lead).order_by(Lead.created_at.desc()).all()


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
