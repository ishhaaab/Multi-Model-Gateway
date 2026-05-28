
from app.core.config import settings
from pydantic import BaseModel
from typing  import List, Optional
from openai import AsyncOpenAI

from enum import Enum

class Provider(str, Enum):
    auto= "auto"
    local= "local"
    openrouter= "openrouter"

class ChatMessage(BaseModel):
    role: str
    content: str



class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    messages: List[ChatMessage]
    model: str = settings.LOCAL_DEFAULT_MODEL
    stream: bool = True
    provider: Provider= Provider.auto
    private: bool= False



def get_local_client():
    return AsyncOpenAI(
        base_url=settings.LOCAL_URL,
        api_key = "ollama"
        )

def get_openrouter_client():
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY
    )

async def get_provider(request: ChatRequest):
    last_message = request.messages[-1].content.lower()
    code = ["script", "code", "function", "debug", "bug", "python", "c++", "java", "javascript", "typescript"]
    image= ["draw","image", "picture", "screenshot", "imagine"]

    # user has model choice; fall back to the provider default if unset
    local_model = request.model if request.model != 'auto' else settings.LOCAL_DEFAULT_MODEL
    or_model    = request.model if request.model != 'auto' else settings.OPENROUTER_DEFAULT_MODEL

    match request:
        case ChatRequest(private=True):
            return get_local_client(), local_model                # privacy 
        case ChatRequest(provider=Provider.local):                
            return get_local_client(), local_model                # explicitly use local   
        case ChatRequest(model=m) if "/" in m:
            return get_openrouter_client(), request.model         # explicitly use openrouter 
        case ChatRequest(provider=Provider.openrouter):
            return get_openrouter_client(), or_model              # openrouter model
        case _ if any(k in last_message for k in code):
            return get_openrouter_client(), or_model              # for coding tasks we use openrouter model
        case _ if len(request.messages) > 80:
            return get_openrouter_client(), or_model              # for long tasks, use openrouter model
        case _:
            return get_local_client(), local_model       