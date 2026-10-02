"""A-01 synthetic behavior tests; no database, network or connector credentials."""

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from gigmate.waha_adapter import (
    ROOT,
    AdapterError,
    normalize_event,
    semantic_digest,
    validate_event,
)
from gigmate.waha_replay import ReplayLedger, load_cases

CASES = load_cases()
RECEIPT = datetime(2026, 10, 2, 0, 0, 10, tzinfo=UTC)


def case(name):
    return deepcopy(next(item for item in CASES if item["name"] == name))


def normalized(name="text-created"):
    item = case(name)
    return normalize_event(item["raw"], item["context"], received_at=RECEIPT)


@pytest.mark.parametrize("item", CASES, ids=[item["name"] for item in CASES])
def test_manifest_cases_match_contract_or_safe_error(item):
    if "error" in item["expect"]:
        with pytest.raises(AdapterError) as failure:
            normalize_event(item["raw"], item["context"], received_at=RECEIPT)
        assert failure.value.code == item["expect"]["error"]
    else:
        result = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
        validate_event(result)
        assert all(result[key] == value for key, value in item["expect"].items())


def test_redelivery_keeps_identity_and_semantics_but_changes_receipt():
    item = case("text-created")
    original = deepcopy(item["raw"])
    first = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    second = normalize_event(item["raw"], item["context"], received_at=RECEIPT + timedelta(hours=1))
    assert first["event_id"] == second["event_id"]
    assert first["received_at"] != second["received_at"]
    assert semantic_digest(first) == semantic_digest(second)
    assert item["raw"] == original
    assert first["occurred_at"] == "2026-10-02T00:00:00Z"


def test_event_identity_is_scoped_to_instance_account_and_session():
    item = case("text-created")
    first = normalized()
    for context in (
        replace(item["context"], instance_id="synthetic:instance-2"),
        replace(item["context"], account_id="00000000-0000-4000-8000-000000000099"),
        replace(item["context"], session_id="synthetic:session-2"),
    ):
        raw = {**item["raw"], "session": context.session_id}
        other = normalize_event(raw, context, received_at=RECEIPT)
        assert other["event_id"] != first["event_id"]


def test_edit_and_revoke_resolve_original_identity_not_action_id():
    created, edited, revoked = (
        normalized(name) for name in ("text-created", "text-edited", "text-revoked")
    )
    assert len({event["event_id"] for event in (created, edited, revoked)}) == 3
    assert {event["provider_message_id"] for event in (created, edited, revoked)} == {
        "synthetic:original-message"
    }
    assert {event["payload"]["message_id"] for event in (created, edited, revoked)} == {
        "00000000-0000-4000-8000-000000000005"
    }
    assert list(revoked["payload"]) == ["message_id"]


@pytest.mark.parametrize("event_name", ["text-edited", "text-revoked"])
def test_missing_mutation_target_is_not_replaced_by_action_identity(event_name):
    item = case(event_name)
    item["raw"]["payload"].pop(
        "editedMessageId" if event_name == "text-edited" else "revokedMessageId"
    )
    with pytest.raises(AdapterError, match="^INVALID_PROVIDER_SHAPE$"):
        normalize_event(item["raw"], item["context"], received_at=RECEIPT)


@pytest.mark.parametrize("timestamp", [None, "1790899200000", -1, 1.5, 10**100, [], {}])
def test_timestamp_is_explicit_milliseconds_without_guessing(timestamp):
    item = case("text-created")
    item["raw"]["timestamp"] = timestamp
    with pytest.raises(AdapterError, match="^INVALID_TIMESTAMP$"):
        normalize_event(item["raw"], item["context"], received_at=RECEIPT)


def test_receipt_requires_timezone_and_utc_conversion_is_exact():
    item = case("text-created")
    with pytest.raises(AdapterError, match="^INVALID_TIMESTAMP$"):
        normalize_event(item["raw"], item["context"], received_at=datetime(2026, 10, 2))
    received = datetime.fromisoformat("2026-10-02T08:00:10+08:00")
    assert (
        normalize_event(item["raw"], item["context"], received_at=received)["received_at"]
        == "2026-10-02T00:00:10Z"
    )


@pytest.mark.parametrize("bad_raw", [None, [], "private text", {}, {"session": None}])
def test_malformed_provider_input_has_safe_error(bad_raw):
    with pytest.raises(AdapterError):
        normalize_event(bad_raw, case("text-created")["context"], received_at=RECEIPT)


@pytest.mark.parametrize("revision", [True, 0, -1, "1", 1.5])
def test_invalid_resolved_revision_is_rejected(revision):
    item = case("text-created")
    context = replace(item["context"], message=replace(item["context"].message, revision=revision))
    with pytest.raises(AdapterError, match="^INVALID_TRUSTED_MAPPING$"):
        normalize_event(item["raw"], context, received_at=RECEIPT)


