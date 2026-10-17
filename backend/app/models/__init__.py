"""统一注册所有 ORM 模型，确保 create_all 能建出全部表"""

from app.models.role import Role, role_menus, user_roles
from app.models.user import User
from app.models.menu import Menu

__all__ = ["Role", "User", "Menu", "user_roles", "role_menus"]
