"""Safe running-backend smoke: no real message bodies, no external sends."""

import json

from waha_local import AdapterError, httpx, load_config
from waha_ingress import local_binding


class SmokeFailure(Exception):
    pass


def require(condition, code):
    if not condition:
        raise SmokeFailure(code)


def main():
    binding = local_binding(load_config())
    base = "http://127.0.0.1:18702"
    with httpx.Client(
        base_url=base, timeout=10, trust_env=False, follow_redirects=False
    ) as client:
        require(client.get("/health").status_code == 200, "HEALTH_FAILED")
        require(
            client.get("/api/v1/connectors").status_code == 401,
            "UNAUTHENTICATED_CHECK_FAILED",
        )
        forged = client.post(
            f"/api/v1/connectors/waha/{binding.connection_id}/events",
            json={"synthetic": True},
            headers={"X-Webhook-Hmac": "0" * 128, "X-Webhook-Hmac-Algorithm": "sha512"},
        )
        require(forged.status_code == 401, "SIGNATURE_CHECK_FAILED")
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "merchant", "password": "demo-only-change-me"},
        )
        require(login.status_code == 200, "LOGIN_FAILED")
        require(
            login.json()["data"]["account_id"] == binding.account_id,
            "ACCOUNT_MAPPING_FAILED",
        )
        response = client.get("/api/v1/connectors")
        require(response.status_code == 200, "AUTHENTICATED_STATUS_FAILED")
        statuses = response.json()["items"]
        require(
            any(row["id"] == binding.connection_id for row in statuses),
            "CONNECTION_MAPPING_FAILED",
        )
        require(
            not any("secret" in row or "provider_chat_id" in row for row in statuses),
            "PRIVATE_DATA_EXPOSED",
        )
        issues = client.get(
            f"/api/v1/connectors/{binding.connection_id}/recovery-issues"
        )
        require(issues.status_code == 200, "RECOVERY_LIST_FAILED")
        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": login.json()["data"]["csrf_token"]},
        )
        require(logout.status_code == 200, "LOGOUT_FAILED")
    print(
        json.dumps(
            {"backend_http_checks": 7, "passed": True, "message_content_read": False}
        )
    )


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as exc:
        raise SystemExit("INGRESS_SMOKE_FAILED: " + str(exc)) from None
    except (AdapterError, httpx.HTTPError, AssertionError, KeyError, ValueError):
        raise SystemExit(
            "INGRESS_SMOKE_FAILED; inspect local service and private binding"
        ) from None
