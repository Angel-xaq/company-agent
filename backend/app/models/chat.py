from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    pass


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_session_user", "user_id", "update_time"),
        {"comment": "对话会话表"},
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, comment="用户ID"
    )
    title: Mapped[str] = mapped_column(
        String(100), nullable=False, default="新对话", comment="会话标题"
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_message_session", "session_id", "id"),
        {"comment": "对话消息表"},
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="会话ID",
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="角色：user/assistant"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="消息内容"
    )
    citations: Mapped[list | None] = mapped_column(
        JSON, comment="知识库引用"
    )
    tool_calls: Mapped[list | None] = mapped_column(
        JSON, comment="工具调用记录"
    )
    usage: Mapped[dict | None] = mapped_column(JSON, comment="token 用量")

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class ChatPendingAction(Base):
    __tablename__ = "chat_pending_actions"
    __table_args__ = (
        Index("ix_chat_action_token", "token"),
        {"comment": "智能助手待确认操作"},
    )

    token: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="确认令牌"
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        comment="会话ID",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, comment="用户ID"
    )
    tool_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="工具名称"
    )
    params: Mapped[dict] = mapped_column(JSON, nullable=False, comment="工具参数")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", comment="pending/confirmed/rejected/expired"
    )
    expire_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="过期时间"
    )
