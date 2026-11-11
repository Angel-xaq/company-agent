from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: int | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatSessionResponse(BaseModel):
    id: int
    title: str
    create_time: datetime
    update_time: datetime


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    citations: list[dict] | None = None
    create_time: datetime


class ChatActionRequest(BaseModel):
    approve: bool = True


class ChatPendingActionResponse(BaseModel):
    """待确认操作：用于刷新页面后回挂确认卡片。"""

    token: str
    tool_name: str
    params: dict
    summary: str
    expire_at: datetime
