"""
SQLAlchemy ORM models for EVA Agent Backend.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user", nullable=False)  # "user" | "admin"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    tasks: Mapped[list[Task]] = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    connector_accounts: Mapped[list[ConnectorAccount]] = relationship(
        "ConnectorAccount", back_populates="user", cascade="all, delete-orphan"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"task-{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True, nullable=False)
    request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running", nullable=False)
    policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="tasks")
    messages: Mapped[list[Message]] = relationship("Message", back_populates="task", cascade="all, delete-orphan")
    events: Mapped[list[TaskEvent]] = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")
    tool_executions: Mapped[list[ToolExecution]] = relationship(
        "ToolExecution", back_populates="task", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # "user" | "assistant" | "system" | "tool"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    task: Mapped[Task] = relationship("Task", back_populates="messages")


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("task_id", "seq", name="uq_task_events_task_seq"),
        Index("idx_task_events_seq", "task_id", "seq"),
    )

    task: Mapped[Task] = relationship("Task", back_populates="events")


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), index=True, nullable=False)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    args_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    raw_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)  # pass, sanitized, quarantined, held
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    task: Mapped[Task] = relationship("Task", back_populates="tool_executions")


class ConnectorAccount(Base):
    __tablename__ = "connector_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="gmail", nullable=False)
    account_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(String(512), nullable=False)
    expires_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # "connected" | "reconnect_needed"
    status: Mapped[str] = mapped_column(String(32), default="connected", server_default="connected", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="connector_accounts")


class ApprovalIndex(Base):
    __tablename__ = "approvals_index"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # approval_id from guard
    task_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    exact_action_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, approved, denied, expired
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
