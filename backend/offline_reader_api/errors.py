"""The error envelope: every non-2xx /api response is ``{"error": {"code", "message"}}``.

``ApiError`` is the app's own exception (machine-readable ``code`` + human
``message``); handlers below also translate framework exceptions (validation,
bare HTTPException, crashes) into the same envelope so clients parse one shape.
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Fallback codes for bare HTTPExceptions raised without an ApiError.
_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    500: "internal_error",
}


class ApiError(Exception):
    """An expected API failure with a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Build the canonical error envelope."""
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def _summarize_validation(exc: RequestValidationError) -> str:
    """Field-name + message only — never Pydantic's ``input`` (CWE-209).

    ``exc.errors()`` embeds the offending ``input``; we surface just the field
    location and the human message so a bad body never echoes user data back.
    """
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        msg = str(err.get("msg", "invalid"))
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "validation error"


def install_error_handlers(app: FastAPI) -> None:
    """Route every error through the envelope."""

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "error")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(422, "validation_error", _summarize_validation(exc))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled error", extra={"path": request.url.path, "method": request.method}
        )
        return error_response(500, "internal_error", "internal server error")
