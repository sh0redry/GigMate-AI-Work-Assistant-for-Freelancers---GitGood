"""Non-destructive smoke test against a running synthetic replay deployment."""

import argparse
import time
from uuid import uuid4

import httpx

ORDER = "00000000-0000-4000-8000-000000000003"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--password", default="demo-only-change-me")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        assert client.get("/health").json()["mode"] == "synthetic_replay"
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "merchant", "password": args.password},
        )
        login.raise_for_status()
        csrf = login.json()["data"]["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())}
        order_path = f"/api/v1/work-orders/{ORDER}"
        before = client.get(order_path).json()["data"]
        response = client.post(
            "/api/v1/replay", json={"scenario": "available"}, headers=headers
        )
        response.raise_for_status()
        expected = "2026-10-08T08:30:00Z"
        # A repeat run checks persistence instead of resetting the database.
        if before["fields"]["schedule"]["value"]["start_at"] != expected:
            change = None
            for _ in range(40):
                rows = client.get(order_path + "/changes").json()["items"]
                change = next(
                    (
                        row
                        for row in rows
                        if row["status"] == "proposed"
                        and row["new_value"]["start_at"] == expected
                    ),
                    None,
                )
                if change:
                    break
                time.sleep(0.25)
            assert change, "Worker did not produce the available-time proposal"
            context = client.get(
                "/api/v1/conversations/00000000-0000-4000-8000-000000000002"
            ).json()["data"]["context_version"]
            confirmation = client.post(
                order_path + f"/changes/{change['id']}/confirm",
                json={
                    "expected_version": before["version"],
                    "expected_context_version": context,
                    "apply_calendar_update": True,
                },
                headers={**headers, "Idempotency-Key": str(uuid4())},
            )
            confirmation.raise_for_status()
        after = client.get(order_path).json()["data"]
        assert after["fields"]["schedule"]["value"]["start_at"] == expected
        assert after["fields"]["address"]["value"] is None
        calendar = next(
            row
            for row in client.get("/api/v1/calendar-events").json()["items"]
            if row["work_order_id"] == ORDER
        )
        assert calendar["schedule"] == after["fields"]["schedule"]["value"]
        tasks = client.get("/api/v1/tasks").json()["items"]
        assert any(
            row["work_order_id"] == ORDER
            and row["state"] == "pending"
            and row["work_order_version"] == after["version"]
            for row in tasks
        )
        second = client.post(
            "/api/v1/replay",
            json={"scenario": "available"},
            headers={**headers, "Idempotency-Key": str(uuid4())},
        )
        assert second.json()["data"]["duplicate"]
        client.post("/api/v1/auth/logout", json={}, headers=headers).raise_for_status()
        assert client.get(order_path).status_code == 401
    print(
        "PASS: running web proxy, login, replay/worker, persisted confirmation, calendar/tasks, duplicate handling and logout."
    )


if __name__ == "__main__":
    main()
