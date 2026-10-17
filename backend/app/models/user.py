from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.role import user_roles

if TYPE_CHECKING:
    from app.models.role import Role


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "用户信息表"}

    username: Mapped[str] = mapped_column(
        String(50), comment="账号", nullable=False, unique=True
    )
    password: Mapped[str] = mapped_column(String(255), comment="密码", nullable=False)
    name: Mapped[str] = mapped_column(String(50), comment="名称", nullable=False)
    email: Mapped[str | None] = mapped_column(String(50), comment="邮箱")
    phone: Mapped[str | None] = mapped_column(String(50), comment="手机号")
    avatar: Mapped[str | None] = mapped_column(String(50), comment="头像")
    status: Mapped[int] = mapped_column(default=1, comment="状态：0-禁用，1-正常")

    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles, back_populates="users"
    )
