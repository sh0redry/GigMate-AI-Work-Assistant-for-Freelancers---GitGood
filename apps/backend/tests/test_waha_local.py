"""A-02 local client/security tests with mock HTTP; never pair a real account."""

import hashlib
import hmac
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from gigmate.waha_adapter import AdapterError
from gigmate.waha_client import MAX_RESPONSE, PNG_SIGNATURE, LocalWahaClient, LocalWahaConfig
from gigmate.waha_probe import MAX_BODY, create_probe, verify_hmac


@pytest.fixture
def config():
    return LocalWahaConfig(
        base_url="http://127.0.0.1:18700",
        account_id="00000000-0000-4000-8000-000000000001",
        session="default",
        api_key="synthetic-api-key-" + "a" * 32,
        webhook_secret="synthetic-webhook-secret-" + "b" * 32,
        allowlisted_chats=frozenset({"synthetic:customer-chat"}),
    )


def raw_message():
    return {
        "id": "synthetic:event-1",
        "event": "message.any",
        "session": "default",
        "timestamp": 1790899200000,
        "payload": {
            "id": "synthetic:message-1",
            "fromMe": False,
            "from": "synthetic:customer-chat",
            "body": "private-test-marker",
        },
    }


def signed(config, raw=None, body=None):
    if body is None:
        body = json.dumps(raw if raw is not None else raw_message()).encode()
    return body, {
        "Content-Type": "application/json",
        "X-Webhook-Hmac-Algorithm": "sha512",
        "X-Webhook-Hmac": hmac.new(
            config.webhook_secret.encode(), body, hashlib.sha512
        ).hexdigest(),
    }


def status_response(state="WORKING", engine="WEBJS"):
    return {
        "name": "default",
        "status": state,
        "engine": {"engine": engine},
        "config": {"credential": "private-server-secret"},
        "me": {"id": "private-phone"},
    }


def test_official_hmac_vector_and_raw_body_changes():
    body = b'{"event":"message","session":"default","engine":"WEBJS"}'
    signature = (
        "208f8a55dde9e05519e898b10b89bf0d0b3b0fdf11fdbf09b6b90476301b98d8097c"
        "462b2b17a6ce93b6b47a136cf2e78a33a63f6752c2c1631777076153fa89"
    )
    verify_hmac(body, signature, "sha512", "my-secret-key")
    with pytest.raises(AdapterError, match="WEBHOOK_AUTH_REJECTED"):
        verify_hmac(body + b" ", signature, "sha512", "my-secret-key")


@pytest.mark.parametrize(
    "signature, algorithm",
    [(None, "sha512"), ("x" * 128, "sha512"), ("0" * 128, "sha256"), ("0" * 128, None)],
)
def test_invalid_authentication_does_not_parse_or_echo_body(config, signature, algorithm):
    client = TestClient(create_probe(config))
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Webhook-Hmac"] = signature
    if algorithm is not None:
        headers["X-Webhook-Hmac-Algorithm"] = algorithm
    response = client.post("/probe/webhook", content=b"private-test-marker", headers=headers)
    assert response.status_code == 401
    assert "private" not in response.text


def test_probe_never_claims_business_acceptance_and_stores_no_text(config):
    client = TestClient(create_probe(config))
    body, headers = signed(config)
    first = client.post("/probe/webhook", content=body, headers=headers)
    second = client.post("/probe/webhook", content=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert (
        not first.json()["durable_acceptance"] and first.headers["X-GigMate-Probe-Only"] == "true"
    )
    assert second.json()["duplicate"]
    assert client.get("/probe/observations").status_code == 401
    result = client.get(
        "/probe/observations", headers={"Authorization": "Bearer " + config.api_key}
    )
    assert result.json()["counts"] == {"observed": 1, "duplicate": 1, "identity_conflict": 0}
    assert "private-test-marker" not in result.text and config.webhook_secret not in result.text
    assert "synthetic:customer-chat" not in result.text


def test_signed_changed_identity_is_conflict_without_raw_response(config):
    client = TestClient(create_probe(config))
    body, headers = signed(config)
    assert client.post("/probe/webhook", content=body, headers=headers).status_code == 200
    raw = raw_message()
    raw["payload"]["body"] = "new-private-marker"
    body, headers = signed(config, raw)
    response = client.post("/probe/webhook", content=body, headers=headers)
    assert response.status_code == 409
    assert "private" not in response.text


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ({"session": "foreign"}, 403),
        ({"event": "message.reaction"}, 422),
        ({"id": None}, 422),
        ({"payload": {"fromMe": False, "from": "foreign-chat", "body": "private-marker"}}, 403),
        ({"payload": {"fromMe": "false", "from": "synthetic:customer-chat"}}, 422),
    ],
)
def test_valid_signature_still_requires_owned_session_allowlist_and_shape(
    config, mutation, expected
):
    client = TestClient(create_probe(config))
    raw = {**raw_message(), **mutation}
    body, headers = signed(config, raw)
    response = client.post("/probe/webhook", content=body, headers=headers)
    assert response.status_code == expected and "private" not in response.text
    stats = client.get("/probe/observations", headers={"Authorization": "Bearer " + config.api_key})
    assert stats.json()["counts"]["observed"] == 0


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"[]",
        b'{"session":"default","session":"foreign"}',
        b'{"value":NaN}',
        b"\xff",
        b"[" * 2000,
    ],
)
def test_signed_invalid_json_has_safe_failure(config, body):
    client = TestClient(create_probe(config))
    body, headers = signed(config, body=body)
    assert client.post("/probe/webhook", content=body, headers=headers).status_code == 422


def test_stream_body_limit_and_duplicate_signature_headers(config):
    client = TestClient(create_probe(config))
    body, headers = signed(config, body=b"x" * (MAX_BODY + 1))
    assert client.post("/probe/webhook", content=body, headers=headers).status_code == 413
    body, headers = signed(config)
    pairs = list(headers.items()) + [("X-Webhook-Hmac", headers["X-Webhook-Hmac"])]
    assert client.post("/probe/webhook", content=body, headers=pairs).status_code == 401


def test_revoked_consent_and_no_allowlist_block_content(config):
    for other in (
        replace(config, consent_active=False),
        replace(config, allowlisted_chats=frozenset()),
    ):
        client = TestClient(create_probe(other))
        body, headers = signed(config)
        assert client.post("/probe/webhook", content=body, headers=headers).status_code == 403


def test_session_notification_needs_no_business_chat_and_discards_qr(config):
    raw = {
        "id": "synthetic:session-event",
        "event": "session.status",
        "session": "default",
        "payload": {"status": "SCAN_QR_CODE", "qr": "private-qr-material"},
    }
    client = TestClient(create_probe(replace(config, allowlisted_chats=frozenset())))
    body, headers = signed(config, raw)
    assert client.post("/probe/webhook", content=body, headers=headers).status_code == 200
    result = client.get(
        "/probe/observations", headers={"Authorization": "Bearer " + config.api_key}
    )
    assert "private-qr" not in result.text


def test_volatile_identity_cache_is_bounded(config):
    from gigmate.waha_probe import ProbeObservations

    observations = ProbeObservations()
    for number in range(101):
        raw = raw_message()
        raw["id"] = f"synthetic:event-{number}"
        observations.observe(raw, config)
    assert len(observations.identities) == 100
    assert observations.counts["observed"] == 101


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://user:secret@localhost",
        "http://localhost?key=secret",
        "http://localhost/api",
        "file:///tmp/x",
        "http://127.0.0.1:wrong",
        "http://localhost#x",
    ],
)
def test_client_rejects_nonlocal_or_credential_urls(config, url):
    with pytest.raises(AdapterError, match="LOCAL_WAHA_URL_REQUIRED"):
        replace(config, base_url=url)


def test_config_hides_credentials_and_requires_explicit_session(config):
    assert config.api_key not in repr(config) and config.webhook_secret not in repr(config)
    with pytest.raises(AdapterError, match="LOCAL_DEFAULT_SESSION_REQUIRED"):
        replace(config, session="other")
    with pytest.raises(AdapterError, match="STRONG_LOCAL_SECRET_REQUIRED"):
        replace(config, api_key="short")


def test_create_has_hmac_safe_subscriptions_and_no_automatic_retries(config):
    requests = []

    def handler(request):
        requests.append(request)
        data = json.loads(request.content)
        webhook = data["config"]["webhooks"][0]
        assert webhook["hmac"]["key"] == config.webhook_secret
        assert webhook["url"] == "http://probe:18701/probe/webhook"
        assert "message.any" in webhook["events"] and "message" not in webhook["events"]
        assert request.headers["X-Api-Key"] == config.api_key
        return httpx.Response(201, json={"name": "default"})

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        assert client.create_session()["session_created"]
        assert len(requests) == 1
    finally:
        client.close()


def test_status_and_qr_never_expose_server_credentials(config):
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path.endswith("/auth/qr"):
            return httpx.Response(
                200, content=PNG_SIGNATURE + b"synthetic-qr", headers={"content-type": "image/png"}
            )
        return httpx.Response(200, json=status_response("SCAN_QR_CODE"))

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        assert "private" not in json.dumps(client.status())
        assert client.qr().startswith(PNG_SIGNATURE)
    finally:
        client.close()


