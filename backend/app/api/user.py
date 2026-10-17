from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.common.response import Response
from app.models.user import User
from app.dependencies.auth import get_current_user, require_roles
from app.schemas.user import UserCreateRequest, UserUpdateRequest, PasswordUpdateRequest
from app.services import user_service
from app.database import get_db

router = APIRouter(prefix="/user", tags=["用户信息接口"])


@router.get("/me")
def get_user_info(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return Response.success(data=user_service.get_user_info(current_user))


@router.put("/me")
def update_user_info(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新当前用户信息"""
    res = user_service.update_user_info(db, current_user, data)
    return Response.success(data=res)


@router.put("/password")
def update_password(
    data: PasswordUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改当前用户密码"""
    user_service.update_password(db, current_user, data)
    return Response.success(message="密码修改成功")


@router.get("/list")
def get_user_list(
    page: int = 1,
    page_size: int = 10,
    keywords: str | None = None,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """分页查询用户列表（需 admin；可按账号/姓名筛选）"""
    res = user_service.get_user_page_list(db, page, page_size, keywords)
    return Response.success(data=res)


@router.post("")
def create_user(
    data: UserCreateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """新增用户（需 admin）"""
    res = user_service.create_user(db, data)
    return Response.success(data=res)


@router.put("/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """更新指定用户（需 admin）"""
    res = user_service.update_user(db, user_id, data)
    return Response.success(data=res)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """删除指定用户（需 admin；不可删本人）"""
    user_service.delete_user(db, user_id, current_user)
    return Response.success()
