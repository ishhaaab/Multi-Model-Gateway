"""Domain-level errors for the service layer.

Services raise these instead of `fastapi.HTTPException` so they stay
framework-agnostic (callable from a worker, CLI, or test, not just an HTTP
request). A single handler in `app.main` translates them to HTTP responses at
the API boundary. The response shape matches FastAPI's default ({"detail": ...})
so existing clients are unaffected.
"""


class AppError(Exception):
    """Base for errors that map to an HTTP response at the API boundary."""

    status_code: int = 500
    detail: str = "internal server error"

    def __init__(self, detail: str | None = None):
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    detail = "not found"


class ForbiddenError(AppError):
    status_code = 403
    detail = "forbidden"
