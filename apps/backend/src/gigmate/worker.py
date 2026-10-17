import copy
import json
import logging
import os
import threading
import time
import traceback
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError

from gigmate.approvals import draft_for_change
from gigmate.contracts import RequirementChange
from gigmate.db import (
    Account,
    ChangeRow,
    ConversationOrder,
    ConversationRow,
    Inbox,
    Job,
    MessageRow,
    Session,
    WahaChat,
    WahaConnection,
    WahaExclusion,
    WorkOrderRow,
)
from gigmate.errors import BusinessError
from gigmate.extraction import (
    ExtractionRequest,
    persist_changes_for,
    persist_proposal,
    provider,
)
from gigmate.extraction.llm import validate_provider_config
from gigmate.extraction.persistence import review_schedule_shapes
from gigmate.planning import CLOSED
from gigmate.understanding import extract
from gigmate.waha_recovery import worker_heartbeat

log = logging.getLogger("gigmate.worker")

EXTRACTION_NEEDS_REVIEW = "EXTRACTION_NEEDS_REVIEW"
OWN_SEND_ECHO = "OWN_SEND_ECHO"


def open_orders(db, conversation_id, job_id=None):
    """Orders this conversation can still change: cancelled/completed ones are history.

    When the merchant has filed this message to one order, only that order is
    offered (if it is still open).
    """
    from gigmate.db import JobAssignment

    chosen = db.get(JobAssignment, job_id) if job_id else None
    owner = db.get(ConversationRow, conversation_id)
    return [
        order.id
        for order in db.scalars(
            select(WorkOrderRow)
            .join(ConversationOrder, ConversationOrder.work_order_id == WorkOrderRow.id)
            .where(ConversationOrder.conversation_id == conversation_id)
            .order_by(WorkOrderRow.id)
        )
        if owner is not None
        and order.account_id == owner.account_id
        and order.data["status"] not in CLOSED
        and (chosen is None or order.id == chosen.work_order_id)
    ]


