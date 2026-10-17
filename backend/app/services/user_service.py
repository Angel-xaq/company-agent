from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.models.role import Role
from app.models.user import User
from app.schemas.role import RoleBrief
from app.schemas.user import (
    PasswordUpdateRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.utils.password import hash_password, verify_password


def _compat_role(roles: list[Role]) -> str | None:
    """兼容旧前端单 role 字段：有 admin 则返回 admin，否则取首个启用角色码。"""
    if not roles:
        return None
    codes = [r.code for r in roles if r.status == 1]
    if "admin" in codes:
        return "admin"
    return codes[0] if codes else None


def _permissions_from_roles(roles: list[Role]) -> list[str]:
    """从多角色启用菜单中汇总权限码并集。"""
    perms: set[str] = set()
    for role in roles or []:
        if role.status != 1:
            continue
        for menu in role.menus or []:
            if menu.status == 1 and menu.permission:
                perms.add(menu.permission)
    return sorted(perms)


def user_to_response(user: User) -> UserResponse:
    """将 User ORM 转为含角色/权限的响应 DTO。"""
    roles = list(user.roles or [])
    return UserResponse(
        id=user.id,
        username=user.username,
        name=user.name,
        email=user.email,
        phone=user.phone,
        avatar=user.avatar,
        status=user.status,
        roles=[RoleBrief.model_validate(r) for r in roles],
        role_ids=[r.id for r in roles],
        permissions=_permissions_from_roles(roles),
        role=_compat_role(roles),
    )


def _load_roles_by_ids(db: Session, role_ids: list[int]) -> list[Role]:
    """按 ID 批量加载角色，任一无效则报错。"""
    if not role_ids:
        return []
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
    if len(roles) != len(set(role_ids)):
        raise BusinessException(message="存在无效的角色ID")
    return roles


def _resolve_roles(
    db: Session, role_ids: list[int] | None, role_code: str | None
) -> list[Role]:
    """优先 role_ids；否则按兼容字段 role 字符串解析。"""
    if role_ids:
        return _load_roles_by_ids(db, role_ids)
    if role_code:
        role = db.query(Role).filter(Role.code == role_code).first()
        if not role:
            raise BusinessException(message=f"角色不存在: {role_code}")
        return [role]
    return []


def _count_other_admins(db: Session, exclude_user_id: int | None = None) -> int:
    """统计启用管理员人数（可排除指定用户），用于末位保护。"""
    query = (
        db.query(User)
        .join(User.roles)
        .filter(Role.code == "admin", Role.status == 1, User.status == 1)
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.distinct().count()


def _ensure_not_removing_last_admin(
    db: Session, user: User, new_roles: list[Role]
) -> None:
    """禁止把系统中最后一个管理员角色摘掉。"""
    had_admin = any(r.code == "admin" for r in (user.roles or []))
    will_have_admin = any(r.code == "admin" for r in new_roles)
    if had_admin and not will_have_admin:
        if _count_other_admins(db, exclude_user_id=user.id) == 0:
            raise BusinessException(message="不能移除系统中最后一个管理员角色")


def get_user_info(user: User) -> UserResponse:
    """获取当前用户资料（含角色权限）"""
    return user_to_response(user)


def update_user_info(db: Session, user: User, data: UserUpdateRequest):
    """本人改资料（禁止改角色/状态/密码）"""
    # 本人改资料禁止改角色/状态
    user_dict = data.model_dump(
        exclude_none=True,
        exclude={"role", "role_ids", "status", "password"},
    )
    for field, value in user_dict.items():
        setattr(user, field, value)
    db.commit()
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.menus))
        .filter(User.id == user.id)
        .first()
    )
    return user_to_response(user)


def update_password(db: Session, user: User, data: PasswordUpdateRequest):
    """本人改密码（校验原密码且新旧不可相同）"""
    if not verify_password(data.old_password, user.password):
        raise BusinessException(message="原密码错误")
    if data.old_password == data.new_password:
        raise BusinessException(message="新密码不能与原密码相同")
    user.password = hash_password(data.new_password)
    db.commit()


def get_user_page_list(
    db: Session, page: int, page_size: int, keywords: str | None = None
):
    """分页模糊查询用户列表"""
    query = db.query(User)
    if keywords:
        query = query.filter(
            or_(User.username.ilike(f"%{keywords}%"), User.name.ilike(f"%{keywords}%"))
        )
    total = query.count()
    items = (
        query.options(joinedload(User.roles).joinedload(Role.menus))
        .order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(list=[user_to_response(item) for item in items], total=total)


def create_user(db: Session, data: UserCreateRequest):
    """新增用户（无角色时默认绑定 student）"""
    exist = db.query(User).filter(User.username == data.username).first()
    if exist:
        raise BusinessException(message="账号已存在")

    roles = _resolve_roles(db, data.role_ids, data.role)
    if not roles:
        student = db.query(Role).filter(Role.code == "student").first()
        if not student:
            raise BusinessException(message="默认学生角色不存在，请先初始化 RBAC")
        roles = [student]

    user = User(
        username=data.username,
        password=hash_password(data.password),
        name=data.name or data.username,
        email=data.email,
        phone=data.phone,
        avatar=data.avatar,
        status=data.status,
    )
    user.roles = roles
    db.add(user)
    db.commit()
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.menus))
        .filter(User.id == user.id)
        .first()
    )
    return user_to_response(user)


def update_user(db: Session, user_id: int, data: UserUpdateRequest):
    """更新用户资料与角色（禁止移除末位管理员）"""
    user = (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise BusinessException(message="用户不存在")

    payload = data.model_dump(exclude_none=True, exclude={"role", "role_ids"})
    for field, value in payload.items():
        setattr(user, field, value)

    # 角色更新
    if data.role_ids is not None or data.role is not None:
        new_roles = _resolve_roles(db, data.role_ids, data.role)
        if not new_roles:
            raise BusinessException(message="用户至少需要绑定一个角色")
        _ensure_not_removing_last_admin(db, user, new_roles)
        user.roles = new_roles

    db.commit()
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(Role.menus))
        .filter(User.id == user_id)
        .first()
    )
    return user_to_response(user)


def delete_user(db: Session, user_id: int, current_user: User):
    """删除用户（不可删本人或末位管理员）"""
    if user_id == current_user.id:
        raise BusinessException(message="不能删除当前登录的账号")
    user = (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise BusinessException(message="用户不存在")
    if any(r.code == "admin" for r in (user.roles or [])):
        if _count_other_admins(db, exclude_user_id=user.id) == 0:
            raise BusinessException(message="不能删除系统中最后一个管理员")
    user.roles.clear()
    db.delete(user)
    db.commit()
