"""
Hard request-size cap for upload endpoints, enforced before the multipart body is buffered.

Starlette spools a multipart body before route code runs, so the per-file check in the route only
limits what is stored. This ASGI middleware limits what is *received*: it rejects on Content-Length
and also counts bytes for chunked bodies that declare no length.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# multipart framing + one file part; the route enforces the exact per-file limit.
OVERHEAD_BYTES = 64 * 1024


class RequestTooLarge(Exception):
    pass


class UploadSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, path: str, max_body_bytes: int) -> None:
        self.app = app
        self.path = path
        self.max_body_bytes = max_body_bytes

    async def _reject(self, send: Send) -> None:
        body = json.dumps({"detail": "Request body too large"}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_body_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                pass

        received = 0
        exceeded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    exceeded = True
                    raise RequestTooLarge()
            return message

        replaced = False

        async def tracking_send(message: Message) -> None:
            # FastAPI converts an exception raised while reading the body into a 400; when the cap
            # was what stopped the read, answer 413 instead.
            nonlocal replaced
            if exceeded:
                if not replaced:
                    replaced = True
                    await self._reject(send)
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except RequestTooLarge:
            if not replaced:
                await self._reject(send)