@pytest.mark.parametrize("field", ["account_id", "conversation_id", "message_id"])
def test_application_ids_must_be_canonical_uuid(field):
    item = case("text-created")
    if field == "account_id":
        context = replace(item["context"], account_id="not-a-uuid")
    else:
        context = replace(
            item["context"], message=replace(item["context"].message, **{field: "not-a-uuid"})
        )
    with pytest.raises(AdapterError, match="^INVALID_TRUSTED_MAPPING$"):
        normalize_event(item["raw"], context, received_at=RECEIPT)


@pytest.mark.parametrize("flag", ["source_verified", "consent_active"])
def test_trust_flags_cannot_be_truthy_strings(flag):
    item = case("text-created")
    context = replace(item["context"], **{flag: "true"})
    with pytest.raises(AdapterError):
        normalize_event(item["raw"], context, received_at=RECEIPT)


def test_forged_provider_metadata_does_not_control_account_or_revision():
    item = case("text-created")
    item["raw"].update(
        account_id="forged",
        message_revision=99,
        metadata={"user.id": "forged", "credential": "private-marker"},
    )
    item["raw"]["payload"]["_data"] = {"credential": "private-marker"}
    result = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    assert result["account_id"] == item["context"].account_id
    assert result["message_revision"] == 1
    assert "private-marker" not in json.dumps(result)
    assert "forged" not in json.dumps(result)


def test_rejection_precedes_content_validation_and_does_not_log(capsys):
    item = case("not-allowlisted")
    item["raw"]["payload"]["body"] = {"private-marker": "do not log"}
    with pytest.raises(AdapterError) as failure:
        normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    assert str(failure.value) == "CONVERSATION_NOT_ALLOWED"
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "ack, expected", [(0, "unknown"), (1, "sent"), (2, "delivered"), (3, "read"), (4, "read")]
)
def test_ack_semantics_do_not_claim_customer_confirmation(ack, expected):
    item = case("delivery-read")
    item["raw"]["payload"].pop("ackName")
    item["raw"]["payload"]["ack"] = ack
    event = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    assert event["payload"]["delivery_status"] == expected
    assert set(event["payload"]) == {"message_id", "delivery_status"}


def test_ack_minimum_peer_field_and_conflicting_ack_name():
    item = case("delivery-read")
    item["raw"]["payload"].pop("to")
    item["raw"]["payload"]["fromMe"] = True
    result = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    assert result["direction"] == "outgoing"
    item["raw"]["payload"]["ackName"] = "SERVER"
    with pytest.raises(AdapterError, match="^ACK_MAPPING_MISMATCH$"):
        normalize_event(item["raw"], item["context"], received_at=RECEIPT)


@pytest.mark.parametrize(
    "state, expected",
    [
        ("WORKING", "connected"),
        ("STARTING", "connecting"),
        ("SCAN_QR_CODE", "connecting"),
        ("PASSKEY_REQUIRED", "connecting"),
        ("PASSKEY_CONFIRMATION_REQUIRED", "connecting"),
        ("STOPPED", "disconnected"),
        ("FAILED", "failed"),
    ],
)
def test_session_mapping_discards_qr_material(state, expected):
    item = case("session-connected")
    item["raw"]["payload"].update(status=state, qr="private-qr", data={"key": "private-key"})
    event = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    assert event["payload"] == {"status": expected}
    assert "private" not in json.dumps(event)


def test_unknown_source_and_incoming_api_origin_require_review():
    item = case("text-created")
    for source in (None, "replay", "api"):
        context = replace(item["context"], message=replace(item["context"].message, source=source))
        with pytest.raises(AdapterError):
            normalize_event(item["raw"], context, received_at=RECEIPT)


def test_normalized_output_is_strict_and_digest_rejects_invalid_events():
    event = normalized()
    event["unexpected"] = "private-marker"
    with pytest.raises(AdapterError, match="^NORMALIZED_EVENT_INVALID$"):
        semantic_digest(event)


def test_ledger_redelivery_duplicate_and_changed_content_conflict():
    ledger = ReplayLedger()
    event = normalized()
    assert ledger.accept(event).context_version == 1
    redelivery = {**event, "received_at": "2026-10-03T00:00:00Z"}
    assert ledger.accept(redelivery).duplicate
    changed = deepcopy(event)
    changed["payload"]["text"] = "Different synthetic content"
    with pytest.raises(AdapterError, match="^IDEMPOTENCY_CONFLICT$"):
        ledger.accept(changed)
    assert ledger.accept(event).context_version == 1


def test_message_and_message_any_aliases_do_not_advance_context_twice():
    ledger = ReplayLedger()
    first = normalized()
    ledger.accept(first)
    item = case("text-created")
    item["raw"].update(id="synthetic:alias-event", event="message.any")
    alias = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    assert first["event_id"] != alias["event_id"]
    result = ledger.accept(alias)
    assert result.duplicate and result.context_version == 1


def test_edit_revoke_and_ack_are_not_collapsed_with_original_message():
    ledger = ReplayLedger()
    assert ledger.accept(normalized()).context_version == 1
    ack = ledger.accept(normalized("delivery-read"))
    assert not ack.duplicate and ack.context_version == 1
    assert ledger.accept(normalized("text-edited")).context_version == 2
    assert ledger.accept(normalized("text-revoked")).context_version == 3
    assert ledger.accept(normalized("text-revoked")).duplicate


