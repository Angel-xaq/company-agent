from fastapi import APIRouter, Depends, Request, Response as FastAPIResponse
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import Response
from app.config import settings
from app.database import get_db
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["权限验证"])


def _set_refresh_cookie(response: FastAPIResponse, raw_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: FastAPIResponse) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path="/api/auth",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )


@router.post("/login")
def login(
    data: LoginRequest,
    response: FastAPIResponse,
    db: Session = Depends(get_db),
):
    """账号密码登录：返回 15 分钟 Access Token，并通过 HttpOnly Cookie 下发 7 天 Refresh Token。"""
    result, refresh_token = auth_service.login(db, data)
    _set_refresh_cookie(response, refresh_token)
    return Response.success(message="登录成功", data=result)


@router.post("/refresh")
def refresh(
    request: Request,
    response: FastAPIResponse,
    db: Session = Depends(get_db),
):
    """使用 HttpOnly Cookie 中的 Refresh Token 换取新的 Access Token。"""
    raw_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_token:
        raise BusinessException(message="登录已失效，请重新登录", code=401)

    result, new_refresh_token = auth_service.refresh_access_token(db, raw_token)
    _set_refresh_cookie(response, new_refresh_token)
    return Response.success(message="续期成功", data=result)


@router.post("/logout")
def logout(
    request: Request,
    response: FastAPIResponse,
    db: Session = Depends(get_db),
):
    """退出登录：吊销当前 Refresh Token 并清除 Cookie。"""
    raw_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw_token:
        auth_service.revoke_refresh_token(db, raw_token)
    _clear_refresh_cookie(response)
    return Response.success(message="已退出登录")


@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户并默认绑定员工角色。"""
    auth_service.register(db, data)
    return Response.success(message="注册成功")
