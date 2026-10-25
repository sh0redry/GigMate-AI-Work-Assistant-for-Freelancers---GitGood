"""Split bubbles retain bounded context and exact source revisions; no vendor calls."""

import json
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_authorized_context import authorize, event, submit
from test_authorized_context import authorized_context as authorized_context
from test_extraction_batch3 import (
    _configure,
    _gate_open_provider,
    _request,
    _scripted_client,
    _suggestion_payload,
)
from test_waha_ingress import ingress as ingress

from gigmate.db import Job
from gigmate.extraction.disabled import DisabledProvider
from gigmate.extraction.registry import _reset_provider_for_testing
from gigmate.worker import run_once


def collect(ctx):
    class Spy(DisabledProvider):
        requests = []

        def propose(self, request):
            self.requests.append(request)
            return super().propose(request)

    spy = Spy()
    _reset_provider_for_testing(spy)
    try:
        while run_once(ctx.factory):
            pass
    finally:
        _reset_provider_for_testing()
    return spy.requests


def test_split_bubbles_reach_latest_model_call_with_original_sources(
    authorized_context, monkeypatch
):
    ctx = authorized_context
    authorize(ctx)
    submit(
        ctx,
        *event(ctx, body="Fictional photography at HKU", seconds=3, reference="synthetic:first"),
    )
    submit(
        ctx,
        *event(ctx, body="30 October, 3pm, budget 800", seconds=6, reference="synthetic:second"),
    )
    requests = collect(ctx)
    assert len(requests) == 1
    assert requests[0].message_text == "30 October, 3pm, budget 800"
    assert [m["text"] for m in requests[0].recent_messages] == [
        "Fictional photography at HKU",
        "30 October, 3pm, budget 800",
    ]
    assert len({m["message_id"] for m in requests[0].recent_messages}) == 2
    with ctx.factory() as db:
        assert sum(j.error_code == "SOURCE_SUPERSEDED" for j in db.scalars(select(Job))) == 1


def test_context_excludes_other_participants_and_revoked_or_old_revisions(
    authorized_context, monkeypatch
):
    ctx = authorized_context
    authorize(ctx)
    authorize(ctx, peer="syntheticother@lid")
    submit(
        ctx,
        *event(
            ctx,
            peer="syntheticother@lid",
            body="Other private request",
            reference="synthetic:other",
            seconds=3,
        ),
    )
    submit(ctx, *event(ctx, body="Old address", reference="synthetic:first", seconds=3))
    submit(
        ctx,
        *event(
            ctx,
            body="Revised address",
            reference="synthetic:first",
            kind="message.edited",
            seconds=6,
        ),
    )
    submit(ctx, *event(ctx, body="Revoked detail", reference="synthetic:revoked", seconds=9))
    submit(ctx, *event(ctx, reference="synthetic:revoked", kind="message.revoked", seconds=12))
    submit(ctx, *event(ctx, body="Latest time detail", reference="synthetic:last", seconds=15))
    request = next(r for r in collect(ctx) if r.message_text == "Latest time detail")
    assert [m["text"] for m in request.recent_messages] == ["Revised address", "Latest time detail"]
    assert request.recent_messages[0]["message_revision"] == 2


def test_context_is_bounded_by_time_and_message_count(authorized_context, monkeypatch):
    ctx = authorized_context
    authorize(ctx)
    submit(ctx, *event(ctx, body="Too old request", reference="synthetic:old", seconds=3))
    for i in range(12):
        submit(
            ctx, *event(ctx, body=f"Fragment {i}", reference=f"synthetic:f{i}", seconds=310 + i * 3)
        )
    request = collect(ctx)[0]
    assert len(request.recent_messages) == 8
    assert all("Too old" not in m["text"] for m in request.recent_messages)
    assert request.recent_messages[-1]["text"] == "Fragment 11"


def context_request():
    request = _request()
    earlier = str(uuid4())
    return replace(
        request,
        recent_messages=(
            {
                "message_id": earlier,
                "message_revision": 2,
                "text": "中环德辅道中 88 号",
                "occurred_at": request.message_received_at,
            },
            {
                "message_id": request.message_id,
                "message_revision": 1,
                "text": request.message_text,
                "occurred_at": request.message_received_at,
            },
        ),
    )


@pytest.mark.parametrize("source_kind", ["valid", "foreign", "stale"])
def test_model_sources_keep_earlier_bubble_and_refuse_fabricated_or_stale_refs(
    monkeypatch, source_kind
):
    _configure(monkeypatch)
    request = context_request()
    source = {"message_id": request.recent_messages[0]["message_id"], "message_revision": 2}
    if source_kind == "foreign":
        source["message_id"] = str(uuid4())
    if source_kind == "stale":
        source["message_revision"] = 1
    raw = _suggestion_payload()
    raw["new_work_order"]["fields"][0]["sources"] = [source]
    provider = _gate_open_provider(_scripted_client(raw))
    rendered = json.loads(provider._render_user_message(request))
    assert rendered["recent_messages"] == list(request.recent_messages)
    outcome = provider.propose(request)
    if source_kind == "valid":
        suggestion = outcome.proposal.new_work_order
        assert suggestion is not None
        assert suggestion.fields[0].sources[0].message_id == source["message_id"]
        assert suggestion.fields[0].sources[0].message_revision == 2
    else:
        assert outcome.proposal.new_work_order is None or not outcome.proposal.new_work_order.fields
        assert provider._bind_source(source, request)[0].startswith(
            "llm:response-provenance-failed:source-message"
        )


def test_new_bubble_during_model_call_is_included_in_next_call(authorized_context, monkeypatch):
    ctx = authorized_context
    authorize(ctx)
    submit(ctx, *event(ctx, body="Photography", seconds=3, reference="synthetic:first"))

    class Arriving(DisabledProvider):
        def propose(self, request):
            submit(
                ctx,
                *event(ctx, body="At HKU on 30 October", seconds=6, reference="synthetic:second"),
            )
            return super().propose(request)

    _reset_provider_for_testing(Arriving())
    try:
        assert run_once(ctx.factory)
    finally:
        _reset_provider_for_testing()
    request = collect(ctx)[0]
    assert [m["text"] for m in request.recent_messages] == ["Photography", "At HKU on 30 October"]


def test_context_byte_budget_does_not_truncate_source_text(authorized_context, monkeypatch):
    ctx = authorized_context
    authorize(ctx)
    for i in range(5):
        submit(
            ctx, *event(ctx, body="摄影" * 900, seconds=3 + i * 3, reference=f"synthetic:large{i}")
        )
    request = collect(ctx)[0]
    # At 5,400 bytes per bubble, two cannot fit: single-message handling remains.
    assert request.recent_messages == ()
    assert request.message_text == "摄影" * 900
