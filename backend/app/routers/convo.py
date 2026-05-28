from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, status, Depends

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.core import security

from app.models.conversations import Conversation
from app.models.messages import Message

router= APIRouter()

class ConvoCreate(BaseModel):
    title: str

class ConvoRename(BaseModel):
    title: str


# create a new conversation & get it
@router.post("/convo")
async def convo_create(convo_data: ConvoCreate, db: AsyncSession = Depends(get_db), user_id = Depends(security.get_current_user)):
    new_convo= Conversation(title= convo_data.title, user_id= user_id)
    db.add(new_convo)
    await db.commit()
    return {"message": "conversation created", "id": str(new_convo.id)}

@router.get("/convo")
async def convo_get(db: AsyncSession = Depends(get_db), user_id= Depends(security.get_current_user)):
    query= await db.execute(select(Conversation).where(Conversation.user_id== user_id))
    conversations = query.scalars().all()
    return conversations

# get the messages from a specific conversation
@router.get("/convo/{convo_id}")
async def messages_get(convo_id: str, db: AsyncSession = Depends(get_db), user_id= Depends(security.get_current_user) ):
    convo_result = await db.execute(select(Conversation).where(Conversation.id == convo_id))
    conversation = convo_result.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    if str(conversation.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="unauthorised user")
    
    messages_result = await db.execute(select(Message).where(Message.conversation_id == convo_id))
    messages = messages_result.scalars().all()
    return messages

# rename the conversation title

@router.patch("/convo/{convo_id}")
async def convo_rename(convo_id: str, convo_data: ConvoRename, db: AsyncSession= Depends(get_db), user_id= Depends(security.get_current_user)):
    query= await db.execute(select(Conversation).where(Conversation.id== convo_id))
    conversation= query.scalar_one_or_none()
    
    if conversation is None:
        raise HTTPException(status_code=404, detail= "convo not found")
    
    if str(conversation.user_id) != str(user_id):
        raise HTTPException(status_code= 403, detail= "unauthorised user")
    
    conversation.title= convo_data.title
    await db.commit()
    return {"message": "conversation renamed"}


# remove the conversation from the database

@router.delete("/convo/{convo_id}")
async def convo_delete(convo_id: str, db: AsyncSession= Depends(get_db), user_id= Depends(security.get_current_user)):
    query= await db.execute(select(Conversation).where(Conversation.id== convo_id))
    conversation= query.scalar_one_or_none()

    if conversation is None:
        raise HTTPException(status_code=404, detail= "convo not found")
    
    if str(conversation.user_id) != str(user_id):
        raise HTTPException(status_code= 403, detail= "unauthorised user")
    
    await db.delete(conversation)
    await db.commit()
    return {"message": "conversation deleted"}
