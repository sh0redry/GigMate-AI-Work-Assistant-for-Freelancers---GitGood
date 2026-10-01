import json
import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError

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
    WorkOrderRow,
)
from gigmate.understanding import extract

log = logging.getLogger("gigmate.worker")


def run_once(factory=Session):
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
        job.state, job.lease_owner, job.lease_until = (
            "processing",
            owner,
            now + timedelta(seconds=30),
        )
        job.attempts += 1
        job_id, account_id = job.id, job.account_id
    try:
        with factory.begin() as db:
            account = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.state != "processing" or job.lease_owner != owner:
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
            if not account.active or not conversation.allowlisted:
                job.state, job.error_code = "cancelled", "CONSENT_REVOKED"
            elif (
                inbox.context_version != conversation.context_version
                or latest.revision != event["message_revision"]
                or latest.data["revoked"]
            ):
                job.state, job.error_code = "completed", "SOURCE_SUPERSEDED"
            else:
                linked = list(
                    db.scalars(
                        select(ConversationOrder.work_order_id).where(
                            ConversationOrder.conversation_id == conversation.id
                        )
                    )
                )
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
                        # Only proposals at the current accepted context remain actionable.
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
                            "pending_change_ids": [*order.data["pending_change_ids"], change_id],
                        }
                    job.state, job.error_code = (
                        "completed",
                        None if proposal else "STUB_UNSUPPORTED_INPUT",
                    )
            job.lease_owner, job.lease_until = None, None
    except Exception:
        # No raw message text or exception values enter logs.
        log.error("job_failed job_id=%s code=PROCESSING_FAILED", job_id)
        with factory.begin() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.lease_owner == owner:
                job.state = "failed" if job.attempts >= 3 else "pending"
                job.error_code = "PROCESSING_FAILED"
                job.available_at = datetime.now(UTC) + timedelta(seconds=2**job.attempts)
                job.lease_owner, job.lease_until = None, None
    return True


def poll(factory=Session):
    try:
        return run_once(factory)
    except SQLAlchemyError:
        log.error("worker_poll_failed code=DATABASE_UNAVAILABLE")
        return False


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        if not poll():
            time.sleep(0.5)


if __name__ == "__main__":
    main()