def run_once(factory=Session):
    began = time.monotonic()
    owner = str(uuid4())
    now = datetime.now(UTC)
    with factory.begin() as db:
        job = db.scalar(
            select(Job)
            .where(
                or_(
                    and_(Job.state == "pending", Job.available_at <= now),
                    and_(Job.state == "processing", Job.lease_until < now),
                )
            )
            .order_by(Job.available_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return False
        if job.state == "processing" and job.model_request_id:
            # A crashed/expired submitted call may have incurred cost. Never replay it.
            job.state, job.error_code = "completed", "MODEL_OUTCOME_UNKNOWN"
            job.lease_owner, job.lease_until = None, None
            complete_metrics(job, db.get(Inbox, job.event_id), began)
            return True
        if job.attempts >= 3:
            job.state, job.error_code = "failed", "RETRY_EXHAUSTED"
            job.lease_owner, job.lease_until = None, None
            complete_metrics(job, db.get(Inbox, job.event_id), began)
            return True
        if job.state == "processing":
            job.lease_recoveries += 1
        job.state, job.lease_owner, job.lease_until = (
            "processing",
            owner,
            now + timedelta(seconds=30),
        )
        job.attempts += 1
        job_id, account_id = job.id, job.account_id
    deferred = None
    try:
        with factory.begin() as db:
            account = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if (
                job.state != "processing"
                or job.lease_owner != owner
                or job.lease_until is None
                or job.lease_until.replace(tzinfo=UTC) <= datetime.now(UTC)
            ):
                return True
            inbox = db.get(Inbox, job.event_id)
            event = inbox.payload
            conversation = db.get(ConversationRow, event["conversation_id"])
            latest = db.scalar(
                select(MessageRow)
                .where(
                    MessageRow.id == event["payload"]["message_id"],
                    MessageRow.account_id == account_id,
                )
                .order_by(MessageRow.revision.desc())
            )
            connection = (
                db.get(WahaConnection, inbox.connection_id) if inbox.connection_id else None
            )
            if (
                not account.active
                or not conversation.allowlisted
                or (connection and not connection.enabled)
            ):
                job.state, job.error_code = "cancelled", "CONSENT_REVOKED"
            elif (
                (
                    inbox.context_version != conversation.context_version
                    and (
                        event["connector"] != "waha"
                        or authorization_changed_since(db, inbox, conversation)
                    )
                )
                or latest.revision != event["message_revision"]
                or latest.data["revoked"]
            ):
                job.state, job.error_code = "completed", "SOURCE_SUPERSEDED"
            elif event["source"] == "api" and (
                event["connector"] == "waha" or event["direction"] == "outgoing"
            ):
                # Ingress advances context and invalidates pending drafts; echoes
                # never trigger extraction, another question or another send.
                job.state, job.error_code = "completed", OWN_SEND_ECHO
            elif event["connector"] == "waha":
                linked = open_orders(db, conversation.id, job.id)
                job.model_request_id = uuid4().hex
                request = _extraction_request(
                    db, account, event, conversation, linked, request_id=job.model_request_id
                )
                deferred = (
                    request,
                    copy.deepcopy(event),
                    linked,
                    inbox.connection_id,
                    connection.control_version if connection else None,
                )
            else:
                linked = open_orders(db, conversation.id, job.id)
                if len(linked) != 1:
                    job.state, job.error_code = "completed", "ASSIGNMENT_NEEDS_REVIEW"
                else:
                    order = db.get(WorkOrderRow, linked[0])
                    proposal = extract(event, order.data, conversation.context_version)
                    if proposal:
                        change_id = str(uuid4())
                        change = proposal["changes"][0]
                        payload = {
                            "id": change_id,
                            "account_id": account_id,
                            "work_order_id": order.id,
                            "field": change["field"],
                            "old_value": change["old_value"],
                            "new_value": change["new_value"],
                            "status": change["field_status"],
                            "customer_confirmation": change["customer_confirmation"],
                            "proposer": "customer",
                            "sources": change["sources"],
                            "base_work_order_version": order.data["version"],
                        }
                        payload = RequirementChange.model_validate_json(
                            json.dumps(payload)
                        ).model_dump(mode="json")
                        db.add(
                            ChangeRow(
                                id=change_id,
                                account_id=account_id,
                                work_order_id=order.id,
                                conversation_id=conversation.id,
                                context_version=conversation.context_version,
                                data=payload,
                            )
                        )
                        order.data = {
                            **order.data,
                            "pending_change_ids": [
                                *order.data["pending_change_ids"],
                                change_id,
                            ],
                        }
                        db.flush()
                        draft_for_change(db, account_id, order, conversation, payload)
                    job.state, job.error_code = (
                        "completed",
                        None if proposal else "STUB_UNSUPPORTED_INPUT",
                    )
            if deferred is None:
                if job.lease_until.replace(tzinfo=UTC) <= datetime.now(UTC):
                    raise RuntimeError("LEASE_EXPIRED")
                job.lease_owner, job.lease_until = None, None
                complete_metrics(job, inbox, began)
        if deferred is not None:
            # No Session or database lock spans model/network I/O.
            request, event, linked, submitted_connection_id, submitted_control_version = deferred
            outcome = provider().propose(request)
            with factory.begin() as db:
                account = db.scalar(
                    select(Account).where(Account.id == account_id).with_for_update()
                )
                job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                if job.state != "processing" or job.lease_owner != owner:
                    return True
                inbox = db.get(Inbox, job.event_id)
                conversation = db.get(ConversationRow, request.conversation_id)
                latest = db.scalar(
                    select(MessageRow)
                    .where(
                        MessageRow.id == request.message_id,
                        MessageRow.account_id == account_id,
                        MessageRow.conversation_id == request.conversation_id,
                    )
                    .order_by(MessageRow.revision.desc())
                )
                connection = (
                    db.get(WahaConnection, inbox.connection_id) if inbox.connection_id else None
                )
                if (
                    not account.active
                    or not conversation.allowlisted
                    or (connection and not connection.enabled)
                ):
                    job.state, job.error_code = "cancelled", "CONSENT_REVOKED"
                elif job.lease_until is None or job.lease_until.replace(tzinfo=UTC) <= datetime.now(
                    UTC
                ):
                    job.state, job.error_code = "completed", "MODEL_OUTCOME_UNKNOWN"
                elif (
                    latest is None
                    or latest.revision != request.message_revision
                    or latest.data["revoked"]
                    or conversation.context_version != request.context_version
                    or inbox.context_version > request.context_version
                    or open_orders(db, conversation.id, job.id) != linked
                    or inbox.connection_id != submitted_connection_id
                    or (
                        submitted_connection_id is not None
                        and (
                            connection is None
                            or connection.control_version != submitted_control_version
                        )
                    )
                ):
                    job.state, job.error_code = "completed", "SOURCE_SUPERSEDED"
                else:
                    matched = _route_through_provider(
                        db,
                        account=account,
                        inbox=inbox,
                        event=event,
                        conversation=conversation,
                        linked=linked,
                        job=job,
                        prepared_request=request,
                        prepared_outcome=outcome,
                    )
                    job.state = "completed"
                    job.error_code = (
                        "MODEL_OUTCOME_UNKNOWN"
                        if (outcome.refused_reason or "").startswith(
                            (
                                "llm:result-unknown",
                                "llm:http-failed:timeout",
                                "llm:http-failed:transport",
                                "llm:http-failed:status-5xx",
                            )
                        )
                        else None
                        if matched
                        else EXTRACTION_NEEDS_REVIEW
                    )
                job.lease_owner, job.lease_until = None, None
                complete_metrics(job, inbox, began)
    except Exception as exc:
        # No raw message text or exception values enter logs.
        frame = traceback.extract_tb(exc.__traceback__)[-1]
        log.error(
            "job_failed job_id=%s code=PROCESSING_FAILED exception_type=%s location=%s:%s",
            job_id,
            type(exc).__name__,
            frame.name,
            frame.lineno,
        )
        with factory.begin() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.lease_owner == owner:
                job.state = (
                    "completed"
                    if job.model_request_id
                    else ("failed" if job.attempts >= 3 else "pending")
                )
                job.error_code = (
                    "MODEL_OUTCOME_UNKNOWN" if job.model_request_id else "PROCESSING_FAILED"
                )
                job.available_at = datetime.now(UTC) + timedelta(seconds=2**job.attempts)
                job.lease_owner, job.lease_until = None, None
                if job.state in {"failed", "completed"}:
                    complete_metrics(job, db.get(Inbox, job.event_id), began)
    return True


def _route_through_provider(
    db,
    *,
    account: Account,
    inbox: Inbox,
    event: dict,
    conversation: ConversationRow,
    linked: list[str],
    job: Job | None = None,
    prepared_request=None,
    prepared_outcome=None,
) -> bool:
    """Invoke the registered extraction provider and persist its evidence.

    Returns ``True`` only when the proposal was matched and at least one
    ``RequirementChange`` row was created. The WAHA branch always marks the
    request ``origin="live"``; the deterministic default provider therefore
    returns ``needs_review`` for live content even when the text equals a
    synthetic fixture. A provider that wants to mark ``matched`` for live
    content must be a separately authorized batch.

    Pre-activation gate 3 also revalidates after the call: a model call can
    take long enough for the conversation context or the work order version to
    move on, or for this worker's lease to expire. In either case the result
    describes a stale snapshot, so it is discarded instead of being promoted —
    no stale business changes are written and the original call identity stays
    available for review; paid calls are not automatically replayed.
    """
    request = prepared_request or _extraction_request(db, account, event, conversation, linked)
    outcome = review_schedule_shapes(prepared_outcome or provider().propose(request))
    target_order_id = (
        outcome.proposal.work_order_id if outcome.proposal.assignment.value == "matched" else None
    )
    base_version = outcome.proposal.base_work_order_version
    if target_order_id is not None and target_order_id not in request.candidate_work_order_ids:
        return False
    if job is not None and job.lease_until is not None:
        if job.lease_until.replace(tzinfo=UTC) <= datetime.now(UTC):
            return False
    db.refresh(conversation)
    if conversation.context_version != request.context_version:
        return False
    snapshots = request.extra.get("candidate_orders") or (
        [request.base_work_order_snapshot] if request.base_work_order_snapshot else []
    )
    for snapshot in snapshots:
        current_candidate = db.get(WorkOrderRow, snapshot["id"])
        if current_candidate is None or current_candidate.data["version"] != snapshot["version"]:
            return False
    if target_order_id is not None:
        current = db.get(WorkOrderRow, target_order_id)
        if current is None or current.data.get("version") != base_version:
            return False
    proposal_row = persist_proposal(
        db,
        account_id=account.id,
        conversation_id=conversation.id,
        event_id=inbox.id,
        proposal=outcome.proposal,
        outcome=outcome,
    )
    if outcome.proposal.assignment.value == "matched" and target_order_id is not None:
        order = db.get(WorkOrderRow, target_order_id)
        new_ids = persist_changes_for(
            db,
            proposal_row=proposal_row,
            proposal=outcome.proposal,
            account_id=account.id,
            conversation_id=conversation.id,
            work_order_id=target_order_id,
            base_work_order_version=base_version,
            work_order_field=order.data if order is not None else {},
        )
        if new_ids and order is not None:
            order.data = {
                **order.data,
                "pending_change_ids": list(order.data.get("pending_change_ids", [])) + new_ids,
            }
            db.flush()
            for change in db.scalars(select(ChangeRow).where(ChangeRow.id.in_(new_ids))):
                # Role B's draft_text is a merchant-facing summary (prompt v1), not a
                # customer reply, so the customer-facing body uses the role C template.
                draft_for_change(db, account.id, order, conversation, change.data)
            return True
    return False


def _extraction_request(db, account, event, conversation, linked, request_id=None):
    base_snapshot = None
    base_version: int | None = None
    if len(linked) == 1:
        target = db.get(WorkOrderRow, linked[0])
        if target is not None and target.account_id == account.id:
            base_snapshot = target.data
            base_version = target.data.get("version")
    candidates = [db.get(WorkOrderRow, identifier) for identifier in linked]
    latest = {}
    for row in db.scalars(
        select(MessageRow)
        .where(MessageRow.account_id == account.id, MessageRow.conversation_id == conversation.id)
        .order_by(MessageRow.revision)
    ):
        latest[row.id] = row
    history = sorted(
        (row for row in latest.values() if not row.data["revoked"] and row.data.get("text")),
        key=lambda row: (datetime.fromisoformat(row.data["occurred_at"]), row.id),
    )[-12:]
    return ExtractionRequest(
        account_id=account.id,
        conversation_id=conversation.id,
        message_id=event["payload"]["message_id"],
        message_revision=event["message_revision"],
        message_text=event.get("payload", {}).get("text"),
        context_version=conversation.context_version,
        candidate_work_order_ids=tuple(linked),
        base_work_order_version=base_version,
        base_work_order_snapshot=copy.deepcopy(base_snapshot),
        extra={
            "request_id": request_id,
            "candidate_orders": [
                {
                    "id": row.id,
                    "version": row.data["version"],
                    "summary": row.data.get("summary", ""),
                    "fields": row.data.get("fields", {}),
                }
                for row in candidates
                if row and row.account_id == account.id
            ],
            "recent_messages": [
                {
                    "id": row.id,
                    "revision": row.revision,
                    "text": row.data["text"],
                    "direction": row.data["direction"],
                    "occurred_at": row.data["occurred_at"],
                }
                for row in history
            ],
        },
        origin="live",
        # Gate 4: the connector's own sending time plus the merchant's
        # configured zone are the only date-grounding basis the provider gets.
        # Both stay ``None`` when unavailable and the provider then refuses
        # relative-date proposals instead of guessing.
        message_received_at=event.get("occurred_at"),
        workspace_timezone=_workspace_timezone(),
    )


def _workspace_timezone() -> str | None:
    """The merchant's validated IANA zone used to ground relative dates.

    Pre-activation gate 4. The zone is operator configuration, never taken
    from the model or the message. An unknown or missing value yields
    ``None``, which makes the provider refuse relative-date proposals instead
    of silently anchoring them to a guessed zone.
    """
    raw = (os.environ.get("GIGMATE_WORKSPACE_TIMEZONE") or "").strip()
    if not raw:
        return None
    try:
        ZoneInfo(raw)
    except (KeyError, ValueError, OSError):
        log.error("workspace_timezone_invalid code=CONFIG_INVALID")
        return None
    return raw


def complete_metrics(job, inbox, began):
    job.completed_at = datetime.now(UTC)
    job.processing_ms = max(0, int((time.monotonic() - began) * 1000))
    job.completion_latency_ms = max(
        0, int((job.completed_at - inbox.received_at.replace(tzinfo=UTC)).total_seconds() * 1000)
    )


def heartbeat(factory=Session):
    try:
        with factory.begin() as db:
            worker_heartbeat(db)
        return True
    except SQLAlchemyError:
        log.error("worker_heartbeat_failed code=DATABASE_UNAVAILABLE")
        return False


def poll(factory=Session):
    try:
        return run_once(factory)
    except SQLAlchemyError:
        log.error("worker_poll_failed code=DATABASE_UNAVAILABLE")
        return False


def heartbeat_loop(stop, factory=Session, interval=10):
    """Keep component health fresh during bounded parser/model I/O."""
    while not stop.is_set():
        heartbeat(factory)
        stop.wait(interval)


def audit_provider_config():
    """Audit the extraction provider configuration once at worker boot.

    Pre-activation batch 2. ``validate_provider_config`` is pure — it takes
    no database session and issues no network call — so it is safe to run
    before the poll loop starts. Three policies apply:

    * no issues → log nothing (the default closed-seam deployment);
    * any issue while ``GIGMATE_LLM_LIVE=1`` → refuse to start. A worker
      that is *about* to issue real vendor calls must not run against a
      configuration it already knows is broken, because the first failure
      would be a real request with real money behind it;
    * any issue while the live gate is off → warn only, because the
      closed skeleton seam (``_SKELETON_SEAM``) refuses every call anyway.
    """
    from gigmate.extraction.registry import build_provider

    try:
        build_provider()
    except (ValueError, RuntimeError):
        log.error("provider_config_invalid code=EXTRACTION_PROVIDER_INVALID")
        return False
    if (
        os.environ.get("GIGMATE_EXTRACTION_PROVIDER") == "reviewed_llm"
        and os.environ.get("GIGMATE_LLM_LIVE") == "1"
    ):
        from gigmate.extraction.reviewed import configured_for_live

        if not configured_for_live():
            log.error("provider_config_invalid code=REVIEWED_LLM_CONFIG_INVALID")
            return False
    issues = validate_provider_config()
    if not issues:
        return True
    live = os.environ.get("GIGMATE_LLM_LIVE") == "1"
    if live:
        log.error("provider_config_invalid code=CONFIG_INVALID live=1 issues=%s", ",".join(issues))
        return False
    log.warning(
        "provider_config_invalid code=CONFIG_INVALID live=0 issues=%s "
        "(ignored: the skeleton seam refuses every call)",
        ",".join(issues),
    )
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    if not audit_provider_config():
        # Fail fast rather than boot into a poll loop that would attempt
        # real vendor calls against a configuration already known to be
        # wrong. The seam check above is the same one the provider applies
        # at call time; running it at boot simply surfaces it earlier.
        raise SystemExit(2)
    stop = threading.Event()
    pulse = threading.Thread(
        target=heartbeat_loop, args=(stop,), name="gigmate-heartbeat", daemon=True
    )
    pulse.start()
    try:
        work_loop()
    finally:
        stop.set()
        pulse.join(timeout=2)


def work_loop():
    maintenance_at = 0
    while True:
        if time.monotonic() >= maintenance_at:
            maintain()
            maintenance_at = time.monotonic() + 3600
        if os.environ.get("WAHA_CONTROL_CONFIG"):
            from gigmate.waha_controls import run_once as control_once

            try:
                control_once()
                from gigmate.waha_sync import run_once as sync_once

                sync_once()
                from gigmate.waha_media import run_once as media_once

                media_once()
                from gigmate.waha_send import run_once as send_once

                send_once()
            except BusinessError as error:
                log.error("media_poll_failed code=%s", error.code)
            except SQLAlchemyError:
                log.error("control_poll_failed code=DATABASE_UNAVAILABLE")
        if not poll():
            time.sleep(0.5)


def maintain(factory=Session):
    from gigmate.waha_ingress import purge_expired

    try:
        from sqlalchemy import delete

        from gigmate.db import WahaCandidate, WahaControl

        with factory.begin() as db:
            db.execute(delete(WahaCandidate).where(WahaCandidate.expires_at <= datetime.now(UTC)))
            db.execute(
                delete(WahaControl).where(
                    WahaControl.active_key.is_(None),
                    WahaControl.created_at < datetime.now(UTC) - timedelta(days=30),
                )
            )
        with factory() as db:
            identifiers = list(db.scalars(select(WahaConnection.id)))
        for identifier in identifiers:
            with factory.begin() as db:
                purge_expired(db, identifier)
        from gigmate.approvals import follow_up_unanswered

        with factory.begin() as db:
            follow_up_unanswered(db)
        from gigmate.waha_media import purge as purge_media

        purge_media(factory)
        if os.environ.get("WAHA_SEND_ENABLED") == "true":
            from gigmate.waha_send import purge as purge_sends

            purge_sends(factory)
        return True
    except SQLAlchemyError:
        log.error("worker_maintenance_failed code=DATABASE_UNAVAILABLE")
        return False
    except (BusinessError, OSError):
        log.error("worker_maintenance_failed code=MEDIA_STORAGE_UNAVAILABLE")
        return False


def authorization_changed_since(db, inbox, conversation):
    """Only message arrivals may be re-contextualised automatically before a call.

    A denial/pause interval since acceptance requires an explicit reanalysis.
    No already submitted call is retried through this path.
    """
    if inbox.connection_id is None:
        return False
    chat = db.scalar(
        select(WahaChat).where(
            WahaChat.conversation_id == conversation.id,
            WahaChat.connection_id == inbox.connection_id,
        )
    )
    return (
        db.scalar(
            select(WahaExclusion.id)
            .where(
                WahaExclusion.connection_id == inbox.connection_id,
                or_(
                    WahaExclusion.chat_id.is_(None),
                    WahaExclusion.chat_id == (chat.id if chat else None),
                ),
                WahaExclusion.started_at >= inbox.received_at,
            )
            .limit(1)
        )
        is not None
    )


if __name__ == "__main__":
    main()
