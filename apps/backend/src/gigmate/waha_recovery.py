"""Operational metadata only: health samples, counters and manual gap review.

Never accepts provider payloads, chat identifiers, credentials or free-form notes.
Recovery of a component does not prove recovery of missing message revisions.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import case, func, select, text

from gigmate.contracts import RecoveryIssue
from gigmate.db import (
    Account,
    Inbox,
    Job,
    ServiceHeartbeat,
    WahaConnection,
    WahaOperation,
    WahaRecoveryIssue,
)
from gigmate.errors import BusinessError

FRESH_SECONDS = 120
WORKER_FRESH_SECONDS = 30
REVIEW_CODES = {
    "SOURCE_MESSAGE_UNRESOLVED",
    "SOURCE_MESSAGE_AMBIGUOUS",
    "SOURCE_MAPPING_MISMATCH",
    "SOURCE_ORDER_NEEDS_RECONCILIATION",
    "SOURCE_REVOKED",
    "IDEMPOTENCY_CONFLICT",
    "STATE_ORDER_NEEDS_RECONCILIATION",
    "EVENT_RETENTION_EXPIRED",
    "ACK_ERROR_NEEDS_RECONCILIATION",
}
SAFE_REJECTIONS = REVIEW_CODES | {
    "CONSENT_REVOKED",
    "SESSION_MAPPING_MISMATCH",
    "CONVERSATION_NOT_ALLOWED",
    "INVALID_PROVIDER_SHAPE",
    "INVALID_TIMESTAMP",
    "TEXT_LIMIT_EXCEEDED",
    "UNSUPPORTED_MEDIA",
    "UNSUPPORTED_ACK",
    "ACK_MAPPING_MISMATCH",
    "INVALID_WEBHOOK_JSON",
    "EVENT_SCHEMA_INVALID",
    "DATABASE_UNAVAILABLE",
}


def stamp(value):
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value else None


def age(value, now):
    return max(0, (now - value.replace(tzinfo=UTC)).total_seconds()) if value else None


def health(observed, healthy, now, *, window=FRESH_SECONDS):
    if observed is None:
        state = "unknown"
    elif age(observed, now) > window:
        state = "stale"
    else:
        state = "healthy" if healthy else "unavailable"
    return {"state": state, "observed_at": stamp(observed)}


def worker_heartbeat(db, *, now=None):
    now = now or datetime.now(UTC)
    # Atomic upsert also handles multiple worker processes starting together.
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    statement = insert(ServiceHeartbeat).values(service="worker", observed_at=now)
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[ServiceHeartbeat.service],
            set_={"observed_at": now},
            where=ServiceHeartbeat.observed_at < now,
        )
    )


def owned_operation(db, binding):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SET LOCAL lock_timeout = '3s'"))
        db.execute(text("SET LOCAL statement_timeout = '5s'"))
    account = db.scalar(select(Account).where(Account.id == binding.account_id).with_for_update())
    connection = db.scalar(
        select(WahaConnection)
        .where(
            WahaConnection.id == binding.connection_id,
            WahaConnection.account_id == binding.account_id,
        )
        .with_for_update()
    )
    if (
        not account
        or not account.active
        or not connection
        or (connection.instance_id, connection.session_id)
        != (binding.instance_id, binding.session_id)
    ):
        raise BusinessError(403, "SESSION_MAPPING_MISMATCH", "Trusted connector ownership required")
    row = db.get(WahaOperation, connection.id)
    if row is None:
        row = WahaOperation(connection_id=connection.id, rejected=0)
        db.add(row)
        db.flush()
    return connection, row


def issue(db, connection_id, code, now, *, start=None, recovered=False):
    existing = db.scalar(
        select(WahaRecoveryIssue).where(
            WahaRecoveryIssue.connection_id == connection_id,
            WahaRecoveryIssue.active_key == code,
        )
    )
    if existing is None:
        existing = WahaRecoveryIssue(
            id=str(uuid4()),
            connection_id=connection_id,
            code=code,
            active_key=code,
            started_at=start or now,
            last_seen_at=now,
            occurrences=1,
        )
        db.add(existing)
    else:
        existing.last_seen_at = now
        existing.occurrences += 1
    if recovered:
        existing.recovered_at = now
    db.flush()
    return existing


def recovered_issue(db, connection_id, code, now):
    existing = db.scalar(
        select(WahaRecoveryIssue).where(
            WahaRecoveryIssue.connection_id == connection_id,
            WahaRecoveryIssue.active_key == code,
        )
    )
    if existing:
        existing.recovered_at, existing.active_key = now, None


def record_rejection(db, binding, code, *, now=None):
    now = now or datetime.now(UTC)
    connection, row = owned_operation(db, binding)
    code = code if code in SAFE_REJECTIONS else "INVALID_PROVIDER_SHAPE"
    row.rejected += 1
    row.last_rejection_at, row.last_error_code = now, code
    if connection.enabled and code in REVIEW_CODES | {"DATABASE_UNAVAILABLE"}:
        issue(db, connection.id, code, now, recovered=True)


def record_database_gap(db, binding, started_at, *, now=None):
    """Persist monitor outage evidence once the database can accept writes again."""
    now = now or datetime.now(UTC)
    connection, _ = owned_operation(db, binding)
    if connection.enabled:
        gap = issue(
            db, connection.id, "DATABASE_UNAVAILABLE", now, start=started_at, recovered=True
        )
        gap.active_key = None


def observe_pipeline(db, binding, *, api_ok, provider_ok, now=None):
    now = now or datetime.now(UTC)
    connection, row = owned_operation(db, binding)
    if row.monitor_at and now <= row.monitor_at.replace(tzinfo=UTC):
        return  # An older concurrent probe must not overwrite a newer sample.
    if connection.enabled:
        if row.monitor_at and age(row.monitor_at, now) > FRESH_SECONDS:
            gap = issue(db, connection.id, "MONITOR_GAP", now, start=row.monitor_at, recovered=True)
            gap.active_key = None
        for code, ok, prior in (
            ("INGRESS_UNAVAILABLE", api_ok, row.api_at),
            ("PROVIDER_UNAVAILABLE", provider_ok, row.provider_at),
        ):
            if ok:
                recovered_issue(db, connection.id, code, now)
            else:
                issue(db, connection.id, code, now, start=prior)
        heartbeat = db.get(ServiceHeartbeat, "worker")
        worker_at = heartbeat.observed_at if heartbeat else None
        if worker_at and age(worker_at, now) <= WORKER_FRESH_SECONDS:
            recovered_issue(db, connection.id, "WORKER_GAP", now)
        else:
            issue(db, connection.id, "WORKER_GAP", now, start=worker_at)
    row.monitor_at = row.api_at = row.provider_at = now
    row.api_ok, row.provider_ok = api_ok, provider_ok
    db.flush()


def acknowledge_issue(db, binding, issue_id, resolution, *, now=None):
    owned_operation(db, binding)
    if resolution not in {"reviewed_no_import", "needs_followup"}:
        raise BusinessError(422, "INVALID_REVIEW_RESOLUTION", "Choose an explicit review outcome")
    row = db.scalar(
        select(WahaRecoveryIssue)
        .where(
            WahaRecoveryIssue.id == issue_id,
            WahaRecoveryIssue.connection_id == binding.connection_id,
        )
        .with_for_update()
    )
    if not row:
        raise BusinessError(404, "NOT_FOUND", "Recovery issue not found")
    if row.recovered_at is None:
        raise BusinessError(
            409, "COMPONENT_STILL_UNAVAILABLE", "Restore the component before review"
        )
    # needs_followup keeps the review flag visible; it is not evidence of recovery/import.
    if row.acknowledged_at:
        if row.resolution != resolution:
            raise BusinessError(409, "REVIEW_ALREADY_RECORDED", "Review outcome is immutable")
    else:
        row.resolution = resolution
        if resolution == "reviewed_no_import":
            row.acknowledged_at = now or datetime.now(UTC)
            row.active_key = None
    db.flush()
    return issue_view(row)


def issue_view(row):
    return RecoveryIssue(
        id=row.id,
        connection_id=row.connection_id,
        code=row.code,
        started_at=stamp(row.started_at),
        last_seen_at=stamp(row.last_seen_at),
        recovered_at=stamp(row.recovered_at),
        acknowledged_at=stamp(row.acknowledged_at),
        resolution=row.resolution,
        occurrences=row.occurrences,
    ).model_dump(mode="json")


def operational_view(db, connection, *, now):
    row = db.get(WahaOperation, connection.id)
    heartbeat = db.get(ServiceHeartbeat, "worker")
    api = health(row.api_at if row else None, row.api_ok if row else False, now)
    provider = health(row.provider_at if row else None, row.provider_ok if row else False, now)
    worker = health(
        heartbeat.observed_at if heartbeat else None, True, now, window=WORKER_FRESH_SECONDS
    )
    monitor = health(row.monitor_at if row else None, True, now)
    unresolved = db.scalar(
        select(func.count())
        .select_from(WahaRecoveryIssue)
        .where(
            WahaRecoveryIssue.connection_id == connection.id,
            (WahaRecoveryIssue.acknowledged_at.is_(None))
            | (WahaRecoveryIssue.resolution == "needs_followup"),
        )
    )
    query = (
        select(
            func.sum(case((Job.attempts > 1, Job.attempts - 1), else_=0)),
            func.sum(Job.lease_recoveries),
            func.count(Job.processing_ms),
            func.avg(Job.processing_ms),
            func.max(Job.processing_ms),
            func.avg(Job.completion_latency_ms),
        )
        .join(Inbox, Inbox.id == Job.event_id)
        .where(Inbox.connection_id == connection.id)
    )
    retries, recovered, timed, average, maximum, latency = db.execute(query).one()
    oldest = db.scalar(
        select(func.min(Inbox.received_at))
        .join(Job)
        .where(
            Inbox.connection_id == connection.id,
            Job.state.in_(["pending", "processing"]),
        )
    )
    expired = db.scalar(
        select(func.count())
        .select_from(Job)
        .join(Inbox)
        .where(
            Inbox.connection_id == connection.id,
            Job.state == "processing",
            Job.lease_until <= now,
        )
    )
    return {
        "api_health": api,
        "provider_health": provider,
        "worker_health": worker,
        "monitor_health": monitor,
        "pipeline_ready": connection.enabled
        and connection.state == "connected"
        and all(h["state"] == "healthy" for h in (api, provider, worker, monitor))
        and connection.state_received_at is not None
        and age(connection.state_received_at, now) <= FRESH_SECONDS,
        "review_required": bool(unresolved),
        "unresolved_issues": unresolved,
        "metrics": {
            "rejected": row.rejected if row else 0,
            "retries": retries or 0,
            "lease_recoveries": recovered or 0,
            "expired_leases": expired,
            "oldest_pending_seconds": age(oldest, now),
            "timed_jobs": timed,
            "average_processing_ms": float(average) if average is not None else None,
            "maximum_processing_ms": maximum,
            "average_completion_latency_ms": float(latency) if latency is not None else None,
            "last_error_code": row.last_error_code if row else None,
            "last_rejection_at": stamp(row.last_rejection_at) if row else None,
        },
    }
