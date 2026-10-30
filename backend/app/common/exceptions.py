import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.common.response import Response

logger = logging.getLogger(__name__)


class BusinessException(Exception):
    """自定义的业务异常"""

    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)


class UnauthorizedException(Exception):
    """认证失败异常：统一返回真正的 HTTP 401。"""

    def __init__(self, message: str = "登录已失效，请重新登录"):
        self.message = message
        super().__init__(message)


async def business_exception_handler(request: Request, exc: BusinessException):
    """自定义业务异常处理器"""
    return JSONResponse(
        status_code=200,
        content=Response.error(code=exc.code, message=exc.message).model_dump(),
    )


async def unauthorized_exception_handler(request: Request, exc: UnauthorizedException):
    """认证异常处理器：HTTP 401，并返回统一的业务响应体。"""
    return JSONResponse(
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
        content=Response.error(code=401, message=exc.message).model_dump(),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Http异常处理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content=Response.error(code=exc.status_code, message=exc.detail).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数异常处理器"""
    return JSONResponse(
        status_code=422,
        content=Response.error(code=422, message="请求参数校验错误").model_dump(),
    )


async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器（记录堆栈，避免线上问题无法定位）"""
    logger.exception(
        "未处理异常：%s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(
        status_code=500,
        content=Response.error(code=500, message="服务器内部错误").model_dump(),
    )
