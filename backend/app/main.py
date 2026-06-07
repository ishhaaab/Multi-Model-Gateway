from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import chat, models, auth, convo, presets, templates, images, workflows
from app.middleware.ratelimit import RateLimitMiddleware
from app.core.redis import get_redis, close_redis
from app.core.config import settings
from app.core.exceptions import AppError
from prometheus_fastapi_instrumentator import Instrumentator


_docs_enabled = settings.ENV != "production"
app = FastAPI(
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,  # restrict to configured frontends
    allow_credentials=False,                      # bearer tokens go in the Authorization header; no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    # Translate service-layer domain errors into HTTP at the API boundary.
    # Matches FastAPI's default error shape ({"detail": ...}); one handler
    # covers every AppError subclass (Starlette walks the exception's MRO).
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


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
app.include_router(presets.router, prefix="/v1")
app.include_router(templates.router, prefix="/v1")
app.include_router(images.router, prefix="/v1")
app.include_router(workflows.router, prefix="/v1")
 