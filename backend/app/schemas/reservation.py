from datetime import datetime

from pydantic import BaseModel, Field


class ReservationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    purpose: str | None = Field(default=None, max_length=255)
    attendees: int | None = Field(default=None, ge=1)
    start_time: datetime
    end_time: datetime


class ReservationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    purpose: str | None = Field(default=None, max_length=255)
    attendees: int | None = Field(default=None, ge=1)
    room_id: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None


class ReservationCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class ReservationResponse(BaseModel):
    id: int
    room_id: int
    room_name: str
    user_id: int
    user_name: str
    title: str
    purpose: str | None = None
    attendees: int | None = None
    start_time: datetime
    end_time: datetime
    status: str
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    create_time: datetime
    mine: bool = False
