from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.config import settings
from app.core.constants import (
    PERM_BOOKING_MANAGE,
    RESERVATION_CANCELLED,
    RESERVATION_CONFIRMED,
)
from app.dependencies.auth import has_permission
from app.models.meeting_room import MeetingRoom
from app.models.reservation import Reservation
from app.models.user import User
from app.schemas.reservation import (
    ReservationCreateRequest,
    ReservationResponse,
    ReservationUpdateRequest,
)
from app.services.room_service import (
    get_timezone,
    local_day_bounds,
    now_local,
)


def _as_local(value: datetime) -> datetime:
    """统一转换为业务时区；无时区输入按业务时区处理。"""
    tz = get_timezone()
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _to_response(
    reservation: Reservation,
    *,
    room_name: str | None = None,
    user_name: str | None = None,
    mine: bool = False,
) -> ReservationResponse:
    return ReservationResponse(
        id=reservation.id,
        room_id=reservation.room_id,
        room_name=room_name or (reservation.room.name if reservation.room else ""),
        user_id=reservation.user_id,
        user_name=user_name
        or (reservation.user.name if reservation.user else ""),
        title=reservation.title,
        purpose=reservation.purpose,
        attendees=reservation.attendees,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
        status=reservation.status,
        cancelled_at=reservation.cancelled_at,
        cancel_reason=reservation.cancel_reason,
        create_time=reservation.create_time,
        mine=mine,
    )


def _get_reservation(db: Session, reservation_id: int) -> Reservation:
    reservation = (
        db.query(Reservation)
        .options(
            joinedload(Reservation.room),
            joinedload(Reservation.user),
        )
        .filter(Reservation.id == reservation_id)
        .first()
    )
    if not reservation:
        raise BusinessException(message="预约不存在", code=404)
    return reservation


def _validate_time(
    db: Session,
    *,
    room: MeetingRoom,
    user_id: int,
    start: datetime,
    end: datetime,
    attendees: int | None,
    exclude_id: int | None = None,
) -> tuple[datetime, datetime]:
    """校验营业时间、粒度、时长、人数与每日次数，返回业务时区时间。"""
    start = _as_local(start)
    end = _as_local(end)
    now = now_local()

    if end <= start:
        raise BusinessException(message="结束时间必须晚于开始时间")
    if start < now - timedelta(minutes=1):
        raise BusinessException(message="不能预约已经过去的时间")

    day = start.date()
    if end.date() != day:
        raise BusinessException(message="暂不支持跨天预约")

    day_start, day_end = local_day_bounds(day)
    if start < day_start or end > day_end:
        raise BusinessException(
            message=f"预约时间需在 {settings.BUSINESS_START}-{settings.BUSINESS_END} 之间"
        )

    if end - start > timedelta(hours=settings.BOOKING_MAX_HOURS):
        raise BusinessException(
            message=f"单次预约不能超过 {settings.BOOKING_MAX_HOURS} 小时"
        )

    step = timedelta(minutes=settings.SLOT_MINUTES)
    if (start - day_start).total_seconds() % step.total_seconds() != 0:
        raise BusinessException(
            message=f"开始时间需与 {settings.SLOT_MINUTES} 分钟时段对齐"
        )
    if (end - day_start).total_seconds() % step.total_seconds() != 0:
        raise BusinessException(
            message=f"结束时间需与 {settings.SLOT_MINUTES} 分钟时段对齐"
        )

    latest_day = (now + timedelta(days=settings.BOOKING_MAX_DAYS)).date()
    if day > latest_day:
        raise BusinessException(
            message=f"最多只能预约未来 {settings.BOOKING_MAX_DAYS} 天内的会议室"
        )

    if attendees is not None and attendees > room.capacity:
        raise BusinessException(message=f"该会议室最多容纳 {room.capacity} 人")

    count_query = db.query(func.count(Reservation.id)).filter(
        Reservation.user_id == user_id,
        Reservation.status == RESERVATION_CONFIRMED,
        Reservation.start_time >= day_start,
        Reservation.start_time < day_start + timedelta(days=1),
    )
    if exclude_id is not None:
        count_query = count_query.filter(Reservation.id != exclude_id)
    if (count_query.scalar() or 0) >= settings.BOOKING_MAX_PER_DAY:
        raise BusinessException(
            message=f"每人每天最多预约 {settings.BOOKING_MAX_PER_DAY} 次"
        )

    return start, end


def _ensure_no_conflict(
    db: Session,
    room_id: int,
    start: datetime,
    end: datetime,
    exclude_id: int | None = None,
) -> None:
    """同一会议室时间重叠检查。"""
    query = db.query(Reservation.id).filter(
        Reservation.room_id == room_id,
        Reservation.status == RESERVATION_CONFIRMED,
        Reservation.start_time < end,
        Reservation.end_time > start,
    )
    if exclude_id is not None:
        query = query.filter(Reservation.id != exclude_id)
    if query.first():
        raise BusinessException(message="该时段已被预约，请选择其他时间", code=409)


