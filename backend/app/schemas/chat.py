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
