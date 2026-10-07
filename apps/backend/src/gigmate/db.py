from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from gigmate.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConversationRow(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    context_version: Mapped[int] = mapped_column(Integer)
    allowlisted: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkOrderRow(Base):
    __tablename__ = "work_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class ConversationOrder(Base):
    __tablename__ = "conversation_orders"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), primary_key=True)


class Inbox(Base):
    __tablename__ = "inbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    context_version: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    connection_id: Mapped[str | None] = mapped_column(ForeignKey("waha_connections.id"), index=True)


class WahaConnection(Base):
    __tablename__ = "waha_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    instance_id: Mapped[str] = mapped_column(String(128))
    session_id: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    control_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    state: Mapped[str] = mapped_column(String(24), default="unknown")
    state_timestamp: Mapped[int | None] = mapped_column(BigInteger)
    state_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    stale_events: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("instance_id", "session_id", name="uq_waha_session"),)


class WahaChat(Base):
    __tablename__ = "waha_chats"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("waha_connections.id"), index=True)
    provider_chat_id: Mapped[str] = mapped_column(String(256))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), unique=True)
    __table_args__ = (UniqueConstraint("connection_id", "provider_chat_id", name="uq_waha_chat"),)


class WahaMessage(Base):
    __tablename__ = "waha_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_id: Mapped[str] = mapped_column(ForeignKey("waha_chats.id"), index=True)
    provider_message_id: Mapped[str] = mapped_column(String(256))
    stanza_id: Mapped[str | None] = mapped_column(String(256))
    message_id: Mapped[str] = mapped_column(String(36), unique=True)
    revision: Mapped[int] = mapped_column(Integer)
    occurred_timestamp: Mapped[int] = mapped_column(BigInteger)
    delivery_rank: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("chat_id", "provider_message_id", name="uq_waha_message"),
        Index("ix_waha_message_stanza", "chat_id", "stanza_id"),
    )


class WahaControl(Base):
    __tablename__ = "waha_controls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("waha_connections.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    request_key: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32))
    active_key: Mapped[str | None] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("connection_id", "request_key", name="uq_waha_control_key"),)


class WahaCandidate(Base):
    __tablename__ = "waha_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("waha_connections.id"), index=True)
    provider_chat_id: Mapped[str] = mapped_column(String(256))
    label: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MessageRow(Base):
    __tablename__ = "message_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    provider_message_id: Mapped[str] = mapped_column(String(256))
    data: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "conversation_id",
            "provider_message_id",
            "revision",
            name="uq_message_identity",
        ),
    )


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"
    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WahaOperation(Base):
    __tablename__ = "waha_operations"
    connection_id: Mapped[str] = mapped_column(ForeignKey("waha_connections.id"), primary_key=True)
    monitor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    api_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    api_ok: Mapped[bool | None] = mapped_column(Boolean)
    provider_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_ok: Mapped[bool | None] = mapped_column(Boolean)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    last_rejection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class WahaRecoveryIssue(Base):
    __tablename__ = "waha_recovery_issues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("waha_connections.id"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    active_key: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(32))
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("connection_id", "active_key", name="uq_waha_active_issue"),)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("inbox.id"), unique=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    state: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(36))
    error_code: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    completion_latency_ms: Mapped[int | None] = mapped_column(BigInteger)
    lease_recoveries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ChangeRow(Base):
    __tablename__ = "requirement_changes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    context_version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)


class CalendarRow(Base):
    __tablename__ = "calendar_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), unique=True)
    data: Mapped[dict] = mapped_column(JSON)


class TaskRow(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"))
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict] = mapped_column(JSON)


class AuditRow(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    data: Mapped[dict] = mapped_column(JSON)


class CommandResult(Base):
    __tablename__ = "command_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    scope: Mapped[str] = mapped_column(String(256))
    key: Mapped[str] = mapped_column(String(128))
    digest: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("account_id", "scope", "key", name="uq_command_key"),)


def make_engine(url=DATABASE_URL):
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False}
        if url.startswith("sqlite")
        else {"connect_timeout": 5},
        pool_timeout=5,
    )


engine = make_engine()
Session = sessionmaker(engine, expire_on_commit=False)
