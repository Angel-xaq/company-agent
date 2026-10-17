from pydantic import BaseModel, ConfigDict, Field


class RoleBrief(BaseModel):
    id: int
    code: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(BaseModel):
    id: int
    code: str
    name: str
    status: int
    remark: str | None = None
    menu_ids: list[int] = []

    model_config = ConfigDict(from_attributes=True)


class RoleCreateRequest(BaseModel):
    code: str
    name: str
    status: int = 1
    remark: str | None = None


class RoleUpdateRequest(BaseModel):
    code: str | None = None
    name: str | None = None
    status: int | None = None
    remark: str | None = None


class RoleMenusUpdateRequest(BaseModel):
    menu_ids: list[int] = Field(default_factory=list)
