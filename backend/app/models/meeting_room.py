from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.reservation import Reservation


class MeetingRoom(Base):
    __tablename__ = "meeting_rooms"
    __table_args__ = {"comment": "会议室表"}

    name: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="会议室名称"
    )
    location: Mapped[str | None] = mapped_column(String(100), comment="位置")
    capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="容纳人数"
    )
    equipment: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, comment="设备列表"
    )
    description: Mapped[str | None] = mapped_column(String(255), comment="描述")
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="状态：0-停用，1-启用"
    )
    sort: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="排序，越小越靠前"
    )

    reservations: Mapped[list[Reservation]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )
