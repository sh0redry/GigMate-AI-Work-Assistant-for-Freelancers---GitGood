"""Bounded assistant batch 3 (ADR 0011): reply/polish drafts, invalidation, adoption.

Synthetic data and the offline composer only; nothing calls a model or sends.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_assistant_turns import app_message

from gigmate import assistant, assistant_drafts
from gigmate.assistant import dictated_text
from gigmate.db import (
    AgentDraftRow,
    AssistantDraft,
    AssistantTurn,
    ConversationRow,
    MessageRow,
    WahaSendAction,
    WorkOrderRow,
)
from gigmate.seed import uid

CONV, ORDER = uid(2), uid(3)


def chat(version=4, **extra):
    return {"conversation_id": CONV, "expected_context_version": version, **extra}


def with_order(version=4):
    return chat(version, work_order_id=ORDER, expected_work_order_version=3)


def ask(client, headers, question, context=None):
    body = {"question": question, **({"context": context} if context else {})}
    response = client.post(
        "/api/v1/assistant/turns", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
    )
    assert response.status_code == 202, response.text
    return response.json()["data"]["id"]


def run(client, factory, turn_id, **kwargs):
    assistant.run_once(factory, **kwargs)
    return client.get(f"/api/v1/assistant/turns/{turn_id}").json()["data"]


def consented(factory, text="周二下午可以吗？", at=None):
    """A consented live customer message in CONV; returns its source reference."""
    with factory.begin() as db:
        message = app_message(db, CONV, at or datetime.now(UTC), text)
    return {"message_id": message, "message_revision": 1}


def draft_of(client, done):
    draft_id = done["answer"]["draft_id"]
    return client.get(f"/api/v1/assistant/drafts/{draft_id}").json()["data"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("帮我回一下，说周二下午可以", "周二下午可以"),
        ("帮我回复说可以的", "可以的"),
        ("回复「好的，周二见」", "好的，周二见"),
        ("润色：明天上午十点到", "明天上午十点到"),
        ("Reply to them saying Tuesday works", "Tuesday works"),
        ("幫我回一下，話星期二下晝得", "星期二下晝得"),
        ("帮我回一下客户说的那条", None),
        ("帮我回一下", None),
    ],
)
def test_dictated_text(question, expected):
    assert dictated_text(question) == expected


def test_dictated_reply_becomes_an_unsent_bound_draft(signed_in):
    client, factory, _engine, headers = signed_in
    source = consented(factory)
    done = run(
        client,
        factory,
        ask(
            client,
            headers,
            "帮我回一下，说周二下午可以",
            {**with_order(), "selected_sources": [source]},
        ),
    )
    answer = done["answer"]
    assert (done["status"], done["intent"], answer["kind"]) == ("completed", "reply_draft", "draft")
    assert answer["execution_authority"] is False
    assert "您好，周二下午可以。谢谢！" in answer["text"]
    assert {"kind": "message", "message": source} in [
        {k: v for k, v in c.items() if v is not None} for c in answer["citations"]
    ]
    draft = draft_of(client, done)
    assert draft["text"] == "您好，周二下午可以。谢谢！"
    assert (draft["status"], draft["kind"], draft["sources"]) == (
        "proposed",
        "reply_draft",
        [source],
    )
    assert (draft["work_order_id"], draft["base_work_order_version"]) == (ORDER, 3)
    assert draft["context_version"] == 4 and draft["execution_authority"] is False
    with factory() as db:
        assert db.scalar(select(func.count(AgentDraftRow.id))) == 0
        assert db.scalar(select(func.count(WahaSendAction.id))) == 0


def test_reply_without_selection_answers_the_latest_consented_message(signed_in):
    client, factory, _engine, headers = signed_in
    now = datetime.now(UTC)
    consented(factory, "第一条", now - timedelta(seconds=30))
    latest = consented(factory, "第二条", now)
    done = run(client, factory, ask(client, headers, "帮我回一下，说收到", chat()))
    assert draft_of(client, done)["sources"] == [latest]
    assert draft_of(client, done)["work_order_id"] is None


def test_no_consented_message_means_no_draft(signed_in):
    client, factory, _engine, headers = signed_in
    # The seeded message is replay-only, so nothing may be cited.
    done = run(client, factory, ask(client, headers, "帮我回一下，说收到", chat()))
    assert done["answer"]["kind"] == "unsupported" and done["answer"]["draft_id"] is None
    with factory() as db:
        assert db.scalar(select(func.count(AssistantDraft.id))) == 0


def test_polish_needs_a_chat_and_cites_nothing(signed_in):
    client, factory, _engine, headers = signed_in
    unselected = run(client, factory, ask(client, headers, "润色：明天上午十点到"))
    assert unselected["intent"] == "clarify"
    done = run(client, factory, ask(client, headers, "帮我润色：明天上午十点到", chat()))
    draft = draft_of(client, done)
    assert (draft["kind"], draft["sources"], draft["text"]) == (
        "polish",
        [],
        "您好，明天上午十点到。谢谢！",
    )


def test_english_and_traditional_drafts(signed_in):
    client, factory, _engine, headers = signed_in
    consented(factory, "Is Tuesday ok?")
    english = draft_of(
        client,
        run(client, factory, ask(client, headers, "Reply to them saying Tuesday works", chat())),
    )
    assert english["text"] == "Hi, Tuesday works. Thanks!"
    traditional = draft_of(
        client,
        run(client, factory, ask(client, headers, "幫我回覆佢，話星期二下晝得", chat())),
    )
    assert traditional["text"] == "你好，星期二下晝得。多謝！"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            lambda db, src: setattr(db.get(ConversationRow, CONV), "context_version", 5),
            "context_changed",
        ),
        (
            lambda db, src: setattr(db.get(ConversationRow, CONV), "allowlisted", False),
            "consent_revoked",
        ),
        (
            lambda db, src: setattr(
                db.get(WorkOrderRow, ORDER),
                "data",
                {**db.get(WorkOrderRow, ORDER).data, "version": 4},
            ),
            "order_changed",
        ),
        (
            lambda db, src: db.add(
                MessageRow(
                    id=src["message_id"],
                    revision=2,
                    account_id=uid(1),
                    conversation_id=CONV,
                    provider_message_id="synthetic:edit-" + src["message_id"],
                    data={"text": "改了", "direction": "incoming", "source": "app"},
                )
            ),
            "source_changed",
        ),
    ],
)
def test_changed_bindings_revoke_an_unconsumed_draft_on_read(signed_in, change, reason):
    client, factory, _engine, headers = signed_in
    source = consented(factory)
    done = run(
        client,
        factory,
        ask(client, headers, "帮我回一下，说可以", {**with_order(), "selected_sources": [source]}),
    )
    draft_id = done["answer"]["draft_id"]
    with factory.begin() as db:
        change(db, source)
    view = client.get(f"/api/v1/assistant/drafts/{draft_id}").json()["data"]
    assert (view["status"], view["revoke_reason"]) == ("revoked", reason)
    refused = client.post(f"/api/v1/assistant/drafts/{draft_id}/consume", headers=headers)
    assert (refused.status_code, refused.json()["error"]["code"]) == (
        409,
        "ASSISTANT_DRAFT_NOT_USABLE",
    )


def test_consume_once_then_revocation_rules(signed_in):
    client, factory, _engine, headers = signed_in
    consented(factory)
    first = run(client, factory, ask(client, headers, "帮我回一下，说可以", chat()))["answer"][
        "draft_id"
    ]
    taken = client.post(f"/api/v1/assistant/drafts/{first}/consume", headers=headers)
    assert taken.status_code == 200 and taken.json()["data"]["status"] == "consumed"
    assert taken.json()["data"]["text"] == "您好，可以。谢谢！"
    again = client.post(f"/api/v1/assistant/drafts/{first}/consume", headers=headers)
    assert again.status_code == 409
    late = client.post(f"/api/v1/assistant/drafts/{first}/revoke", headers=headers)
    assert late.json()["error"]["code"] == "ASSISTANT_DRAFT_ALREADY_CONSUMED"
    second = run(client, factory, ask(client, headers, "帮我回一下，说好的", chat()))["answer"][
        "draft_id"
    ]
    revoked = client.post(f"/api/v1/assistant/drafts/{second}/revoke", headers=headers).json()[
        "data"
    ]
    assert (revoked["status"], revoked["revoke_reason"]) == ("revoked", "merchant")
    assert (
        client.post(f"/api/v1/assistant/drafts/{second}/consume", headers=headers).status_code
        == 409
    )


def test_drafts_expire(signed_in):
    client, factory, _engine, headers = signed_in
    consented(factory)
    draft_id = run(client, factory, ask(client, headers, "帮我回一下，说可以", chat()))["answer"][
        "draft_id"
    ]
    with factory.begin() as db:
        db.get(AssistantDraft, draft_id).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get(f"/api/v1/assistant/drafts/{draft_id}").json()["data"]["status"] == "expired"


def test_drafts_are_account_scoped_and_need_csrf(signed_in):
    client, factory, _engine, headers = signed_in
    consented(factory)
    draft_id = run(client, factory, ask(client, headers, "帮我回一下，说可以", chat()))["answer"][
        "draft_id"
    ]
    assert client.post(f"/api/v1/assistant/drafts/{draft_id}/consume").status_code == 403
    client.post("/api/v1/auth/logout", headers=headers)
    other = client.post(
        "/api/v1/auth/login", json={"username": "other", "password": "demo-only-change-me"}
    ).json()["data"]
    other_headers = {"X-CSRF-Token": other["csrf_token"]}
    assert client.get(f"/api/v1/assistant/drafts/{draft_id}").status_code == 404
    stolen = client.post(f"/api/v1/assistant/drafts/{draft_id}/consume", headers=other_headers)
    assert stolen.status_code == 404


class Composer:
    engine = "rules"

    def __init__(self, value=None, error=None, hook=None):
        self.value, self.error, self.hook, self.calls = value, error, hook, 0

    def compose(self, request):
        self.calls += 1
        if self.hook:
            self.hook(request)
        if self.error:
            raise self.error
        return json.dumps(self.value(request) if callable(self.value) else self.value)


def composition(request, **changes):
    value = {
        "schema_version": "1.0.0",
        "kind": "reply_draft",
        "language": "zh-Hans",
        "text": "您好，可以。",
        "sources": request["selected_sources"],
        "unverified_claims": [],
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    ("composer", "state", "code"),
    [
        (Composer(error=TimeoutError()), "unknown", "ASSISTANT_RESULT_UNKNOWN"),
        (
            Composer(
                lambda r: composition(
                    r, sources=[{"message_id": str(uuid4()), "message_revision": 1}]
                )
            ),
            "failed",
            "ASSISTANT_COMPOSITION_INVALID",
        ),
        (
            Composer(lambda r: composition(r, kind="polish")),
            "failed",
            "ASSISTANT_COMPOSITION_INVALID",
        ),
        (
            Composer(lambda r: composition(r, recipient="x")),
            "failed",
            "ASSISTANT_COMPOSITION_INVALID",
        ),
    ],
)
def test_composer_failures_never_store_a_draft(signed_in, composer, state, code):
    client, factory, _engine, headers = signed_in
    source = consented(factory)
    done = run(
        client,
        factory,
        ask(client, headers, "帮我回一下，说可以", chat(selected_sources=[source])),
        composer=composer,
    )
    assert (done["status"], done["error_code"], done["answer"]) == (state, code, None)
    assert assistant.run_once(factory, composer=composer) is False and composer.calls == 1
    with factory() as db:
        assert db.scalar(select(func.count(AssistantDraft.id))) == 0


def test_unverified_claims_are_carried_to_answer_and_draft(signed_in):
    client, factory, _engine, headers = signed_in
    source = consented(factory)
    composer = Composer(
        lambda r: composition(
            r, text="您好，两人拍摄报价 800 元。", unverified_claims=["报价 800 元"]
        )
    )
    done = run(
        client,
        factory,
        ask(client, headers, "帮我回一下报价", chat(selected_sources=[source])),
        composer=composer,
    )
    assert done["answer"]["unverified_claims"] == ["报价 800 元"]
    assert draft_of(client, done)["unverified_claims"] == ["报价 800 元"]


def test_a_message_arriving_during_composition_supersedes_the_turn(signed_in):
    client, factory, _engine, headers = signed_in
    source = consented(factory)

    def arrive(_request):
        with factory.begin() as db:
            db.get(ConversationRow, CONV).context_version = 5

    turn = ask(client, headers, "帮我回一下，说可以", chat(selected_sources=[source]))
    done = run(client, factory, turn, composer=Composer(composition, hook=arrive))
    assert (done["status"], done["error_code"]) == ("superseded", "ASSISTANT_CONTEXT_STALE")
    with factory() as db:
        assert db.scalar(select(func.count(AssistantDraft.id))) == 0


def test_a_lost_lease_during_composition_stores_nothing(signed_in):
    client, factory, _engine, headers = signed_in
    source = consented(factory)
    turn = ask(client, headers, "帮我回一下，说可以", chat(selected_sources=[source]))

    def steal(_request):
        with factory.begin() as db:
            db.get(AssistantTurn, turn).lease_token = str(uuid4())

    assistant.run_once(factory, composer=Composer(composition, hook=steal))
    with factory() as db:
        row = db.get(AssistantTurn, turn)
        assert (row.state, row.answer) == ("running", None)
        assert db.scalar(select(func.count(AssistantDraft.id))) == 0


def test_draft_text_is_scrubbed_after_retention(signed_in):
    client, factory, _engine, headers = signed_in
    consented(factory)
    draft_id = run(client, factory, ask(client, headers, "帮我回一下，说可以", chat()))["answer"][
        "draft_id"
    ]
    with factory.begin() as db:
        db.get(AssistantDraft, draft_id).created_at = datetime.now(UTC) - timedelta(days=31)
    assert assistant_drafts.scrub(factory) == 1
    view = client.get(f"/api/v1/assistant/drafts/{draft_id}").json()["data"]
    assert view["text"] is None and view["scrubbed_at"]


def test_logs_never_contain_draft_text(signed_in, caplog):
    client, factory, _engine, headers = signed_in
    caplog.set_level(logging.DEBUG)
    consented(factory, "机密客户原文")
    run(client, factory, ask(client, headers, "帮我回一下，说机密回复内容", chat()))
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert "机密" not in joined
