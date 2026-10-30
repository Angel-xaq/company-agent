from datetime import datetime

from pydantic import BaseModel


class RoomBrief(BaseModel):
    id: int
    name: str
    location: str | None = None
    capacity: int
    equipment: list[str] = []
    description: str | None = None
    status: int
    sort: int


class BoardReservation(BaseModel):
    id: int
    title: str
    start_time: datetime
    end_time: datetime
    status: str
    mine: bool = False
    user_name: str | None = None


class BoardRoom(RoomBrief):
    reservations: list[BoardReservation] = []


class BusinessHours(BaseModel):
    start: str
    end: str
    slot_minutes: int


class BoardResponse(BaseModel):
    date: str
    server_time: datetime
    business_hours: BusinessHours
    rooms: list[BoardRoom]
