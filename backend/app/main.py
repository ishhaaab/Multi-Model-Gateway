from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import chat, models, auth

from app.db import engine, Base
from app.models import users, conversations, messages
from app.routers import convo

app= FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # to accept requests from any origin
    allow_credentials=True,
    allow_methods=["*"],  #to accept any HTTP method (GET, POST, etc.)
    allow_headers=["*"], # to accept any headers
                   )


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(chat.router, prefix = "/v1")
app.include_router(models.router, prefix = "/v1")
app.include_router(auth.router, prefix="/auth")
app.include_router(convo.router, prefix="/v1")

@app.on_event("startup")
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)