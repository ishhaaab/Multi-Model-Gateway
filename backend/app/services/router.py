
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
    model: str = settings.LM_DEFAULT_MODEL
    stream: bool = True
    provider: Provider= Provider.auto
    private: bool= False



def get_lm_client():
    return AsyncOpenAI(
        base_url=settings.LM_URL,
        api_key = "lm-studio"
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


    # privacy 
    if request.private:
        return get_lm_client(), settings.LM_DEFAULT_MODEL


    # explicit provider:

    if request.provider == Provider.local:
        return get_lm_client(), settings.LM_DEFAULT_MODEL

    if request.provider == Provider.openrouter:
        return get_openrouter_client()

    # explicit openroutuer model: 
    
    if "/" in request.model :
        return get_openrouter_client()


    # coding tasks are handled by openrouter models
    if any(keyword in last_message for keyword in code):
        return get_openrouter_client()

    # vision tasks are handled by ???
    
    # long tasks are handled by openrouter models
    if len(request.messages) > 80:
        return get_openrouter_client()

    return get_lm_client(), settings.LM_DEFAULT_MODEL