from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
from app.core.config import settings
from app.core.redis import get_redis
import time

EXCLUDED_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/auth/register", "/auth/login", "/auth/refresh"}

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)

        # Extract user_id from JWT— don't re-raise auth errors here,
        # actual route handler will deal with bad tokens
        user_id = self._extract_user_id(request)
        if user_id is None:
            return await call_next(request)

        redis = await get_redis()
        key = f"rate:{user_id}"
        window = settings.RATE_LIMIT_WINDOW_SECONDS
        limit = settings.RATE_LIMIT_PER_MINUTE

        now = int(time.time())
        window_start = now - window

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)   # drop requests outside window
        pipe.zadd(key, {str(now): now})                # add this request
        pipe.zcard(key)                                # count requests in window
        pipe.expire(key, window)                       # auto-expire the key
        results = await pipe.execute()

        count = results[2]

        if count > limit:
            retry_after = window - (now - window_start)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(retry_after)}
            )

        return await call_next(request)

    def _extract_user_id(self, request: Request) -> str | None:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1]
        try:
            decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            if decoded.get("type") != "access":
                return None
            return decoded.get("sub")
        except JWTError:
            return None