@pytest.mark.parametrize(
    "payload, code",
    [
        (status_response(engine="NOWEB"), "WAHA_ENGINE_MISMATCH"),
        (status_response(state="UNKNOWN"), "WAHA_UNKNOWN_STATE"),
        ({"name": "foreign"}, "WAHA_SESSION_MISMATCH"),
    ],
)
def test_status_checks_pinned_engine_state_and_identity(config, payload, code):
    client = LocalWahaClient(
        config, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    try:
        with pytest.raises(AdapterError, match=code):
            client.status()
    finally:
        client.close()


@pytest.mark.parametrize(
    "status, code",
    [
        (401, "WAHA_AUTH_REJECTED"),
        (403, "WAHA_AUTH_REJECTED"),
        (404, "WAHA_RESOURCE_NOT_FOUND"),
        (409, "WAHA_STATE_CONFLICT"),
        (500, "WAHA_HTTP_FAILED"),
        (302, "WAHA_HTTP_FAILED"),
    ],
)
def test_http_failure_does_not_expose_content_or_follow_redirect(config, status, code):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, text="private-server-secret", headers={"Location": "https://foreign.example"}
        )

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AdapterError, match=code) as failure:
            client.status()
        assert "private" not in str(failure.value) and len(requests) == 1
    finally:
        client.close()


def test_session_creation_timeout_is_unknown_without_resend(config):
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("private-server-secret", request=request)

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AdapterError, match="WAHA_RESULT_UNKNOWN"):
            client.create_session()
        assert len(requests) == 1
        with pytest.raises(AdapterError, match="WAHA_UNAVAILABLE"):
            client.status()
    finally:
        client.close()


def test_history_is_allowlisted_encoded_bounded_and_content_free(config):
    chat = "synthetic:customer/chat@c.us"
    config = replace(config, allowlisted_chats=frozenset({chat}))
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/messages"):
            assert b"%2F" in request.url.raw_path and request.url.params["downloadMedia"] == "false"
            return httpx.Response(200, json=[{"body": "private-message"}])
        return httpx.Response(200, json=status_response())

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AdapterError, match="CONVERSATION_NOT_ALLOWED"):
            client.history("foreign")
        assert not requests
        with pytest.raises(AdapterError, match="INVALID_HISTORY_RANGE"):
            client.history(chat, limit=101)
        assert not requests
        result = client.history(chat)
        assert result["available_records"] == 1 and not result["complete_history"]
        assert "private" not in json.dumps(result)
    finally:
        client.close()


def test_response_size_bound_and_invalid_json(config):
    for body, code in [
        (b"x" * (MAX_RESPONSE + 1), "WAHA_RESPONSE_TOO_LARGE"),
        (b"private-invalid-json", "WAHA_INVALID_RESPONSE"),
    ]:
        client = LocalWahaClient(
            config, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
        )
        try:
            with pytest.raises(AdapterError, match=code):
                client.status()
        finally:
            client.close()


def test_private_cli_initialization_does_not_overwrite_or_print_secrets(
    tmp_path, monkeypatch, capsys
):
    from scripts import waha_local

    monkeypatch.setattr(waha_local, "ROOT", tmp_path)
    assert waha_local.main(["init"]) == 0
    config_data = json.loads((tmp_path / "local-data/waha-a02/config.json").read_text())
    output = capsys.readouterr().out
    assert config_data["api_key"] not in output and config_data["webhook_secret"] not in output
    assert waha_local.load_config().allowlisted_chats == frozenset()
    before = (tmp_path / "local-data/waha-a02/config.json").read_bytes()
    with pytest.raises(AdapterError, match="LOCAL_CONFIG_EXISTS"):
        waha_local.initialize()
    assert (tmp_path / "local-data/waha-a02/config.json").read_bytes() == before


def test_recovery_preserves_session_without_logout_or_recreate(config):
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={**status_response(), "status": "FAILED"})
        return httpx.Response(200, json={"name": "default", "status": "STARTING"})

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        assert client.restart_failed_session()["restart_requested"] is True
        assert requests == [
            ("GET", "/api/sessions/default"),
            ("POST", "/api/sessions/default/restart"),
        ]
    finally:
        client.close()


def test_recovery_does_not_interrupt_working_connection(config):
    requests = []

    def handler(request):
        requests.append(request.method)
        return httpx.Response(200, json={**status_response(), "status": "WORKING"})

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AdapterError, match="WAHA_RECOVERY_NOT_REQUIRED"):
            client.restart_failed_session()
        assert requests == ["GET"]
    finally:
        client.close()


def test_recovery_timeout_never_blindly_retries(config):
    requests = []

    def handler(request):
        requests.append(request.method)
        if request.method == "GET":
            return httpx.Response(200, json={**status_response(), "status": "FAILED"})
        raise httpx.ReadTimeout("private error", request=request)

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AdapterError, match="WAHA_RESULT_UNKNOWN"):
            client.restart_failed_session()
        assert requests == ["GET", "POST"]
    finally:
        client.close()


