from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import chat, models, auth, convo
from app.middleware.ratelimit import RateLimitMiddleware
from app.core.redis import get_redis, close_redis
from prometheus_fastapi_instrumentator import Instrumentator

app= FastAPI()

Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # to accept requests from any origin
    allow_credentials=True,
    allow_methods=["*"],  #to accept any HTTP method (GET, POST, etc.)
    allow_headers=["*"], # to accept any headers
                   )

app.add_middleware(RateLimitMiddleware)

@app.on_event("startup")
async def startup():
    await get_redis()  # warm the connection pool

@app.on_event("shutdown")
async def shutdown():
    await close_redis()



@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(chat.router, prefix = "/v1")
app.include_router(models.router, prefix = "/v1")
app.include_router(auth.router, prefix="/auth")
app.include_router(convo.router, prefix="/v1")
