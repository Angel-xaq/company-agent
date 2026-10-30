from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import RESERVATION_CONFIRMED
from app.database import Base

if TYPE_CHECKING:
    from app.models.meeting_room import MeetingRoom
    from app.models.user import User


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("ix_res_room_time", "room_id", "start_time", "end_time"),
        Index("ix_res_user_time", "user_id", "start_time"),
        {"comment": "会议室预约表"},
    )

    room_id: Mapped[int] = mapped_column(
        ForeignKey("meeting_rooms.id"), nullable=False, comment="会议室ID"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, comment="预约人ID"
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False, comment="会议主题")
    purpose: Mapped[str | None] = mapped_column(String(255), comment="用途说明")
    attendees: Mapped[int | None] = mapped_column(Integer, comment="参会人数")
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="开始时间"
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="结束时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RESERVATION_CONFIRMED,
        comment="状态：confirmed/cancelled",
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="取消时间"
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(255), comment="取消原因")

    room: Mapped[MeetingRoom] = relationship(back_populates="reservations")
    user: Mapped[User] = relationship()
