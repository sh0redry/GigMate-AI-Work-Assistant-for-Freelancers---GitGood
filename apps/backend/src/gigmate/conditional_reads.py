"""Conditional JSON reads after route execution, authentication and ownership checks."""

import hashlib
import json
import re

from starlette.requests import Request
from starlette.responses import Response


async def conditional_read(request: Request, response: Response) -> Response:
    path = request.url.path
    if (
        request.method != "GET"
        or response.status_code != 200
        or not request.cookies.get("gigmate_session")
        or not path.startswith("/api/v1/")
        or re.search(r"/(auth|replay)(/|$)|/qr$|/content$|\.ics$", path)
        or "application/json" not in response.headers.get("content-type", "")
        or not response.headers.get("content-length", "").isdigit()
        or int(response.headers["content-length"]) > 2 * 1024 * 1024
    ):
        return response
    body = b"".join([part async for part in response.body_iterator])
    payload = json.loads(body)
    if isinstance(payload, dict):
        payload.pop("request_id", None)  # transport trace, not business state
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    tag = 'W/"' + hashlib.sha256(canonical).hexdigest() + '"'
    headers = dict(response.headers)
    headers["etag"] = tag
    headers["cache-control"] = "private, no-store"
    headers["vary"] = ", ".join(filter(None, [headers.get("vary"), "Cookie"]))
    # The route has already rechecked the current session and authorization.
    matches = request.headers.get("if-none-match", "").split(",")
    if any(candidate.strip() == tag for candidate in matches):
        headers.pop("content-length", None)
        return Response(status_code=304, headers=headers)
    return Response(body, status_code=200, headers=headers)
