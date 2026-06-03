
from app.core.config import settings, OPENROUTER_API_KEY
from pydantic import BaseModel, Field
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
    preset_id: Optional[str] = None
    messages: List[ChatMessage] = Field(min_length=1)
    model: str = "auto"
    stream: bool = True
    provider: Provider= Provider.auto
    private: bool= False



def get_local_client():
    return AsyncOpenAI(
        base_url=f"{settings.LM_URL}/v1",
        api_key = "LM-STUDIO"
        )

def get_openrouter_client():
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY
    )

async def get_provider(request: ChatRequest):
    last_message = request.messages[-1].content.lower()
    code = ["script", "code", "function", "debug", "bug", "python", "c++", "java", "javascript", "typescript"]
    image= ["draw","image", "picture", "screenshot", "imagine"]

    # user has model choice; fall back to the provider default if unset
    local_model = request.model if request.model != 'auto' else (settings.LM_CHAT_MODEL or settings.LM_DEFAULT_MODEL)
    or_model    = request.model if request.model != 'auto' else settings.OPENROUTER_DEFAULT_MODEL

    match request:
        case ChatRequest(private=True):
            return get_local_client(), local_model                # privacy 
        case ChatRequest(provider=Provider.local):                
            return get_local_client(), local_model                # explicitly use local   
        case ChatRequest(provider=Provider.openrouter):
            return get_openrouter_client(), or_model              # explicitly use openrouter
        case _ if any(k in last_message for k in code):
            return get_openrouter_client(), or_model              # for coding tasks we use openrouter model
        case _ if len(request.messages) > 80:
            return get_openrouter_client(), or_model              # for long tasks, use openrouter model
        case _:
            return get_local_client(), local_model       