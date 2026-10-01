from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import REQUEST_ID_HEADER

logger = structlog.get_logger("app.errors")


class AppError(Exception):
    """Base class for errors that map to a standard error response."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found."


class PermissionDeniedError(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"
    message = "You are not allowed to perform this action."


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "The request conflicts with the current state."


class ValidationAppError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "The request is invalid."


class LimitExceededError(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Limit exceeded. Try again later."


class ExternalServiceError(AppError):
    status_code = 502
    code = "EXTERNAL_SERVICE_ERROR"
    message = "An external service failed."


_HTTP_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_FILE_TYPE",
    429: "RATE_LIMITED",
}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
        headers=headers,
    )


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
    return error_response(request, exc.status_code, code, message)


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    fields = [
        {
            "loc": [str(part) for part in error.get("loc", ())],
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
    return error_response(
        request, 422, "VALIDATION_ERROR", "The request is invalid.", {"fields": fields}
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path)
    return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
