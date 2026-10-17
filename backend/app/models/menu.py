from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.role import role_menus

if TYPE_CHECKING:
    from app.models.role import Role


class Menu(Base):
    __tablename__ = "menus"
    __table_args__ = {"comment": "菜单表"}

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("menus.id"), nullable=True, comment="父菜单ID"
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="菜单名称")
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="menu", comment="类型：dir/menu/button"
    )
    path: Mapped[str | None] = mapped_column(String(100), comment="前端路由")
    component: Mapped[str | None] = mapped_column(String(100), comment="组件标识")
    icon: Mapped[str | None] = mapped_column(String(50), comment="图标名")
    permission: Mapped[str | None] = mapped_column(String(100), comment="权限码")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="排序，越小越靠前")
    visible: Mapped[int] = mapped_column(
        Integer, default=1, comment="侧栏显示：0-否，1-是"
    )
    status: Mapped[int] = mapped_column(
        Integer, default=1, comment="状态：0-禁用，1-启用"
    )

    parent: Mapped[Menu | None] = relationship(
        remote_side="Menu.id", back_populates="children"
    )
    children: Mapped[list[Menu]] = relationship(back_populates="parent")
    roles: Mapped[list[Role]] = relationship(
        secondary=role_menus, back_populates="menus"
    )
