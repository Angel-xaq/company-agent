from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, time as time_type, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.constants import RESERVATION_CONFIRMED
from app.models.meeting_room import MeetingRoom
from app.models.reservation import Reservation
from app.models.user import User
from app.schemas.room import (
    BoardReservation,
    BoardResponse,
    BoardRoom,
    BusinessHours,
    RoomBrief,
)


def get_timezone() -> ZoneInfo:
    """业务时区，默认 Asia/Shanghai。"""
    return ZoneInfo(settings.TIMEZONE)


def now_local() -> datetime:
    """当前业务时区的 aware 时间。"""
    return datetime.now(get_timezone())


def parse_hhmm(value: str) -> time_type:
    """解析 HH:MM 配置。"""
    hour, minute = value.split(":")
    return time_type(int(hour), int(minute))


def local_day_bounds(day: date_type) -> tuple[datetime, datetime]:
    """返回某天营业时间对应的 aware 起止时间。"""
    tz = get_timezone()
    start = datetime.combine(day, parse_hhmm(settings.BUSINESS_START)).replace(
        tzinfo=tz
    )
    end = datetime.combine(day, parse_hhmm(settings.BUSINESS_END)).replace(tzinfo=tz)
    return start, end


def room_to_brief(room: MeetingRoom) -> RoomBrief:
    """会议室 ORM 转响应 DTO。"""
    return RoomBrief(
        id=room.id,
        name=room.name,
        location=room.location,
        capacity=room.capacity,
        equipment=list(room.equipment or []),
        description=room.description,
        status=room.status,
        sort=room.sort,
    )


def list_rooms(db: Session) -> list[RoomBrief]:
    """启用中的会议室列表。"""
    rooms = (
        db.query(MeetingRoom)
        .filter(MeetingRoom.status == 1)
        .order_by(MeetingRoom.sort.asc(), MeetingRoom.id.asc())
        .all()
    )
    return [room_to_brief(room) for room in rooms]


def _mask_name(name: str | None) -> str | None:
    """预约人姓名脱敏。"""
    if not name:
        return None
    return f"{name[0]}{'*' * max(len(name) - 1, 1)}"


def get_board(
    db: Session, day: date_type | None, current_user: User
) -> BoardResponse:
    """按日期返回会议室看板：房间 + 当日有效预约 + 营业时间配置。"""
    tz = get_timezone()
    target_day = day or now_local().date()
    day_start = datetime.combine(target_day, time_type.min).replace(tzinfo=tz)
    next_day = day_start + timedelta(days=1)
    business_start, business_end = local_day_bounds(target_day)

    rooms = (
        db.query(MeetingRoom)
        .filter(MeetingRoom.status == 1)
        .order_by(MeetingRoom.sort.asc(), MeetingRoom.id.asc())
        .all()
    )
    reservations = (
        db.query(Reservation)
        .options(joinedload(Reservation.user))
        .filter(
            Reservation.status == RESERVATION_CONFIRMED,
            Reservation.start_time < next_day,
            Reservation.end_time > day_start,
        )
        .order_by(Reservation.start_time.asc())
        .all()
    )

    grouped: dict[int, list[BoardReservation]] = defaultdict(list)
    for item in reservations:
        grouped[item.room_id].append(
            BoardReservation(
                id=item.id,
                title=item.title,
                start_time=item.start_time,
                end_time=item.end_time,
                status=item.status,
                mine=item.user_id == current_user.id,
                user_name=_mask_name(item.user.name if item.user else None),
            )
        )

    return BoardResponse(
        date=target_day.isoformat(),
        server_time=now_local(),
        business_hours=BusinessHours(
            start=business_start.strftime("%H:%M"),
            end=business_end.strftime("%H:%M"),
            slot_minutes=settings.SLOT_MINUTES,
        ),
        rooms=[
            BoardRoom(
                **room_to_brief(room).model_dump(),
                reservations=grouped.get(room.id, []),
            )
            for room in rooms
        ],
    )
