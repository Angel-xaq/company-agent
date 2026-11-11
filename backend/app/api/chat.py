from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.common.response import Response
from app.core.constants import PERM_CHAT_USE
from app.database import get_db
from app.dependencies.auth import require_permissions
from app.models.user import User
from app.schemas.chat import ChatActionRequest, ChatRequest
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["智能对话"])


@router.get("/sessions")
def get_sessions(
    current_user: User = Depends(require_permissions(PERM_CHAT_USE)),
    db: Session = Depends(get_db),
):
    """当前用户的会话列表。"""
    return Response.success(data=chat_service.list_sessions(db, current_user.id))


@router.post("/sessions")
def create_session(
    current_user: User = Depends(require_permissions(PERM_CHAT_USE)),
    db: Session = Depends(get_db),
):
    """新建空会话。"""
    return Response.success(data=chat_service.create_session(db, current_user.id))


@router.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: int,
    current_user: User = Depends(require_permissions(PERM_CHAT_USE)),
    db: Session = Depends(get_db),
):
    """会话历史消息。"""
    return Response.success(
        data=chat_service.get_messages(db, current_user.id, session_id)
    )


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    current_user: User = Depends(require_permissions(PERM_CHAT_USE)),
    db: Session = Depends(get_db),
):
    """删除会话及其消息。"""
    chat_service.delete_session(db, current_user.id, session_id)
    return Response.success(message="会话已删除")


@router.post("/stream")
def stream_chat(
    data: ChatRequest,
    current_user: User = Depends(require_permissions(PERM_CHAT_USE)),
):
    """SSE 流式对话。"""
    return StreamingResponse(
        chat_service.stream_chat(current_user.id, data.session_id, data.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/actions/pending")
def get_pending_actions(
    session_id: int,
    current_user: User = Depends(require_permissions(PERM_CHAT_USE)),
    db: Session = Depends(get_db),
):
    """当前会话待确认的操作，用于刷新页面后回挂确认卡片。"""
    return Response.success(
        data=chat_service.list_pending_actions(db, current_user.id, session_id)
    )


@router.post("/actions/{token}")
def confirm_action(
    token: str,
    data: ChatActionRequest,
    current_user: User = Depends(require_permissions(PERM_CHAT_USE)),
):
    """确认或拒绝待执行操作，从 checkpoint 恢复同一个对话线程。

    返回 SSE，事件类型与 /chat/stream 完全一致（delta / citation / action / done / error）。
    """
    return StreamingResponse(
        chat_service.confirm_action_stream(current_user.id, token, data.approve),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
