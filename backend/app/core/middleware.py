"""Bounded request controls for public API deployments."""

import time
from collections import OrderedDict, deque
from math import ceil
from threading import Lock
from typing import Any

from starlette.responses import JSONResponse


class RequestSizeLimitMiddleware:
    """Buffer small API requests and reject oversized bodies before dispatch."""

    def __init__(self, app: Any, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await JSONResponse(
                    status_code=400,
                    content={
                        "detail": {
                            "code": "invalid_content_length",
                            "message": "Request content length is invalid.",
                        }
                    },
                )(scope, receive, send)
                return

        messages: list[dict[str, Any]] = []
        total_bytes = 0
        message_count = 0
        while True:
            message = await receive()
            messages.append(message)
            message_count += 1
            if message["type"] == "http.disconnect":
                return
            total_bytes += len(message.get("body", b""))
            if total_bytes > self.max_bytes or message_count > 1024:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_receive() -> dict[str, Any]:
            nonlocal message_index
            if message_index < len(messages):
                message = messages[message_index]
                message_index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "detail": {
                    "code": "request_too_large",
                    "message": "Request body exceeds the configured size limit.",
                }
            },
        )
        await response(scope, receive, send)


class AgentRateLimitMiddleware:
    """Apply a bounded per-process sliding-window limit to agent runs."""

    def __init__(
        self,
        app: Any,
        max_requests: int,
        window_seconds: int = 60,
        max_clients: int = 5000,
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/api/agent/run"
        ):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_key = str(client[0]) if client else "unknown"
        now = time.monotonic()
        with self._lock:
            timestamps = self._requests.setdefault(client_key, deque())
            cutoff = now - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.max_requests:
                retry_after = max(
                    1, ceil(self.window_seconds - (now - timestamps[0]))
                )
                limited = True
            else:
                timestamps.append(now)
                self._requests.move_to_end(client_key)
                while len(self._requests) > self.max_clients:
                    self._requests.popitem(last=False)
                retry_after = 0
                limited = False

        if limited:
            response = JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "detail": {
                        "code": "rate_limited",
                        "message": "Agent request limit reached. Try again shortly.",
                    }
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
