from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.db import Base
import uuid, datetime

class Preset(Base): 
    __tablename__= "presets"
    id= Column(UUID, primary_key= True, nullable=False, default= uuid.uuid4)
    user_id= Column(UUID, ForeignKey("users.id", ondelete= "CASCADE"))
    name= Column(String, nullable= False)
    system_prompt= Column(Text, nullable= True)
    temperature= Column(Float, default= 0.8)
    token_limit= Column(Integer, nullable= True)
    context_overflow=  Column(String, nullable=True, default="truncate_middle")
    stop_strings = Column(ARRAY(String), nullable=True)
    top_k= Column(Integer, nullable= True, default= 40)
    top_p= Column(Float, nullable= True, default= 0.95)
    min_p= Column(Float, nullable= True, default= 0.05)
    repeat_penalty= Column(Float, nullable= True, default= 1.10)
    created_at= Column(DateTime, default= datetime.datetime.utcnow)


    