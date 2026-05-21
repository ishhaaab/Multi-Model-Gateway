from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.core.config import settings
from app.models.conversations import Conversation
from app.models.messages import Message
from app.services.router import get_provider, ChatRequest
from app.core.security import get_current_user


router = APIRouter()

async def stream_tokens(request: ChatRequest, user_id: str, db: AsyncSession ) :
    
    if request.conversation_id is None:
        title = " ".join(request.messages[-1].content.split()[:6])
        new_convo = Conversation(title=title, user_id=user_id)
        db.add(new_convo)
        await db.commit()
        conversation_id = str(new_convo.id)
    else:
        conversation_id= request.conversation_id
    
    
    query= await db.execute(select(Conversation).where(conversation_id== Conversation.id))
    conversation= query.scalar_one_or_none()

    if conversation is  None:
        raise HTTPException(status_code=404, detail="conversation not found")

    if str(conversation.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="unauthorised user")
    
    messages_result= await db.execute(select(Message).where(Message.conversation_id == conversation_id))
    all_messages = messages_result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in all_messages]
    current = {"role": "user", "content": request.messages[-1].content}
    messages = history + [current]


    client, model = await get_provider(request)
    response = await client.chat.completions.create(
        model= model,
        messages= messages,
        stream = True,
    )

    full_response= ""
    async for chunk in response:
        content= chunk.choices[0].delta.content
    
        if content:
            full_response += content
            yield f"data: {content}\n\n"

    user_msg = Message(conversation_id=str(conversation_id), role="user", content=request.messages[-1].content)
    assistant_msg = Message(conversation_id=str(conversation_id), role="assistant", content=full_response, model_used=model)
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()

    yield "data: [Done]\n\n" 


@router.post("/chat/completions")
async def chat_completions(request: ChatRequest, db: AsyncSession = Depends(get_db), user_id= Depends(get_current_user)):
    return StreamingResponse(
        stream_tokens(request, user_id, db),
        media_type="text/event-stream"
    )