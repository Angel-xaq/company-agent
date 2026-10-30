from datetime import date as date_type

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import Response
from app.core.constants import PERM_ROOM_BOOK, PERM_ROOM_VIEW
from app.database import get_db
from app.dependencies.auth import require_permissions
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest
from app.services import reservation_service, room_service

router = APIRouter(prefix="/rooms", tags=["会议室"])


@router.get("")
def get_rooms(
    _current_user: User = Depends(require_permissions(PERM_ROOM_VIEW)),
    db: Session = Depends(get_db),
):
    """会议室列表。"""
    return Response.success(data=room_service.list_rooms(db))


@router.get("/board")
def get_board(
    day: date_type | None = Query(default=None, alias="date"),
    current_user: User = Depends(require_permissions(PERM_ROOM_VIEW)),
    db: Session = Depends(get_db),
):
    """会议室看板：房间、当日有效预约、营业时间与服务器时间。"""
    return Response.success(
        data=room_service.get_board(db, day, current_user)
    )


@router.post("/{room_id}/reservations")
def create_reservation(
    room_id: int,
    data: ReservationCreateRequest,
    current_user: User = Depends(require_permissions(PERM_ROOM_BOOK)),
    db: Session = Depends(get_db),
):
    """预约会议室（30 分钟粒度，单次最长 4 小时）。"""
    result = reservation_service.create_reservation(db, room_id, current_user, data)
    return Response.success(message="预约成功", data=result)
