from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from app.services.user_service import user_to_response
from app.utils.jwt import create_access_token
from app.utils.password import hash_password, verify_password


def login(db: Session, data: LoginRequest) -> LoginResponse:
    """校验账号密码并签发 JWT（禁用账号拒绝）"""
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

    token = create_access_token(user.id)
    return LoginResponse(
        token=token,
        user=user_to_response(user),
    )


def register(db: Session, data: RegisterRequest) -> None:
    """注册用户并绑定默认 student 角色"""
    exists = db.query(User).filter(User.username == data.username).first()
    if exists:
        raise BusinessException(message="账号已存在")

    student = db.query(Role).filter(Role.code == "student").first()
    if not student:
        raise BusinessException(message="默认学生角色不存在，请先初始化 RBAC")

    user = User(
        username=data.username,
        password=hash_password(data.password),
        name=data.name or data.username,
        status=1,
    )
    user.roles = [student]
    db.add(user)
    db.commit()
    db.refresh(user)
