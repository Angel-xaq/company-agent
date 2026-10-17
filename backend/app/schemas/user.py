from pydantic import BaseModel, ConfigDict, Field

from app.schemas.role import RoleBrief


class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    status: int
    roles: list[RoleBrief] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    # 兼容旧前端：含 admin 则取 admin，否则取第一个角色 code
    role: str | None = None
    role_ids: list[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=64)
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role_ids: list[int] = Field(default_factory=list)
    # 兼容：仍可传单个 role 字符串
    role: str | None = None
    status: int = 1


class PasswordUpdateRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=64)


class UserUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role_ids: list[int] | None = None
    role: str | None = None
    status: int | None = None