def test_chat_discovery_returns_only_metadata_without_allowlist(config):
    config = replace(config, allowlisted_chats=frozenset())

    def handler(request):
        if request.url.path == "/api/default/chats":
            assert dict(request.url.params) == {
                "limit": "20",
                "offset": "0",
                "sortBy": "conversationTimestamp",
                "sortOrder": "desc",
            }
            return httpx.Response(
                200,
                json=[
                    {
                        "id": {"_serialized": "123@lid", "user": "123", "server": "lid"},
                        "name": "Synthetic contact",
                        "lastMessage": {"body": "private"},
                    },
                    {"id": "456@g.us", "name": "Synthetic group", "_data": {"body": "private"}},
                    {"id": "status@broadcast", "name": "Skip"},
                ],
            )
        return httpx.Response(200, json={**status_response(), "status": "WORKING"})

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        result = client.recent_chats()
        assert result == [
            {"id": "123@lid", "name": "Synthetic contact"},
            {"id": "456@g.us", "name": "Synthetic group"},
        ]
        assert "private" not in json.dumps(result)
    finally:
        client.close()


def test_chat_discovery_checks_range_before_network(config):
    requests = []
    client = LocalWahaClient(
        config, transport=httpx.MockTransport(lambda req: requests.append(req))
    )
    try:
        with pytest.raises(AdapterError, match="INVALID_CHAT_RANGE"):
            client.recent_chats(limit=101)
        assert not requests
    finally:
        client.close()


@pytest.mark.parametrize(
    "rows",
    [
        [{"id": "123@lid"}, {"id": "123@lid"}],
        [{"id": "123\n@lid"}],
        [{"id": "123@lid", "name": {"private": "data"}}],
    ],
)
def test_chat_discovery_rejects_invalid_metadata(config, rows):
    def handler(request):
        if request.url.path == "/api/default/chats":
            return httpx.Response(200, json=rows)
        return httpx.Response(200, json={**status_response(), "status": "WORKING"})

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AdapterError, match="WAHA_INVALID_RESPONSE"):
            client.recent_chats()
    finally:
        client.close()


def test_local_selection_cancel_invalid_and_unique_indices():
    from scripts.waha_local import parse_selection

    assert parse_selection("", 3) == []
    assert parse_selection("1,3,1", 3) == [0, 2]
    for answer in ["0", "4", "1,,3", "name", "1.5"]:
        with pytest.raises(AdapterError, match="INVALID_CHAT_SELECTION"):
            parse_selection(answer, 3)


def test_selected_chats_merge_atomically_preserving_secrets(tmp_path, monkeypatch):
    from scripts import waha_local

    monkeypatch.setattr(waha_local, "ROOT", tmp_path)
    waha_local.initialize()
    target = tmp_path / "local-data/waha-a02/config.json"
    original = target.read_bytes()
    waha_local.save_selected_chats(["123@lid", "123@lid", "456@g.us"], original)
    saved = json.loads(target.read_bytes())
    assert saved["allowlisted_chats"] == ["123@lid", "456@g.us"]
    prior = json.loads(original)
    for field in prior.keys() - {"allowlisted_chats"}:
        assert saved[field] == prior[field]
    snapshot = target.read_bytes()
    with pytest.raises(AdapterError, match="LOCAL_CONFIG_CHANGED"):
        waha_local.save_selected_chats(["789@c.us"], original)
    assert target.read_bytes() == snapshot
    assert not list(target.parent.glob("*.tmp"))


def test_business_callback_configuration_preserves_other_settings(config):
    requests = []

    def handler(request):
        requests.append(request.method)
        if request.method == "PUT":
            body = json.loads(request.content)
            assert body["config"]["debug"] is False
            assert body["config"]["webjs"]["custom"] == "synthetic-setting"
            webhook = body["config"]["webhooks"][0]
            assert (
                webhook["url"]
                == "http://ingress:8000/api/v1/connectors/waha/00000000-0000-4000-8000-000000000008/events"
            )
            assert webhook["hmac"]["key"] == config.webhook_secret
            assert "message" not in webhook["events"]
            return httpx.Response(200, json={"name": "default"})
        return httpx.Response(
            200,
            json={
                **status_response(),
                "config": {
                    "debug": False,
                    "webjs": {"custom": "synthetic-setting"},
                    "webhooks": [{"url": "http://probe:18701/probe/webhook"}],
                },
            },
        )

    client = LocalWahaClient(config, transport=httpx.MockTransport(handler))
    try:
        result = client.configure_business_webhook("00000000-0000-4000-8000-000000000008")
        assert requests == ["GET", "GET", "PUT"]
        assert result["business_webhook_configured"] is True
        assert config.webhook_secret not in json.dumps(result)
    finally:
        client.close()
