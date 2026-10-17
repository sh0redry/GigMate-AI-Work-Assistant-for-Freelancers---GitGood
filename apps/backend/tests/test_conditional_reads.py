from gigmate.db import ConversationRow, WorkOrderRow
from gigmate.seed import uid


def test_unchanged_private_read_has_weak_etag_and_empty_304(signed_in):
    client, _, _, _ = signed_in
    first = client.get("/api/v1/work-orders")
    assert first.status_code == 200
    tag = first.headers["etag"]
    assert tag.startswith('W/"')
    assert "no-store" in first.headers["cache-control"]
    assert "private" in first.headers["cache-control"]
    assert "Cookie" in first.headers["vary"]
    second = client.get("/api/v1/work-orders", headers={"If-None-Match": tag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["x-request-id"] != first.headers["x-request-id"]


def test_changed_payload_returns_new_data_not_304(signed_in):
    client, factory, _, _ = signed_in
    first = client.get("/api/v1/work-orders")
    order_id = first.json()["items"][0]["id"]
    with factory.begin() as db:
        row = db.get(WorkOrderRow, order_id)
        value = dict(row.data)
        value["summary"] = "Synthetic changed summary"
        row.data = value
    second = client.get("/api/v1/work-orders", headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 200
    assert second.headers["etag"] != first.headers["etag"]
    assert second.json()["items"][0]["summary"] == "Synthetic changed summary"


def test_conditional_read_rechecks_authentication_and_source_access(signed_in):
    client, factory, _, _ = signed_in
    route = f"/api/v1/conversations/{uid(2)}/messages"
    tag = client.get(route).headers["etag"]
    with factory.begin() as db:
        db.get(ConversationRow, uid(2)).allowlisted = False
    denied = client.get(route, headers={"If-None-Match": tag})
    assert denied.status_code in (403, 404)
    assert "etag" not in denied.headers
    client.cookies.clear()
    expired = client.get(route, headers={"If-None-Match": tag})
    assert expired.status_code == 401
    assert "etag" not in expired.headers


def test_public_health_and_auth_writes_never_get_conditional_etags(environment):
    client, _, _ = environment
    assert "etag" not in client.get("/health").headers
    login = client.post(
        "/api/v1/auth/login", json={"username": "merchant", "password": "demo-only-change-me"}
    )
    assert login.status_code == 200
    assert "etag" not in login.headers
