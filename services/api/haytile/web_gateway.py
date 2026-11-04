"""Same-origin HTTP forwarding; the existing API process terminates live sockets."""

import os
from urllib.parse import urlsplit

import httpx
from fastapi import Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

HOP = {
    "host",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
}


def install(app):
    @app.api_route(
        "/{web_path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def website(request: Request, web_path: str):
        canonical = os.environ.get("HAYTILE_PUBLIC_ORIGIN", "").rstrip("/")
        origin = urlsplit(canonical)
        host = request.url.hostname or ""
        if (
            request.method in ("GET", "HEAD")
            and host.endswith(".onrender.com")
            and origin.scheme == "https"
            and origin.hostname != host
            and not web_path.startswith(("api/", "v1/", "_next/"))
            and (not web_path or "text/html" in request.headers.get("accept", ""))
        ):
            target = canonical + request.url.path
            if request.url.query:
                target += "?" + request.url.query
            return RedirectResponse(target, status_code=307)
        upstream = os.environ.get("HAYTILE_WEB_UPSTREAM")
        if not upstream or web_path == "v1" or web_path.startswith("v1/"):
            return Response(status_code=404)
        client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10), trust_env=False)
        try:
            url = (
                upstream.rstrip("/")
                + request.url.path
                + ("?" + request.url.query if request.url.query else "")
            )
            headers = [(k, v) for k, v in request.headers.raw if k.decode().lower() not in HOP]
            # Preserve the public host for Next's origin/routing logic.
            headers += [(b"host", request.headers.get("host", "localhost").encode())]
            response = await client.send(
                client.build_request(
                    request.method, url, headers=headers, content=request.stream()
                ),
                stream=True,
            )

            async def close():
                await response.aclose()
                await client.aclose()

            result = StreamingResponse(
                response.aiter_raw(),
                status_code=response.status_code,
                background=BackgroundTask(close),
            )
            result.raw_headers = [
                (k, v) for k, v in response.headers.raw if k.decode().lower() not in HOP
            ]
            return result
        except (httpx.HTTPError, OSError):
            await client.aclose()
            return Response("Web temporarily unavailable", status_code=502)
