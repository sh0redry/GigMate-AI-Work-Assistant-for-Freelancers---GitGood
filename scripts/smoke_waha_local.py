"""Exercise running local A-02 services using synthetic events only."""

import hashlib
import hmac
import json
from uuid import uuid4

from waha_local import AdapterError, httpx, load_config


def main():
    config = load_config()
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.get(config.base_url + "/api/sessions/default")
        assert response.status_code == 401, "WAHA must require credentials"
        base = "http://127.0.0.1:18701"
        assert client.get(base + "/health").json()["durable_acceptance"] is False
        assert client.get(base + "/probe/observations").status_code == 401
        raw = {
            "id": "synthetic-smoke-" + uuid4().hex,
            "event": "session.status",
            "session": "default",
            "timestamp": 1770000000000,
            "payload": {"status": "STARTING"},
        }

        def post(event, *, valid=True):
            body = json.dumps(event, separators=(",", ":")).encode()
            signature = hmac.new(
                config.webhook_secret.encode(), body, hashlib.sha512
            ).hexdigest()
            return client.post(
                base + "/probe/webhook",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Hmac-Algorithm": "sha512",
                    "X-Webhook-Hmac": signature if valid else "0" * 128,
                },
            )

        assert post(raw, valid=False).status_code == 401
        accepted = post(raw)
        assert accepted.status_code == 200
        assert accepted.json()["durable_acceptance"] is False
        assert accepted.headers["X-GigMate-Probe-Only"] == "true"
        duplicate = post(raw)
        assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
        assert post({**raw, "timestamp": raw["timestamp"] + 1}).status_code == 409
        assert post({**raw, "session": "synthetic-other"}).status_code == 403
        assert (
            post(
                {
                    **raw,
                    "id": "synthetic-rejected-" + uuid4().hex,
                    "event": "message.any",
                    "payload": {
                        "fromMe": False,
                        "from": "synthetic-unallowed@c.us",
                        "body": "synthetic content",
                    },
                }
            ).status_code
            == 403
        )
    print(json.dumps({"synthetic_http_checks": 9, "passed": True}))


if __name__ == "__main__":
    try:
        main()
    except (AdapterError, httpx.HTTPError, AssertionError, KeyError, ValueError):
        raise SystemExit("A02_SMOKE_FAILED; inspect local service state") from None
