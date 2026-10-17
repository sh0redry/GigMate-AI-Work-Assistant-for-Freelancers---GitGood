"""方案 §4.6 交付前检查与收尾: checklist, completion gate and archiving."""

from uuid import uuid4

from test_create_order import SAID, create, future


def checklist(client, order):
    response = client.get(f"/api/v1/work-orders/{order['id']}/checklist")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def post(client, headers, order, path, body):
    return client.post(
        f"/api/v1/work-orders/{order['id']}/{path}",
        json=body,
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )


def test_checklist_shows_confirmed_items_and_blocks_completion_until_acknowledged(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers, schedule=future(days=5), address="旺角").json()["data"]
    data = post(
        client,
        headers,
        order,
        "requirements",
        {
            "kind": "commitment",
            "text": "交精修图",
            "owner": "merchant",
            "sources": SAID,
            "expected_version": order["version"],
        },
    ).json()["data"]
    check = checklist(client, data)
    assert check["ready"] is False
    titles = [item["title"] for item in check["items"]]
    assert "地址：旺角" in titles
    assert "承诺未完成：交精修图" in titles
    blocked = post(
        client,
        headers,
        data,
        "status",
        {"status": "completed", "expected_version": data["version"]},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CHECKLIST_OPEN"
    assert blocked.json()["error"]["details"]["unfinished"] == ["承诺未完成：交精修图"]
    item = data["requirements"][0]
    data = post(
        client,
        headers,
        data,
        f"requirements/{item['id']}",
        {"status": "done", "expected_version": data["version"]},
    ).json()["data"]
    assert checklist(client, data)["ready"] is True
    done = post(
        client,
        headers,
        data,
        "status",
        {"status": "completed", "expected_version": data["version"]},
    )
    assert done.status_code == 200, done.text


def test_merchant_may_complete_with_open_items_by_acknowledging_them(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers, schedule=future(days=5)).json()["data"]
    started = post(
        client,
        headers,
        order,
        "status",
        {"status": "cancelled", "expected_version": order["version"]},
    )
    assert started.status_code == 200
    order = create(client, headers, schedule=future(days=6), address="中环").json()["data"]
    data = post(
        client,
        headers,
        order,
        "requirements",
        {
            "kind": "question",
            "text": "要不要电子版？",
            "owner": "customer",
            "sources": SAID,
            "expected_version": order["version"],
        },
    ).json()["data"]
    forced = post(
        client,
        headers,
        data,
        "status",
        {
            "status": "completed",
            "expected_version": data["version"],
            "acknowledge_open_items": True,
        },
    )
    assert forced.status_code == 200, forced.text


def test_archiving_hides_closed_orders_but_keeps_history(signed_in):
    client, _, _, headers = signed_in
    order = create(client, headers).json()["data"]
    assert (
        post(client, headers, order, "archive", {"expected_version": order["version"]}).status_code
        == 409
    )
    closed = post(
        client,
        headers,
        order,
        "status",
        {"status": "cancelled", "expected_version": order["version"]},
    ).json()["data"]
    archived = post(client, headers, closed, "archive", {"expected_version": closed["version"]})
    assert archived.status_code == 200, archived.text
    assert archived.json()["data"]["archived_at"]
    listed = {
        item["id"]
        for item in client.get("/api/v1/work-orders", params={"limit": 100}).json()["items"]
    }
    assert order["id"] not in listed
    everything = client.get(
        "/api/v1/work-orders", params={"limit": 100, "include_archived": True}
    ).json()
    assert order["id"] in {item["id"] for item in everything["items"]}
    assert client.get(f"/api/v1/work-orders/{order['id']}").status_code == 200
    again = post(
        client,
        headers,
        archived.json()["data"],
        "archive",
        {"expected_version": archived.json()["data"]["version"]},
    )
    assert again.status_code == 409
