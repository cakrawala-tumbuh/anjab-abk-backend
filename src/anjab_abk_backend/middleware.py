"""Middleware HTTP (pure ASGI) + CORS + TrustedHost."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .context import request_id_ctx, trace_id_ctx
from .errors import error_envelope

logger = logging.getLogger("anjab_abk_backend.access")


def _parse_traceparent(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.split("-")
    if len(parts) >= 2 and len(parts[1]) == 32 and all(c in "0123456789abcdef" for c in parts[1]):
        return parts[1]
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, exclude_paths: set[str] | None = None) -> None:
        self.app = app
        self.exclude_paths = exclude_paths or set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        rid = headers.get("x-request-id") or uuid.uuid4().hex
        trace_id = _parse_traceparent(headers.get("traceparent"))
        rid_token = request_id_ctx.set(rid)
        trace_token = trace_id_ctx.set(trace_id)
        scope.setdefault("state", {})["request_id"] = rid
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).setdefault("X-Request-ID", rid)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if path not in self.exclude_paths:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                extra = {
                    "request_id": rid,
                    "method": scope.get("method"),
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                }
                if trace_id:
                    extra["trace_id"] = trace_id
                logger.info("access", extra=extra)
            request_id_ctx.reset(rid_token)
            trace_id_ctx.reset(trace_token)


class SecurityHeadersMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        hsts: bool = False,
        coop: bool = True,
        popup_paths: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.hsts = hsts
        self.coop = coop
        self.popup_paths = popup_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        allow_popups = any(path.startswith(prefix) for prefix in self.popup_paths)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                if self.coop and not allow_popups:
                    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
                if self.hsts:
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=63072000; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)


class TimeoutMiddleware:
    def __init__(self, app: ASGIApp, timeout_seconds: float) -> None:
        self.app = app
        self.timeout = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await asyncio.wait_for(self.app(scope, receive, send_wrapper), timeout=self.timeout)
        except TimeoutError:
            logger.warning("request_timeout", extra={"path": scope.get("path", "")})
            if not started:
                response = JSONResponse(
                    status_code=504,
                    content=error_envelope(
                        "gateway_timeout",
                        "Permintaan melebihi batas waktu pemrosesan.",
                        request_id_ctx.get(),
                    ),
                )
                await response(scope, receive, send)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        total = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal total, too_large
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    too_large = True
            return message

        started = False

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)
        if too_large and not started:  # pragma: no cover
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content=error_envelope(
                "payload_too_large",
                f"Body melebihi batas {self.max_bytes} byte.",
                request_id_ctx.get(),
            ),
        )
        await response(scope, receive, send)


def install_middleware(app: FastAPI, settings: Settings) -> None:
    if settings.max_request_body_bytes:
        app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    if settings.gzip_min_size:
        app.add_middleware(GZipMiddleware, minimum_size=settings.gzip_min_size)
    if settings.enable_security_headers:
        popup_paths = ("/docs",) if settings.docs_enabled else ()
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts=settings.enable_hsts,
            coop=settings.enable_coop,
            popup_paths=popup_paths,
        )
    if settings.request_timeout_seconds:
        app.add_middleware(TimeoutMiddleware, timeout_seconds=settings.request_timeout_seconds)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "ETag", "Link"],
        )
    if settings.allowed_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        RequestContextMiddleware,
        exclude_paths=set(settings.access_log_excludes),
    )
