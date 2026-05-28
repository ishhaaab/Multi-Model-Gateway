from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey 
from sqlalchemy.dialects.postgresql import UUID
from app.db import Base
import uuid, datetime

class Message(Base):
    __tablename__="messages"
    id= Column(UUID, primary_key=True, default=uuid.uuid4)
    conversation_id= Column(UUID, ForeignKey("conversations.id", ondelete="CASCADE"))
    role= Column(String, nullable=False)
    content= Column(Text)
    created_at= Column(DateTime, default=datetime.datetime.utcnow)
    model_used= Column(String, nullable=True)
    tokens_used= Column(Integer, default=0)
    index = Column(Integer, nullable=True)