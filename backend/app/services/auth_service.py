import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.config import settings
from app.core.constants import DEFAULT_ROLE_CODE
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from app.services.user_service import user_to_response
from app.utils.jwt import create_access_token
from app.utils.password import hash_password, verify_password


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _create_refresh_token(
    db: Session, user_id: int, *, commit: bool = True
) -> str:
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_EXPIRE_DAYS
    )
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=_hash_refresh_token(raw_token),
            expires_at=expires_at,
        )
    )
    if commit:
        db.commit()
    return raw_token


def login(db: Session, data: LoginRequest) -> tuple[LoginResponse, str]:
    """校验账号密码，签发 15 分钟 Access Token 和 7 天 Refresh Token。"""
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.menus))
        .filter(User.username == data.username)
        .first()
    )

    if not user or not verify_password(data.password, user.password):
        raise BusinessException(message="账号或密码错误")

    if user.status != 1:
        raise BusinessException(message="账号被禁用")

    access_token = create_access_token(user.id)
    refresh_token = _create_refresh_token(db, user.id)
    return (
        LoginResponse(token=access_token, user=user_to_response(user)),
        refresh_token,
    )


def refresh_access_token(
    db: Session, raw_token: str
) -> tuple[LoginResponse, str]:
    """校验 Refresh Token，轮换后返回新的 Access Token 与 Refresh Token。"""
    now = datetime.now(timezone.utc)
    token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == _hash_refresh_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if token is None or token.expires_at <= now:
        raise BusinessException(message="登录已失效，请重新登录", code=401)

    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.menus))
        .filter(User.id == token.user_id)
        .first()
    )
    if user is None or user.status != 1:
        token.revoked_at = now
        db.commit()
        raise BusinessException(message="账号不可用，请重新登录", code=401)

    token.revoked_at = now
    db.flush()
    new_refresh_token = _create_refresh_token(db, user.id, commit=False)
    db.commit()

    return (
        LoginResponse(
            token=create_access_token(user.id),
            user=user_to_response(user),
        ),
        new_refresh_token,
    )


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    """退出登录时吊销当前 Refresh Token。"""
    token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == _hash_refresh_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .first()
    )
    if token is not None:
        token.revoked_at = datetime.now(timezone.utc)
        db.commit()


def register(db: Session, data: RegisterRequest) -> None:
    """注册用户并绑定默认员工角色"""
    exists = db.query(User).filter(User.username == data.username).first()
    if exists:
        raise BusinessException(message="账号已存在")

    default_role = (
        db.query(Role).filter(Role.code == DEFAULT_ROLE_CODE).first()
    )
    if not default_role:
        raise BusinessException(message="默认员工角色不存在，请先初始化 RBAC")

    user = User(
        username=data.username,
        password=hash_password(data.password),
        name=data.name or data.username,
        status=1,
    )
    user.roles = [default_role]
    db.add(user)
    db.commit()
    db.refresh(user)
