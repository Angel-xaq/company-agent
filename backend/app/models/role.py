from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.menu import Menu
    from app.models.user import User


# 用户-角色关联表（联合主键，无自增 id）
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True, comment="用户ID"),
    Column("role_id", ForeignKey("roles.id"), primary_key=True, comment="角色ID"),
    comment="用户角色关联表",
)

# 角色-菜单关联表（联合主键，无自增 id）
role_menus = Table(
    "role_menus",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id"), primary_key=True, comment="角色ID"),
    Column("menu_id", ForeignKey("menus.id"), primary_key=True, comment="菜单ID"),
    comment="角色菜单关联表",
)


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"comment": "角色表"}

    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="角色编码"
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="角色名称")
    status: Mapped[int] = mapped_column(
        Integer, default=1, comment="状态：0-禁用，1-启用"
    )
    remark: Mapped[str | None] = mapped_column(String(200), comment="备注")

    users: Mapped[list[User]] = relationship(
        secondary=user_roles, back_populates="roles"
    )
    menus: Mapped[list[Menu]] = relationship(
        secondary=role_menus, back_populates="roles"
    )
