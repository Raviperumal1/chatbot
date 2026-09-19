import enum
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum, JSON, Uuid
from sqlalchemy.orm import relationship

IST = timezone(timedelta(hours=5, minutes=30))

from app.database import Base


class Channel(str, enum.Enum):
    website = "website"
    whatsapp = "whatsapp"


class SenderRole(str, enum.Enum):
    user = "user"
    bot = "bot"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    source = Column(Enum(Channel), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST))

    conversations = relationship("Conversation", back_populates="lead")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(Uuid(as_uuid=True), ForeignKey("leads.id"), nullable=True)
    channel = Column(Enum(Channel), nullable=False)
    session_key = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="active")
    language = Column(String(10), nullable=False, default="en")
    external_user_id = Column(String(255), nullable=True, index=True)
    metadata_ = Column("metadata", JSON, nullable=True)

    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST))
    last_message_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST))
    ended_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), onupdate=lambda: datetime.now(IST))

    lead = relationship("Lead", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_uuid = Column(Uuid(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    conversation_id = Column(Uuid(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    role = Column(Enum(SenderRole), nullable=False)
    channel = Column(Enum(Channel), nullable=False, default=Channel.website)
    external_message_id = Column(String(255), nullable=True, index=True, unique=True)
    content = Column(Text, nullable=False)
    message_type = Column(String(50), nullable=False, default="text")
    message_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST))

    conversation = relationship("Conversation", back_populates="messages")