def test_revision_gap_rejected_without_poisoning_later_recovery():
    ledger = ReplayLedger()
    ledger.accept(normalized())
    with pytest.raises(AdapterError, match="^VERSION_CONFLICT$"):
        ledger.accept(normalized("text-revoked"))
    assert ledger.accept(normalized("text-edited")).context_version == 2
    assert ledger.accept(normalized("text-revoked")).context_version == 3


def test_unknown_original_and_stale_ack_cannot_be_silently_accepted():
    ledger = ReplayLedger()
    for name in ("text-edited", "delivery-read"):
        with pytest.raises(AdapterError, match="^VERSION_CONFLICT$"):
            ledger.accept(normalized(name))
    ledger.accept(normalized())
    ledger.accept(normalized("text-edited"))
    with pytest.raises(AdapterError, match="^VERSION_CONFLICT$"):
        ledger.accept(normalized("delivery-read"))


@pytest.mark.parametrize("foreign_field", ["account_id", "conversation_id"])
def test_cross_account_or_conversation_message_id_reuse_is_rejected(foreign_field):
    ledger = ReplayLedger()
    ledger.accept(normalized())
    item = case("text-created")
    item["raw"]["id"] = "synthetic:foreign-event"
    if foreign_field == "account_id":
        context = replace(item["context"], account_id="00000000-0000-4000-8000-000000000099")
    else:
        context = replace(
            item["context"],
            message=replace(
                item["context"].message,
                conversation_id="00000000-0000-4000-8000-000000000099",
            ),
        )
    event = normalize_event(item["raw"], context, received_at=RECEIPT)
    with pytest.raises(AdapterError, match="^MESSAGE_MAPPING_MISMATCH$"):
        ledger.accept(event)


def test_state_dedup_does_not_create_message_context():
    ledger = ReplayLedger()
    result = ledger.accept(normalized("session-connected"))
    assert not result.duplicate and result.context_version is None
    assert ledger.accept(normalized("session-connected")).duplicate


def test_corpus_loader_rejects_unclassified_or_duplicate_cases(tmp_path):
    from gigmate.waha_replay import FIXTURES

    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    path = tmp_path / "cases.json"
    data["data_classification"] = "real"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AdapterError, match="^INVALID_SYNTHETIC_CORPUS$"):
        load_cases(path)
    data["data_classification"] = "synthetic"
    data["cases"].append(data["cases"][0])
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AdapterError, match="^INVALID_SYNTHETIC_CORPUS$"):
        load_cases(path)


@pytest.mark.parametrize(
    "arguments, code",
    [
        ([], 0),
        (["--case", "text-edited", "--show-events"], 0),
        (["--case", "missing"], 2),
        (["--sequence"], 0),
    ],
)
def test_cli_acceptance_and_unknown_case(arguments, code):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/replay_waha.py"), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == code, result.stderr
    if code == 0:
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert rows[-1]["failures"] == 0 and rows[-1]["mode"] == "synthetic_only"
        assert all(row["pass"] for row in rows[:-1])
        if "--show-events" not in arguments:
            assert "Synthetic appointment request" not in result.stdout


def test_cli_missing_dependencies_fail_with_install_instruction():
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/replay_waha.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "apps/backend/requirements.lock" in result.stderr
    assert "Traceback" not in result.stderr


def test_ledger_mutable_output_does_not_change_saved_revision():
    ledger = ReplayLedger()
    event = normalized()
    original = deepcopy(event)
    ledger.accept(event)
    event["payload"]["text"] = "Modified after acceptance"
    assert ledger.accept(original).duplicate
    assert ledger.accept(normalized("text-edited")).context_version == 2


def test_same_revision_different_event_id_cannot_overwrite_content():
    ledger = ReplayLedger()
    ledger.accept(normalized())
    item = case("text-created")
    item["raw"]["id"] = "synthetic:new-delivery-id"
    item["raw"]["payload"]["body"] = "Different synthetic text"
    event = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    with pytest.raises(AdapterError, match="^IDEMPOTENCY_CONFLICT$"):
        ledger.accept(event)
    assert ledger.accept(normalized("text-edited")).context_version == 2


def test_ack_cannot_change_original_direction():
    ledger = ReplayLedger()
    ledger.accept(normalized())
    item = case("delivery-read")
    item["raw"]["payload"].update(fromMe=True, to="synthetic:customer-chat")
    event = normalize_event(item["raw"], item["context"], received_at=RECEIPT)
    with pytest.raises(AdapterError, match="^MESSAGE_MAPPING_MISMATCH$"):
        ledger.accept(event)


@pytest.mark.parametrize("field", ["raw_patch", "context_patch"])
def test_invalid_corpus_patch_has_safe_error(tmp_path, field):
    from gigmate.waha_replay import FIXTURES

    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    data["cases"][0][field] = []
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AdapterError, match="^INVALID_SYNTHETIC_CORPUS$"):
        load_cases(path)
