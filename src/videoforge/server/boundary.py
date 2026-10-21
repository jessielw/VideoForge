"""Host and browser-origin checks for the single-user server (not authentication)."""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def origin(value: str) -> tuple[str, str, int] | None:
    try:
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            return None
        if url.path or url.query or url.fragment:
            return None
        return url.scheme, url.hostname.lower(), url.port or (443 if url.scheme == "https" else 80)
    except ValueError:
        return None


class BrowserBoundary:
    def __init__(self, app: ASGIApp, *, hosts: list[str], origins: list[str]) -> None:
        self.app = app
        self.hosts = {host.lower() for host in hosts}
        parsed = [origin(value) for value in origins]
        if any(value is None for value in parsed):
            raise ValueError("Allowed origins must be complete http(s) origins without paths")
        self.origins = set(parsed)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        scheme = "https" if scope.get("scheme") in {"https", "wss"} else "http"
        target = origin(f"{scheme}://{headers.get('host', '')}")
        status, reason = 0, ""
        if len(headers.getlist("host")) != 1 or target is None or target[1] not in self.hosts:
            status, reason = 400, "Host is not allowed; configure --allow-host for this address"
        elif scope["type"] == "websocket" or scope.get("method") not in {"GET", "HEAD", "OPTIONS"}:
            sent_origin = headers.get("origin")
            parsed = origin(sent_origin) if sent_origin is not None else None
            if len(headers.getlist("origin")) > 1 or (
                sent_origin is not None and (parsed is None or (parsed != target and parsed not in self.origins))
            ):
                status, reason = 403, "Browser origin is not allowed"
            elif sent_origin is None and headers.get("sec-fetch-site") == "cross-site":
                status, reason = 403, "Cross-site controls are not allowed"
        if status:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008, "reason": reason})
            else:
                await JSONResponse({"detail": reason}, status_code=status)(scope, receive, send)
            return
        await self.app(scope, receive, send)