def _lock_room(db: Session, room_id: int) -> MeetingRoom:
    room = (
        db.query(MeetingRoom)
        .filter(MeetingRoom.id == room_id)
        .with_for_update()
        .first()
    )
    if not room:
        raise BusinessException(message="会议室不存在", code=404)
    if room.status != 1:
        raise BusinessException(message="会议室已停用")
    return room


def create_reservation(
    db: Session, room_id: int, user: User, data: ReservationCreateRequest
) -> ReservationResponse:
    """创建预约：行锁会议室后做重叠检查，避免并发重复预约。"""
    room = _lock_room(db, room_id)
    start, end = _validate_time(
        db,
        room=room,
        user_id=user.id,
        start=data.start_time,
        end=data.end_time,
        attendees=data.attendees,
    )
    _ensure_no_conflict(db, room.id, start, end)

    title = data.title.strip()
    if not title:
        raise BusinessException(message="会议主题不能为空")

    reservation = Reservation(
        room_id=room.id,
        user_id=user.id,
        title=title,
        purpose=data.purpose,
        attendees=data.attendees,
        start_time=start,
        end_time=end,
        status=RESERVATION_CONFIRMED,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return _to_response(
        reservation, room_name=room.name, user_name=user.name, mine=True
    )


def update_reservation(
    db: Session,
    reservation_id: int,
    user: User,
    data: ReservationUpdateRequest,
) -> ReservationResponse:
    """修改预约：仅本人或管理员，且需在开始前。"""
    reservation = _get_reservation(db, reservation_id)
    is_admin = has_permission(user, PERM_BOOKING_MANAGE)

    if reservation.user_id != user.id and not is_admin:
        raise BusinessException(message="无权限操作该预约", code=403)
    if reservation.status != RESERVATION_CONFIRMED:
        raise BusinessException(message="该预约已取消，无法修改")
    if reservation.start_time <= now_local() and not is_admin:
        raise BusinessException(message="预约已开始，无法修改")

    target_room_id = data.room_id or reservation.room_id
    room = _lock_room(db, target_room_id)

    start = data.start_time if data.start_time is not None else reservation.start_time
    end = data.end_time if data.end_time is not None else reservation.end_time
    attendees = data.attendees if data.attendees is not None else reservation.attendees
    start, end = _validate_time(
        db,
        room=room,
        user_id=reservation.user_id,
        start=start,
        end=end,
        attendees=attendees,
        exclude_id=reservation.id,
    )
    _ensure_no_conflict(
        db, room.id, start, end, exclude_id=reservation.id
    )

    if data.title is not None:
        title = data.title.strip()
        if not title:
            raise BusinessException(message="会议主题不能为空")
        reservation.title = title
    if data.purpose is not None:
        reservation.purpose = data.purpose
    if data.attendees is not None:
        reservation.attendees = data.attendees
    reservation.room_id = room.id
    reservation.start_time = start
    reservation.end_time = end

    db.commit()
    db.refresh(reservation)
    return _to_response(
        reservation,
        room_name=room.name,
        mine=reservation.user_id == user.id,
    )


def cancel_reservation(
    db: Session, reservation_id: int, user: User, reason: str | None = None
) -> ReservationResponse:
    """取消预约：仅本人或管理员；已开始的预约仅管理员可取消。"""
    reservation = _get_reservation(db, reservation_id)
    is_admin = has_permission(user, PERM_BOOKING_MANAGE)

    if reservation.user_id != user.id and not is_admin:
        raise BusinessException(message="无权限操作该预约", code=403)
    if reservation.status != RESERVATION_CONFIRMED:
        raise BusinessException(message="该预约已取消")
    if not is_admin and reservation.start_time <= now_local():
        raise BusinessException(message="预约已开始，无法取消")

    reservation.status = RESERVATION_CANCELLED
    reservation.cancelled_at = now_local()
    reservation.cancel_reason = reason
    db.commit()
    db.refresh(reservation)
    return _to_response(
        reservation,
        mine=reservation.user_id == user.id,
    )


def list_my_reservations(
    db: Session,
    user: User,
    *,
    scope: str,
    page: int,
    page_size: int,
) -> PageResponse:
    """我的预约：即将开始 / 历史记录。"""
    now = now_local()
    query = db.query(Reservation).filter(Reservation.user_id == user.id)

    if scope == "history":
        query = query.filter(
            or_(
                Reservation.status == RESERVATION_CANCELLED,
                Reservation.end_time < now,
            )
        )
        order_by = Reservation.start_time.desc()
    else:
        query = query.filter(
            Reservation.status == RESERVATION_CONFIRMED,
            Reservation.end_time >= now,
        )
        order_by = Reservation.start_time.asc()

    total = query.count()
    items = (
        query.options(
            joinedload(Reservation.room),
            joinedload(Reservation.user),
        )
        .order_by(order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(
        list=[_to_response(item, mine=True) for item in items],
        total=total,
    )
