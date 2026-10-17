from typing import Any
from pydantic import BaseModel


class Response(BaseModel):
    """统一封装的返回格式"""

    code: int
    message: str
    data: Any = None

    @classmethod
    def success(cls, message: str = "请求成功", data: Any = None):
        """构造成功响应（code=200）"""
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, code: int = 500, message: str = "请求失败"):
        """构造失败响应（默认 code=500）"""
        return cls(code=code, message=message)


class PageResponse(BaseModel):
    """分页的返回结果"""

    list: Any = []
    total: int = 0
