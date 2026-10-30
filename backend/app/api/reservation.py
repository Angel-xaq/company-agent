from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.response import Response
from app.core.constants import PERM_BOOKING_VIEW
from app.database import get_db
from app.dependencies.auth import require_permissions
from app.models.user import User
from app.schemas.reservation import (
    ReservationCancelRequest,
    ReservationUpdateRequest,
)
from app.services import reservation_service

router = APIRouter(prefix="/reservations", tags=["我的预约"])


@router.get("/mine")
def get_my_reservations(
    scope: Literal["upcoming", "history"] = "upcoming",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(require_permissions(PERM_BOOKING_VIEW)),
    db: Session = Depends(get_db),
):
    """我的预约：scope=upcoming 即将开始 / history 历史记录。"""
    result = reservation_service.list_my_reservations(
        db,
        current_user,
        scope=scope,
        page=page,
        page_size=page_size,
    )
    return Response.success(data=result)


@router.put("/{reservation_id}")
def update_reservation(
    reservation_id: int,
    data: ReservationUpdateRequest,
    current_user: User = Depends(require_permissions(PERM_BOOKING_VIEW)),
    db: Session = Depends(get_db),
):
    """修改预约（仅本人或管理员，且预约未开始）。"""
    result = reservation_service.update_reservation(
        db, reservation_id, current_user, data
    )
    return Response.success(message="修改成功", data=result)


@router.post("/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    data: ReservationCancelRequest | None = None,
    current_user: User = Depends(require_permissions(PERM_BOOKING_VIEW)),
    db: Session = Depends(get_db),
):
    """取消预约（仅本人或管理员，且预约未开始）。"""
    result = reservation_service.cancel_reservation(
        db,
        reservation_id,
        current_user,
        reason=data.reason if data else None,
    )
    return Response.success(message="已取消预约", data=result)
