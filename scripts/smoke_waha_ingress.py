"""Safe running-backend smoke: no real message bodies, no external sends."""

import json

from waha_local import AdapterError, httpx, load_config
from waha_ingress import local_binding


def main():
    binding = local_binding(load_config())
    base = "http://127.0.0.1:18702"
    with httpx.Client(
        base_url=base, timeout=10, trust_env=False, follow_redirects=False
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/connectors").status_code == 401
        forged = client.post(
            f"/api/v1/connectors/waha/{binding.connection_id}/events",
            json={"synthetic": True},
            headers={"X-Webhook-Hmac": "0" * 128, "X-Webhook-Hmac-Algorithm": "sha512"},
        )
        assert forged.status_code == 401
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "merchant", "password": "demo-only-change-me"},
        )
        assert login.status_code == 200
        assert login.json()["data"]["account_id"] == binding.account_id
        response = client.get("/api/v1/connectors")
        assert response.status_code == 200
        statuses = response.json()["items"]
        assert any(row["id"] == binding.connection_id for row in statuses)
        assert not any("secret" in row or "provider_chat_id" in row for row in statuses)
        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": login.json()["data"]["csrf_token"]},
        )
        assert logout.status_code == 200
    print(
        json.dumps(
            {"backend_http_checks": 6, "passed": True, "message_content_read": False}
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (AdapterError, httpx.HTTPError, AssertionError, KeyError, ValueError):
        raise SystemExit(
            "INGRESS_SMOKE_FAILED; inspect local service and private binding"
        ) from None
