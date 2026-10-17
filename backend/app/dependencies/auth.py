from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.utils.jwt import decode_access_token
from app.common.exceptions import BusinessException

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def has_role(user: User, code: str) -> bool:
    """用户是否拥有指定角色码（并集）。"""
    if not user or not user.roles:
        return False
    return any(r.code == code and r.status == 1 for r in user.roles)


def has_permission(user: User, code: str) -> bool:
    """用户是否拥有指定权限码（多角色菜单并集）。"""
    if not user or not user.roles or not code:
        return False
    for role in user.roles:
        if role.status != 1:
            continue
        for menu in role.menus or []:
            if menu.status == 1 and menu.permission == code:
                return True
    return False


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """JWT token 鉴权，并预加载 roles / menus。"""
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录"
        )
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证"
        )
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.menus))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在"
        )
    if user.status != 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户被禁用"
        )
    return user


def require_roles(*codes: str):
    """Depends 工厂：当前用户须具备 codes 中任一角色。"""

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        """实际执行角色校验的 Depends 回调。"""
        if not any(has_role(current_user, c) for c in codes):
            raise BusinessException(message="无权限访问", code=403)
        return current_user

    return _checker


def require_permissions(*codes: str):
    """Depends 工厂：当前用户须具备 codes 中任一权限码。"""

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        """实际执行权限码校验的 Depends 回调。"""
        if not any(has_permission(current_user, c) for c in codes):
            raise BusinessException(message="无权限访问", code=403)
        return current_user

    return _checker


# 兼容旧命名：管理员鉴权
get_current_admin = require_roles("admin")
