"""Error domain (`AppError`) + exception handler terpusat.

Service melempar `AppError` (atau turunannya); handler di sini mengubahnya menjadi
respons JSON ber-amplop seragam. Setiap respons error membawa `X-Request-ID`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .context import get_request_id
from .i18n import get_locale, translate
from .schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger("anjab_abk_backend.error")

_HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    408: "request_timeout",
    409: "conflict",
    412: "precondition_failed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    428: "precondition_required",
    429: "rate_limited",
    503: "service_unavailable",
    504: "gateway_timeout",
}


class AppError(Exception):
    """Error domain dengan status HTTP & kode error stabil."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        details: list[ErrorDetail] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


class ValidationAppError(AppError):
    status_code = 422
    error_code = "validation_error"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthorized"


class PreconditionRequiredError(AppError):
    status_code = status.HTTP_428_PRECONDITION_REQUIRED
    error_code = "precondition_required"


class PreconditionFailedError(AppError):
    status_code = status.HTTP_412_PRECONDITION_FAILED
    error_code = "precondition_failed"


class PayloadTooLargeError(AppError):
    status_code = 413
    error_code = "payload_too_large"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limited"


class GatewayTimeoutError(AppError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    error_code = "gateway_timeout"


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "service_unavailable"


def error_envelope(
    error: str,
    message: str,
    request_id: str | None = None,
    details: list[ErrorDetail] | None = None,
) -> dict:
    return ErrorResponse(
        error=error,
        message=message,
        request_id=request_id,
        details=details,
    ).model_dump(exclude_none=True)


def _resolve_request_id(request: Request | None) -> str | None:
    rid = get_request_id()
    if rid:
        return rid
    if request is not None:
        return getattr(request.state, "request_id", None)
    return None


def _json_error(
    request: Request | None,
    status_code: int,
    error: str,
    message: str,
    *,
    details: list[ErrorDetail] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    rid = _resolve_request_id(request)
    message = translate(message, get_locale(request))
    headers: dict[str, str] = {}
    if extra_headers:
        headers.update(extra_headers)
    if rid:
        headers["X-Request-ID"] = rid
    return JSONResponse(
        status_code=status_code,
        content=error_envelope(error, message, rid, details),
        headers=headers or None,
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError):
        if exc.status_code >= 500:
            logger.error("app_error", extra={"error_code": exc.error_code}, exc_info=exc)
        else:
            logger.warning("app_error", extra={"error_code": exc.error_code})
        return _json_error(
            request,
            exc.status_code,
            exc.error_code,
            exc.message,
            details=exc.details,
            extra_headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError):
        details = [
            ErrorDetail(
                loc=[str(p) for p in e["loc"]],
                msg=e["msg"],
                type=e["type"],
                code=e["type"],
            )
            for e in exc.errors()
        ]
        return _json_error(
            request, 422, "validation_error", "Payload tidak valid.", details=details
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException):
        code = _HTTP_ERROR_CODES.get(exc.status_code, "http_error")
        message = "Terjadi kesalahan internal." if exc.status_code >= 500 else str(exc.detail)
        if exc.status_code >= 500:
            logger.error("http_error", extra={"status_code": exc.status_code}, exc_info=exc)
        return _json_error(
            request,
            exc.status_code,
            code,
            message,
            extra_headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        logger.exception("unhandled_exception")
        return _json_error(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Terjadi kesalahan internal.",
        )
