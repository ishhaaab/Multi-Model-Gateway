from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.conversations import Conversation
from app.models.messages import Message


async def conversation(request, user_id: str, db: AsyncSession) -> str:
    if request.conversation_id is None:
        title = " ".join(request.messages[-1].content.split()[:6])
        new_convo = Conversation(title=title, user_id=user_id)
        db.add(new_convo)
        await db.commit()
        return str(new_convo.id)
    else:
        query = await db.execute(
            select(Conversation).where(Conversation.id == request.conversation_id)
        )
        conversation = query.scalar_one_or_none()

        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")

        if str(conversation.user_id) != str(user_id):
            raise HTTPException(status_code=403, detail="unauthorised user")

        return str(conversation.id)


async def load_history(conversation_id: str, db: AsyncSession) -> list:
    query = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    messages = query.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]


async def save_messages(conversation_id: str, user_content: str, assistant_content: str, model: str, db: AsyncSession):
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=user_content
    )
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        model_used=model
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()