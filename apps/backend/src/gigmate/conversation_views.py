"""Owned display metadata and explicit per-order message provenance."""

from sqlalchemy import select

from gigmate.db import (
    ActionRow,
    ChangeRow,
    Inbox,
    Job,
    JobAssignment,
    ProposalDecision,
    WahaCandidate,
    WahaChat,
    WahaConnection,
)


def conversation_label(db, account_id, conversation_id):
    chat = db.scalar(
        select(WahaChat)
        .join(WahaConnection)
        .where(WahaChat.conversation_id == conversation_id, WahaConnection.account_id == account_id)
    )
    if chat is None:
        return "客户会话"
    peer = chat.provider_chat_id
    identifier, _, domain = peer.partition("@")
    if domain in {"c.us", "s.whatsapp.net"} and identifier.isdigit():
        return "+" + identifier
    if chat.display_name:
        return chat.display_name
    candidate = db.scalar(
        select(WahaCandidate)
        .where(
            WahaCandidate.connection_id == chat.connection_id,
            WahaCandidate.provider_chat_id == peer,
        )
        .order_by(WahaCandidate.expires_at.desc())
    )
    if candidate and candidate.label:
        return candidate.label
    return "未命名群聊" if domain == "g.us" else "客户会话（未提供号码）"


def order_message_ids(db, account_id, order):
    """Only messages explicitly cited or filed to this order, never the whole chat."""
    refs = list(order.data.get("source_messages") or [])
    for field in order.data["fields"].values():
        refs.extend(field.get("sources") or [])
    for item in order.data.get("requirements") or []:
        refs.extend(item.get("sources") or [])
    for row in db.scalars(
        select(ChangeRow).where(
            ChangeRow.account_id == account_id, ChangeRow.work_order_id == order.id
        )
    ):
        refs.extend(row.data.get("sources") or [])
    for row in db.scalars(
        select(ActionRow).where(
            ActionRow.account_id == account_id, ActionRow.work_order_id == order.id
        )
    ):
        refs.extend(row.data.get("sources") or [])
    for inbox in db.scalars(
        select(Inbox)
        .join(Job, Job.event_id == Inbox.id)
        .join(JobAssignment, JobAssignment.job_id == Job.id)
        .where(JobAssignment.account_id == account_id, JobAssignment.work_order_id == order.id)
    ):
        refs.append({"message_id": inbox.payload["payload"]["message_id"]})
    for inbox in db.scalars(
        select(Inbox)
        .join(ProposalDecision, ProposalDecision.event_id == Inbox.id)
        .where(
            ProposalDecision.account_id == account_id, ProposalDecision.work_order_id == order.id
        )
    ):
        refs.append({"message_id": inbox.payload["payload"]["message_id"]})
    return {ref["message_id"] for ref in refs}


def change_source_job(db, account_id, change):
    refs = {ref["message_id"] for ref in change.data.get("sources") or []}
    for job, inbox in db.execute(
        select(Job, Inbox)
        .join(Inbox, Job.event_id == Inbox.id)
        .where(Job.account_id == account_id, Inbox.account_id == account_id)
        .order_by(Inbox.received_at.desc())
    ):
        if (
            inbox.payload.get("conversation_id") == change.conversation_id
            and inbox.payload.get("payload", {}).get("message_id") in refs
            and job.state == "completed"
        ):
            return job.id
    return None
