from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["权限验证"])


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """账号密码登录，返回 token 与用户信息"""
    result = auth_service.login(db, data)
    return Response.success(message="登录成功", data=result)


@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户并默认绑定 student 角色"""
    auth_service.register(db, data)
    return Response.success(message="注册成功")
