from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.conversations import Conversation
from app.models.messages import Message

from app.services.memory import store_memory, retrieve_memories


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



# message retrieval 
    # by index:
async def get_message_by_index(conversation_id: str, index: int, db: AsyncSession):
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .where(Message.index == index)
        .where(Message.role == "user")
    )
    return result.scalar_one_or_none()

    # by embedding:
async def get_memory_context(conversation_id: str, query: str, db: AsyncSession) -> dict | None:
    memories = await retrieve_memories(conversation_id=conversation_id, query=query, db=db)

    if not memories:
        return None

    memory_text = "\n".join([f"[{m['role']} at {m['created_at']}]: {m['content']}" for m in memories])
    
    return {
        "role": "system",
        "content": f"Relevant context from earlier in this conversation:\n{memory_text}"
    }



async def load_history(conversation_id: str, query: str, db: AsyncSession) -> list:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
    recent = [{"role": m.role, "content": m.content} for m in messages]

    context = await get_memory_context(conversation_id, query, db)
    if context:
        return [context] + recent
    return recent


async def save_messages(conversation_id: str, user_content: str, assistant_content: str, model: str, token_count, db: AsyncSession):
    
    result = await db.execute(
    select(func.max(Message.index)).where(Message.conversation_id == conversation_id)
)
    max_index = result.scalar() or 0
    next_index  = int(max_index + 1)
    
    
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=user_content,
        index= next_index
    )
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        model_used=model,
        tokens_used= token_count,
        index= next_index
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()

    convo_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    convo = convo_result.scalar_one_or_none()
    if convo:
        convo.token_count = (convo.token_count or 0) + token_count
        await db.commit()

    await store_memory(conversation_id, role="user", content=user_content, db= db)
    await store_memory(conversation_id, role="assistant", content=assistant_content, db= db)

