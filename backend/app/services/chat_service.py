import asyncio
import json
import logging
import re
import secrets
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Annotated, Any, Generator, Literal, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Overwrite, interrupt
from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.config import settings
from app.core.constants import RESERVATION_CONFIRMED
from app.database import SessionLocal
from app.models.chat import ChatMessage, ChatPendingAction, ChatSession
from app.models.meeting_room import MeetingRoom
from app.models.reservation import Reservation
from app.models.role import Role
from app.models.user import User
from app.schemas.chat import (
    ChatMessageResponse,
    ChatPendingActionResponse,
    ChatSessionResponse,
)
from app.schemas.reservation import ReservationCreateRequest
from app.services import (
    knowledge_service,
    llm_client,
    reservation_service,
    room_service,
)
from app.services.checkpointer import get_checkpointer
from app.services.room_service import get_timezone, now_local

logger = logging.getLogger(__name__)

WRITE_TOOLS = {"create_reservation", "cancel_reservation"}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_rooms",
            "description": "查询指定日期的会议室及已有预约。可传入 start_time/end_time（HH:MM）判断哪些会议室空闲。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "日期 YYYY-MM-DD，不传则为今天",
                    },
                    "start_time": {"type": "string", "description": "开始时间 HH:MM"},
                    "end_time": {"type": "string", "description": "结束时间 HH:MM"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_reservations",
            "description": "查询当前用户的预约记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["upcoming", "history"],
                        "description": "upcoming 即将开始，history 历史记录",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "在公司知识库中检索员工手册、IT 指南等制度文档。每条结果包含 citation_index，回答引用时使用该编号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reservation",
            "description": "创建会议室预约。调用后系统会要求用户二次确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "room_id": {"type": "integer", "description": "会议室 ID"},
                    "start_time": {
                        "type": "string",
                        "description": "开始时间，ISO8601，例如 2026-10-26T10:00:00+08:00",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "结束时间，ISO8601，例如 2026-10-26T11:00:00+08:00",
                    },
                    "title": {"type": "string", "description": "会议主题"},
                    "purpose": {"type": "string", "description": "用途说明，可选"},
                    "attendees": {"type": "integer", "description": "参会人数，可选"},
                },
                "required": ["room_id", "start_time", "end_time", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reservation",
            "description": "取消预约。调用后系统会要求用户二次确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reservation_id": {
                        "type": "integer",
                        "description": "预约编号",
                    }
                },
                "required": ["reservation_id"],
            },
        },
    },
]


def _sse(event: str, data: dict) -> str:
    return (
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    )


def _parse_args(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _fmt_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=get_timezone())
    else:
        value = value.astimezone(get_timezone())
    return value.strftime("%m-%d %H:%M")


def _fmt_hm(value: datetime) -> str:
    return _fmt_time(value).split(" ")[-1]


def _iso_local(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=get_timezone())
    else:
        value = value.astimezone(get_timezone())
    return value.isoformat()


def _fmt_iso(value: Any) -> str:
    """把模型给的 ISO 时间串渲染成 MM-DD HH:MM；解析失败时原样返回。"""
    if not value:
        return "?"
    try:
        return _fmt_time(datetime.fromisoformat(str(value)))
    except ValueError:
        return str(value)


def _session_response(session: ChatSession) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        create_time=session.create_time,
        update_time=session.update_time,
    )


def list_sessions(db: Session, user_id: int) -> list[ChatSessionResponse]:
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(ChatSession.update_time.desc())
        .limit(50)
        .all()
    )
    return [_session_response(item) for item in sessions]


def create_session(
    db: Session, user_id: int, title: str = "新对话"
) -> ChatSessionResponse:
    session = ChatSession(user_id=user_id, title=title[:100] or "新对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_response(session)


def _get_session(db: Session, user_id: int, session_id: int) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if not session:
        raise BusinessException(message="会话不存在", code=404)
    return session


def get_messages(
    db: Session, user_id: int, session_id: int
) -> list[ChatMessageResponse]:
    _get_session(db, user_id, session_id)
    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role.in_(("user", "assistant")),
        )
        .order_by(ChatMessage.id.asc())
        .all()
    )
    return [
        ChatMessageResponse(
            id=item.id,
            role=item.role,
            content=(
                _clean_answer(item.content)
                if item.role == "assistant"
                else item.content
            ),
            citations=item.citations,
            create_time=item.create_time,
        )
        for item in messages
    ]


def delete_session(db: Session, user_id: int, session_id: int) -> None:
    session = _get_session(db, user_id, session_id)
    db.delete(session)
    db.commit()
    try:
        get_checkpointer().delete_thread(_thread_id(session_id))
    except Exception:
        # checkpoint 清理失败不影响业务数据删除
        logger.warning("删除会话 checkpoint 失败：%s", session_id, exc_info=True)


def _save_message(
    db: Session,
    session: ChatSession,
    role: str,
    content: str,
    *,
    citations: list[dict] | None = None,
    usage: dict | None = None,
) -> ChatMessage:
    message = ChatMessage(
        session_id=session.id,
        role=role,
        content=content,
        citations=citations,
        usage=usage,
    )
    session.update_time = datetime.now()
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _save_session_message(db: Session, session_id: int, content: str) -> None:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session is not None:
        _save_message(db, session, "assistant", content)


def _history(db: Session, session_id: int) -> list[dict]:
    rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role.in_(("user", "assistant")),
        )
        .order_by(ChatMessage.id.desc())
        .limit(12)
        .all()
    )
    return [{"role": item.role, "content": item.content} for item in reversed(rows)]


def _system_prompt(user: User, summary: str = "") -> str:
    prompt = f"""你是公司智能助手，负责回答员工问题并协助会议室预约。
当前时间：{now_local().strftime('%Y-%m-%d %H:%M')}（{settings.TIMEZONE}）
当前用户：{user.name}
预约规则：营业时间 {settings.BUSINESS_START}-{settings.BUSINESS_END}，{settings.SLOT_MINUTES} 分钟粒度，单次最长 {settings.BOOKING_MAX_HOURS} 小时。

要求：
1. 涉及会议室空闲情况、预约记录时必须调用工具，不要编造房间、时间或预约编号。
2. 创建或取消预约时调用对应工具；系统会把操作交给用户确认，确认结果会以工具结果返回，不要在确认前声称已完成。
3. 工具返回 error 时如实告知用户并给出替代方案（例如重新查询会议室），不要用相同参数重复提交。
4. 用户拒绝或取消操作后，不要再调用写工具，直接说明未做修改。
5. 制度、流程类问题先调用 search_knowledge。检索结果每条带 citation_index；只在相关句子末尾使用 [citation_index]（如 [1]），只引用实际使用的条目，不要引用未使用的检索结果。
6. 不要输出来源清单，不要写“来源：xxx”，不要单独输出“[1] 文档名”这类尾注；来源由前端根据上标展示。
7. 未检索到相关内容时明确说明，不要编造制度条款。
8. 使用中文简洁回答，必要时列出要点。"""
    if summary:
        prompt += f"\n\n【早期对话摘要】（仅供参考，按需使用）\n{summary}"
    return prompt


def _create_pending_action(
    db: Session,
    session: ChatSession,
    user: User,
    tool_name: str,
    params: dict,
) -> ChatPendingAction:
    action = ChatPendingAction(
        token=secrets.token_urlsafe(24),
        session_id=session.id,
        user_id=user.id,
        tool_name=tool_name,
        params=params,
        status="pending",
        expire_at=now_local() + timedelta(minutes=10),
    )
    db.add(action)
    db.flush()
    return action


def _action_summary(
    tool_name: str,
    params: dict,
    target: MeetingRoom | Reservation | None = None,
) -> str:
    """纯展示函数：把待确认操作渲染成一句话，不再访问数据库。

    target 由 _load_write_target 一次性加载后传入，既避免重复查库，
    也保证卡片展示的就是刚刚校验过的那个对象。
    """
    if tool_name == "create_reservation":
        room_name = target.name if isinstance(target, MeetingRoom) else ""
        if not room_name:
            room_id = params.get("room_id")
            room_name = f"#{room_id}" if room_id is not None else "未知会议室"
        return (
            f"预约 {room_name}，"
            f"{_fmt_iso(params.get('start_time'))} 至 "
            f"{_fmt_iso(params.get('end_time'))}，"
            f"主题：{params.get('title') or '未填写'}"
        )

    if tool_name == "cancel_reservation":
        if isinstance(target, Reservation):
            room_name = target.room.name if target.room else ""
            return (
                f"取消预约 #{target.id}：{room_name} "
                f"{_fmt_time(target.start_time)}-{_fmt_time(target.end_time)}"
            )
        return f"取消预约 #{params.get('reservation_id')}"

    return "待确认操作"


def _pending_prompt(tool_name: str) -> str:
    if tool_name == "create_reservation":
        return "已为您整理好预约信息，请确认后执行。"
    if tool_name == "cancel_reservation":
        return "请确认是否取消该预约。"
    return "请确认是否执行该操作。"


def _thread_id(session_id: int) -> str:
    """LangGraph 线程标识：一个会话对应一个 thread。"""
    return f"chat-{session_id}"


def _run_config(session_id: int) -> RunnableConfig:
    return {
        "configurable": {"thread_id": _thread_id(session_id)},
        "recursion_limit": settings.CHAT_RECURSION_LIMIT,
    }


def _update_action_status(db: Session, token: str | None, status: str) -> None:
    """更新待确认操作状态（审计用）。"""
    if not token:
        return
    try:
        db.query(ChatPendingAction).filter(
            ChatPendingAction.token == token
        ).update(
            {"status": status, "update_time": datetime.now()},
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        logger.warning("更新待确认操作状态失败：%s", status, exc_info=True)
        db.rollback()


def _expire_pending_actions(db: Session, session_id: int) -> None:
    """用户开启新一轮对话时，作废上一个未确认的写操作。"""
    try:
        db.query(ChatPendingAction).filter(
            ChatPendingAction.session_id == session_id,
            ChatPendingAction.status == "pending",
        ).update({"status": "expired"}, synchronize_session=False)
        db.commit()
    except Exception:
        logger.warning("作废待确认操作失败", exc_info=True)
        db.rollback()


def _claim_action(
    db: Session, user_id: int, token: str, approve: bool
) -> ChatPendingAction:
    """原子占用确认令牌，避免同一次确认被重复提交。"""
    action = (
        db.query(ChatPendingAction)
        .filter(
            ChatPendingAction.token == token,
            ChatPendingAction.user_id == user_id,
        )
        .first()
    )
    if action is None:
        raise BusinessException(message="操作不存在或已失效", code=404)
    if action.status == "executing":
        raise BusinessException(message="操作正在处理中，请稍候", code=409)
    if action.status == "failed":
        raise BusinessException(message="该操作已执行失败，请重新发起", code=409)
    if action.status == "expired":
        raise BusinessException(message="操作已过期，请重新发起", code=410)
    if action.status != "pending":
        raise BusinessException(message="该操作已处理", code=409)
    expire_at = action.expire_at
    if expire_at.tzinfo is None:
        expire_at = expire_at.replace(tzinfo=get_timezone())
    if expire_at < now_local():
        action.status = "expired"
        db.commit()
        raise BusinessException(message="操作已过期，请重新发起", code=410)

    target = "executing" if approve else "rejected"
    claimed = (
        db.query(ChatPendingAction)
        .filter(
            ChatPendingAction.id == action.id,
            ChatPendingAction.status == "pending",
        )
        .update(
            {"status": target, "update_time": datetime.now()},
            synchronize_session=False,
        )
    )
    db.commit()
    if claimed != 1:
        raise BusinessException(message="该操作已处理", code=409)
    return action


def list_pending_actions(
    db: Session, user_id: int, session_id: int
) -> list[ChatPendingActionResponse]:
    """当前会话待确认的操作（顺带清理已过期的），用于刷新页面后回挂确认卡片。"""
    _get_session(db, user_id, session_id)
    now = now_local()
    actions = (
        db.query(ChatPendingAction)
        .filter(
            ChatPendingAction.session_id == session_id,
            ChatPendingAction.user_id == user_id,
            ChatPendingAction.status == "pending",
        )
        .order_by(ChatPendingAction.id.desc())
        .all()
    )

    result: list[ChatPendingActionResponse] = []
    expired = False
    for action in actions:
        expire_at = action.expire_at
        if expire_at.tzinfo is None:
            expire_at = expire_at.replace(tzinfo=get_timezone())
        if expire_at < now:
            action.status = "expired"
            expired = True
            continue
        params = action.params or {}
        _, target = _load_write_target(db, action.tool_name, params)
        result.append(
            ChatPendingActionResponse(
                token=action.token,
                tool_name=action.tool_name,
                params=params,
                summary=_action_summary(action.tool_name, params, target),
                expire_at=expire_at,
            )
        )
    if expired:
        db.commit()
    return result


def sweep_stale_actions(db: Session | None = None) -> int:
    """把超时仍处于 executing 的操作置为 failed，避免令牌被永久占用。"""
    own_session = db is None
    target_db = db or SessionLocal()
    try:
        deadline = datetime.now() - timedelta(
            minutes=settings.CHAT_ACTION_EXECUTING_TIMEOUT_MINUTES
        )
        count = (
            target_db.query(ChatPendingAction)
            .filter(
                ChatPendingAction.status == "executing",
                ChatPendingAction.update_time < deadline,
            )
            .update(
                {"status": "failed", "update_time": datetime.now()},
                synchronize_session=False,
            )
        )
        target_db.commit()
        if count:
            logger.warning("回收超时未完成的待确认操作：%s 条", count)
        return count
    except Exception:
        target_db.rollback()
        raise
    finally:
        if own_session:
            target_db.close()


async def run_action_sweeper() -> None:
    """应用内定时任务：定期回收僵尸 executing 状态。"""
    interval = max(settings.CHAT_ACTION_SWEEP_INTERVAL_SECONDS, 30)
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(sweep_stale_actions)
        except Exception:
            logger.warning("清理超时待确认操作失败", exc_info=True)


def _load_write_target(
    db: Session, name: str, args: dict[str, Any]
) -> tuple[str | None, MeetingRoom | Reservation | None]:
    """一次性加载写操作的目标对象，同时完成预检。

    返回 (错误信息, 目标对象)：
    - 错误信息为 None 表示预检通过，可以生成确认卡片；
    - 目标对象用于生成卡片文案，调用方不必再查一次同一行。
    对象已加载但状态不合法时（如房间停用、预约已取消），错误信息非空
    而目标对象仍然返回，便于展示真实信息。
    """
    if name == "create_reservation":
        missing = [
            key
            for key in ("room_id", "start_time", "end_time", "title")
            if not str(args.get(key) or "").strip()
        ]
        if missing:
            return f"缺少必填参数：{'、'.join(missing)}，请先向用户确认", None
        try:
            room_id = int(args["room_id"])
        except (TypeError, ValueError):
            return "room_id 必须是数字，请先调用 query_rooms 获取真实房间 ID", None
        room = db.query(MeetingRoom).filter(MeetingRoom.id == room_id).first()
        if room is None:
            return (
                f"会议室 {room_id} 不存在，请调用 query_rooms 查询真实会议室后再预约，"
                "不要编造 ID"
            ), None
        if room.status != 1:
            return f"会议室「{room.name}」已停用，请更换其他会议室", room
        return None, room

    if name == "cancel_reservation":
        raw = args.get("reservation_id")
        try:
            reservation_id = int(str(raw).strip())
        except (TypeError, ValueError):
            return (
                "reservation_id 必须是数字，请先调用 list_my_reservations 获取真实编号"
            ), None
        reservation = (
            db.query(Reservation)
            .options(joinedload(Reservation.room))
            .filter(Reservation.id == reservation_id)
            .first()
        )
        if reservation is None:
            return (
                f"预约 {reservation_id} 不存在，请先调用 list_my_reservations 获取真实编号，"
                "不要编造"
            ), None
        if reservation.status != RESERVATION_CONFIRMED:
            return f"预约 {reservation_id} 已取消，无法再次取消", reservation
        return None, reservation

    return None, None


def _execute_write_tool(
    db: Session, user: User, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    """在图内执行写工具，异常由调用方转换为工具错误回喂模型。"""
    if name == "create_reservation":
        payload = ReservationCreateRequest(
            title=str(args.get("title") or "").strip(),
            purpose=args.get("purpose"),
            attendees=args.get("attendees"),
            start_time=args["start_time"],
            end_time=args["end_time"],
        )
        result = reservation_service.create_reservation(
            db, int(args["room_id"]), user, payload
        )
        return {
            "status": "ok",
            "message": (
                f"预约成功：{result.room_name} "
                f"{_fmt_time(result.start_time)}-{_fmt_time(result.end_time)}"
            ),
            "reservation": {
                "id": result.id,
                "room_id": result.room_id,
                "room_name": result.room_name,
                "title": result.title,
                "start_time": _iso_local(result.start_time),
                "end_time": _iso_local(result.end_time),
            },
        }

    if name == "cancel_reservation":
        result = reservation_service.cancel_reservation(
            db, int(args["reservation_id"]), user, "通过智能助手取消"
        )
        return {
            "status": "ok",
            "message": (
                f"已取消预约：{result.room_name} "
                f"{_fmt_time(result.start_time)}-{_fmt_time(result.end_time)}"
            ),
        }

    raise BusinessException(message=f"不支持的写操作：{name}")


def _sanitize_dialog(messages: list[dict]) -> list[dict]:
    """丢弃没有配对工具结果的 assistant 消息，避免下一轮请求被模型拒绝。"""
    cleaned: list[dict] = []
    pending: dict[str, int] = {}
    for item in messages:
        role = item.get("role")
        if role == "tool":
            call_id = item.get("tool_call_id")
            if call_id in pending:
                pending.pop(call_id)
                cleaned.append(item)
            continue

        if pending:
            drop = set(pending.values())
            cleaned = [msg for index, msg in enumerate(cleaned) if index not in drop]
            pending.clear()

        if role == "assistant" and item.get("tool_calls"):
            index = len(cleaned)
            cleaned.append(item)
            for call in item.get("tool_calls") or []:
                if call.get("id"):
                    pending[call["id"]] = index
        else:
            cleaned.append(item)

    if pending:
        drop = set(pending.values())
        cleaned = [msg for index, msg in enumerate(cleaned) if index not in drop]
    return cleaned


def _filter_available(board, start: str, end: str) -> list[int]:
    tz = get_timezone()
    try:
        start_dt = datetime.fromisoformat(f"{board.date}T{start}:00").replace(tzinfo=tz)
        end_dt = datetime.fromisoformat(f"{board.date}T{end}:00").replace(tzinfo=tz)
    except ValueError:
        return []
    if end_dt <= start_dt:
        return []

    available: list[int] = []
    for room in board.rooms:
        conflict = any(
            item.start_time < end_dt and item.end_time > start_dt
            for item in room.reservations
        )
        if not conflict:
            available.append(room.id)
    return available


def _execute_read_tool(
    db: Session, user: User, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    if name == "query_rooms":
        day: date_type | None = None
        raw_date = args.get("date")
        if raw_date:
            try:
                day = date_type.fromisoformat(str(raw_date)[:10])
            except ValueError:
                day = None
        board = room_service.get_board(db, day, user)
        result = {
            "date": board.date,
            "business_hours": board.business_hours.model_dump(),
            "rooms": [
                {
                    "id": room.id,
                    "name": room.name,
                    "capacity": room.capacity,
                    "equipment": room.equipment,
                    "reservations": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "start_time": _iso_local(item.start_time),
                            "end_time": _iso_local(item.end_time),
                        }
                        for item in room.reservations
                    ],
                }
                for room in board.rooms
            ],
        }
        start = args.get("start_time")
        end = args.get("end_time")
        if start and end:
            result["available_room_ids"] = _filter_available(
                board, str(start), str(end)
            )
        return result

    if name == "list_my_reservations":
        raw_scope = str(args.get("scope") or "upcoming")
        scope: Literal["upcoming", "history"] = (
            "history" if raw_scope == "history" else "upcoming"
        )
        page = reservation_service.list_my_reservations(
            db, user, scope=scope, page=1, page_size=20
        )
        return {
            "scope": scope,
            "items": [item.model_dump(mode="json") for item in page.list],
        }

    if name == "search_knowledge":
        try:
            items = knowledge_service.search_knowledge(
                db, str(args.get("query", "")), top_k=int(args.get("top_k", 5) or 5)
            )
        except Exception:
            logger.exception("知识库检索失败")
            items = []
        return {"items": items}

    return {"error": f"未知工具：{name}"}


def _merge_messages(
    left: list[dict] | None, right: list[dict] | None
) -> list[dict]:
    """messages 使用追加语义；需要整表替换时由节点返回 Overwrite(...)。"""
    return list(left or []) + list(right or [])


class AgentState(TypedDict, total=False):
    """图内流转的状态；db / user / session 通过构建图时的闭包注入，不进入 state。

    所有字段按需写入，因此使用 total=False，节点返回的也是局部更新。
    """

    messages: Annotated[list[dict], _merge_messages]
    summary: str
    answer: str
    citations: list[dict]
    tool_calls: list[dict]
    write_calls: list[dict]
    last_content: str
    pending: dict | None
    need_summary: bool
    usage: dict
    rounds: int


def _need_summary(dialog: list[dict]) -> bool:
    if len(dialog) > settings.CHAT_HISTORY_MAX_MESSAGES:
        return True
    total = sum(len(str(item.get("content") or "")) for item in dialog)
    return total > settings.CHAT_HISTORY_MAX_CHARS


def _summarize_messages(previous: str, head: list[dict]) -> str:
    """把较早的对话压缩成摘要；模型不可用时退化为本地截断。"""
    lines: list[str] = []
    for item in head:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "用户" if item.get("role") == "user" else "助手"
        lines.append(f"{label}：{content[:500]}")
    transcript = "\n".join(lines)[:6000]
    if not transcript:
        return previous

    if llm_client.is_configured():
        try:
            content, _, _ = llm_client.chat_completion(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是对话摘要助手。把已有摘要与新增对话压缩成不超过 300 字的中文摘要，"
                            "保留用户身份与偏好、已确认的事实、进行中的事项；不要编造内容。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"已有摘要：\n{previous or '无'}\n\n新增对话：\n{transcript}",
                    },
                ]
            )
            if content.strip():
                return content.strip()[:2000]
        except Exception:
            logger.warning("对话摘要失败，退化为本地截断", exc_info=True)

    merged = f"{previous}\n{transcript}".strip()
    return merged[-2000:]


def _build_chat_graph(db: Session, user: User, session: ChatSession):
    """构建对话图：prepare → (summarize) → agent → read_tools → write_tool(interrupt) → finalize。"""
    workflow = StateGraph(AgentState)

    def prepare_node(state: AgentState) -> dict:
        """每轮开始：刷新 system prompt、补齐历史、重置单轮字段。"""
        messages = list(state.get("messages") or [])
        dialog = [item for item in messages if item.get("role") != "system"]
        if len(dialog) <= 1:
            # 新会话，或 checkpoint 丢失（进程重启）时用库里的历史兜底
            history = _history(db, session.id)
            if history:
                dialog = history
        dialog = _sanitize_dialog(dialog)
        summary = state.get("summary") or ""
        return {
            "messages": Overwrite(
                [
                    {"role": "system", "content": _system_prompt(user, summary)},
                    *dialog,
                ]
            ),
            "answer": "",
            "citations": [],
            "tool_calls": [],
            "write_calls": [],
            "last_content": "",
            "pending": None,
            "usage": {},
            "rounds": 0,
            "need_summary": _need_summary(dialog),
        }

    def summarize_node(state: AgentState) -> dict:
        """把较早的对话压成摘要，只保留最近若干条原文。"""
        messages = list(state.get("messages") or [])
        dialog = [item for item in messages if item.get("role") != "system"]
        keep = max(settings.CHAT_HISTORY_KEEP_MESSAGES, 2)
        head, tail = dialog[:-keep], dialog[-keep:]
        # 保留窗口必须从用户消息开始，避免出现孤立的 tool 消息
        while tail and tail[0].get("role") != "user":
            tail = tail[1:]
        if not tail:
            tail = dialog[-keep:]
        summary = _summarize_messages(state.get("summary") or "", head)
        return {
            "summary": summary,
            "messages": Overwrite(
                [
                    {"role": "system", "content": _system_prompt(user, summary)},
                    *tail,
                ]
            ),
            "need_summary": False,
        }

    def agent_node(state: AgentState) -> dict:
        writer = get_stream_writer()
        messages = list(state.get("messages") or [])
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        usage: dict = {}

        try:
            for event in llm_client.chat_completion_stream(messages, TOOLS):
                if event["type"] == "delta":
                    text = event.get("content", "")
                    if text:
                        content_parts.append(text)
                        writer({"event": "delta", "data": {"content": text}})
                elif event["type"] == "done":
                    tool_calls = event.get("tool_calls", [])
        except Exception:
            # 流式不可用时回退到非流式，保证工具调用仍能工作
            if content_parts:
                raise
            logger.warning("流式调用失败，回退非流式", exc_info=True)
            content, tool_calls, usage = llm_client.chat_completion(messages, TOOLS)
            if content:
                content_parts.append(content)
                writer({"event": "delta", "data": {"content": content}})

        content = "".join(content_parts)
        new_messages: list[dict] = []
        if content or tool_calls:
            assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            new_messages.append(assistant_message)

        return {
            "messages": new_messages,
            "answer": state.get("answer", "") + content,
            "tool_calls": tool_calls,
            "last_content": content,
            "usage": usage or state.get("usage", {}),
            "rounds": state.get("rounds", 0) + 1,
        }

    def read_tools_node(state: AgentState) -> dict:
        """执行只读工具；写操作不执行，只生成待用户确认的操作。"""
        writer = get_stream_writer()
        new_messages: list[dict] = []
        write_calls: list[dict] = []
        citations = list(state.get("citations") or [])
        citation_by_key = {
            (item.get("document_id"), item.get("chunk_index")): item
            for item in citations
        }

        for tool_call in state.get("tool_calls") or []:
            name = tool_call["function"]["name"]
            args = _parse_args(tool_call["function"].get("arguments"))

            if name in WRITE_TOOLS:
                write_calls.append(tool_call)
                continue

            result: dict[str, Any]
            try:
                result = _execute_read_tool(db, user, name, args)
            except Exception as exc:
                logger.warning("工具执行失败：%s", name, exc_info=True)
                result = {"error": str(exc)}

            if name == "search_knowledge":
                raw_items = result.get("items")
                items = raw_items if isinstance(raw_items, list) else []
                enriched: list[dict[str, Any]] = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = (item.get("document_id"), item.get("chunk_index"))
                    if key not in citation_by_key:
                        citation_by_key[key] = {
                            **item,
                            "index": len(citation_by_key) + 1,
                        }
                    enriched.append(
                        {
                            **item,
                            "citation_index": citation_by_key[key]["index"],
                        }
                    )
                result["items"] = enriched
                citations = list(citation_by_key.values())

            new_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

        pending: dict | None = None
        if write_calls:
            # 一轮只确认一个写操作，其余直接回绝，避免一次点击产生多个副作用
            for extra in write_calls[1:]:
                new_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": extra["id"],
                        "content": json.dumps(
                            {"error": "一次只能确认一个写操作，请先处理已提交的这一个"},
                            ensure_ascii=False,
                        ),
                    }
                )
            first = write_calls[0]
            name = first["function"]["name"]
            args = _parse_args(first["function"].get("arguments"))

            error, target = _load_write_target(db, name, args)
            if error:
                # 参数/对象不存在时不打扰用户，直接把错误回喂模型
                write_calls = []
                new_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": first["id"],
                        "content": json.dumps(
                            {"error": error}, ensure_ascii=False
                        ),
                    }
                )
            else:
                write_calls = [first]
                # 先取文案再 commit：commit 会让 target 过期，再读属性又会打一次查询
                summary = _action_summary(name, args, target)
                action = _create_pending_action(db, session, user, name, args)
                db.commit()

                preamble = (state.get("last_content") or "").strip()
                if not preamble:
                    preamble = _pending_prompt(name)
                    writer({"event": "delta", "data": {"content": preamble}})
                # 确认前把引导语单独落库，确认后模型再生成结果，避免重复
                _save_message(db, session, "assistant", _clean_answer(preamble))

                pending = {
                    "token": action.token,
                    "tool_name": name,
                    "params": args,
                    "summary": summary,
                    "expire_at": action.expire_at.isoformat(),
                }
                writer({"event": "action", "data": pending})

        return {
            "messages": new_messages,
            "citations": citations,
            "tool_calls": [],
            "write_calls": write_calls,
            "pending": pending,
        }

    def write_tool_node(state: AgentState) -> dict:
        """在人机确认点挂起；恢复后在图内执行写操作，结果回喂模型。"""
        write_calls = list(state.get("write_calls") or [])
        if not write_calls:
            return {}

        call = write_calls[0]
        name = call["function"]["name"]
        args = _parse_args(call["function"].get("arguments"))
        pending = state.get("pending") or {}
        token = pending.get("token")

        decision = interrupt(
            {
                "token": token,
                "tool_name": name,
                "params": args,
                "summary": pending.get("summary", ""),
            }
        )
        writer = get_stream_writer()
        approve = bool(decision.get("approve")) if isinstance(decision, dict) else False

        if not approve:
            _update_action_status(db, token, "rejected")
            result: dict[str, Any] = {
                "status": "rejected",
                "message": "用户已取消该操作，未做任何修改",
            }
        else:
            try:
                result = _execute_write_tool(db, user, name, args)
                _update_action_status(db, token, "confirmed")
            except BusinessException as exc:
                _update_action_status(db, token, "failed")
                result = {"status": "failed", "error": exc.message}
            except ValueError:
                _update_action_status(db, token, "failed")
                result = {
                    "status": "failed",
                    "error": "时间或参数格式无法解析，请用 YYYY-MM-DDTHH:MM:SS+08:00 重新描述",
                }
            except Exception:
                logger.exception("写工具执行失败：%s", name)
                _update_action_status(db, token, "failed")
                result = {"status": "failed", "error": "系统处理失败，请稍后重试"}

        writer(
            {
                "event": "tool_result",
                "data": {"tool_name": name, "result": result},
            }
        )
        # 确认前的引导语已单独落库，这里清空避免 finalize 重复保存
        return {
            "messages": [
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            ],
            "write_calls": [],
            "pending": None,
            "answer": "",
            "last_content": "",
            "tool_calls": [],
        }

    def finalize_node(state: AgentState) -> dict:
        writer = get_stream_writer()
        raw_answer = state.get("answer", "").strip()
        answer, used = _filter_citations(
            _clean_answer(raw_answer), state.get("citations", [])
        )
        if not answer:
            answer = "抱歉，我暂时无法回答这个问题，请换一种说法。"
            writer({"event": "delta", "data": {"content": answer}})

        citations = _dedup_citations(used)
        saved = _save_message(
            db,
            session,
            "assistant",
            answer,
            citations=citations or None,
            usage=state.get("usage") or None,
        )

        for citation in citations:
            writer({"event": "citation", "data": citation})

        writer(
            {
                "event": "done",
                "data": {
                    "message_id": saved.id,
                    "session_id": session.id,
                    "usage": state.get("usage") or {},
                    "answer": answer,
                },
            }
        )
        return {"answer": answer, "citations": citations}

    def after_prepare(state: AgentState) -> str:
        return "summarize" if state.get("need_summary") else "agent"

    def after_agent(state: AgentState) -> str:
        return "read_tools" if state.get("tool_calls") else "finalize"

    def after_read_tools(state: AgentState) -> str:
        if state.get("write_calls"):
            return "write_tool"
        if state.get("rounds", 0) >= settings.CHAT_MAX_TOOL_ROUNDS:
            return "finalize"
        return "agent"

    def after_write_tool(state: AgentState) -> str:
        if state.get("rounds", 0) >= settings.CHAT_MAX_TOOL_ROUNDS:
            return "finalize"
        return "agent"

    workflow.add_node("prepare", prepare_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("read_tools", read_tools_node)
    workflow.add_node("write_tool", write_tool_node)
    workflow.add_node("finalize", finalize_node)

    workflow.add_edge(START, "prepare")
    workflow.add_conditional_edges(
        "prepare", after_prepare, {"summarize": "summarize", "agent": "agent"}
    )
    workflow.add_edge("summarize", "agent")
    workflow.add_conditional_edges(
        "agent", after_agent, {"read_tools": "read_tools", "finalize": "finalize"}
    )
    workflow.add_conditional_edges(
        "read_tools",
        after_read_tools,
        {"write_tool": "write_tool", "agent": "agent", "finalize": "finalize"},
    )
    workflow.add_conditional_edges(
        "write_tool",
        after_write_tool,
        {"agent": "agent", "finalize": "finalize"},
    )
    workflow.add_edge("finalize", END)
    # checkpointer 是全局单例，图按请求重建不影响 thread 的持久化
    return workflow.compile(checkpointer=get_checkpointer())


CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")
SOURCE_LINE_RE = re.compile(r"^(\[\d+\])+\s*\S{0,40}$")
SOURCE_HEADING_RE = re.compile(
    r"^(#+\s*)?(\*\*)?(来源|参考来源|参考资料|引用来源)(\*\*)?[:：]?$"
)
SOURCE_PREFIX_RE = re.compile(r"^(\*\*)?(来源|参考来源|参考资料|引用来源)(\*\*)?[:：]")


def _clean_answer(answer: str) -> str:
    """移除模型自行追加的来源清单/尾注，仅保留正文。"""
    lines: list[str] = []
    for line in answer.splitlines():
        stripped = line.strip()
        if SOURCE_LINE_RE.match(stripped):
            continue
        if SOURCE_HEADING_RE.match(stripped):
            continue
        if SOURCE_PREFIX_RE.match(stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _filter_citations(answer: str, citations: list[dict]) -> tuple[str, list[dict]]:
    """只保留答案实际引用的来源，并按首次出现顺序重编号为 [1]、[2]…"""
    matches = CITATION_MARKER_RE.findall(answer)
    if not matches:
        return answer, []

    by_index = {item.get("index"): item for item in citations}
    mapping: dict[int, int] = {}
    filtered: list[dict] = []

    for raw in matches:
        old_index = int(raw)
        if old_index not in by_index or old_index in mapping:
            continue
        new_index = len(mapping) + 1
        mapping[old_index] = new_index
        item = dict(by_index[old_index])
        item["index"] = new_index
        filtered.append(item)

    def replace(match: re.Match) -> str:
        old_index = int(match.group(1))
        return f"[{mapping[old_index]}]" if old_index in mapping else ""

    cleaned = CITATION_MARKER_RE.sub(replace, answer)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, filtered


def _dedup_citations(items: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    result: list[dict] = []
    for item in items:
        key = (item.get("document_id"), item.get("chunk_index"))
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "index": item.get("index", 0),
                "document_id": item.get("document_id"),
                "document_name": item.get("document_name", ""),
                "chunk_index": item.get("chunk_index", 0),
                "content": (item.get("content") or "")[:300],
                "page_no": item.get("page_no"),
                "score": item.get("score"),
            }
        )
    return result


def _fallback_answer(db: Session, user: User, message: str) -> tuple[str, list[dict]]:
    text = message.strip()

    if "取消" in text:
        page = reservation_service.list_my_reservations(
            db, user, scope="upcoming", page=1, page_size=20
        )
        if not page.list:
            return "当前没有可取消的预约。", []
        lines = [
            f"- {item.room_name} {_fmt_time(item.start_time)}-{_fmt_time(item.end_time)}"
            f"（{item.title}，编号 {item.id}）"
            for item in page.list
        ]
        return (
            "当前未启用大模型，以下是你即将开始的预约，可前往「我的预约」取消：\n"
            + "\n".join(lines),
            [],
        )

    if "我的预约" in text or (
        "我" in text
        and "预约" in text
        and any(keyword in text for keyword in ("哪些", "多少", "记录", "查询"))
    ):
        page = reservation_service.list_my_reservations(
            db, user, scope="upcoming", page=1, page_size=20
        )
        if not page.list:
            return "你当前没有即将开始的预约。", []
        lines = [
            f"- {item.room_name} {_fmt_time(item.start_time)}-{_fmt_time(item.end_time)}"
            f"（{item.title}）"
            for item in page.list
        ]
        return "你的预约：\n" + "\n".join(lines), []

    if "会议" in text or "预约" in text:
        board = room_service.get_board(db, None, user)
        lines = []
        for room in board.rooms:
            occupied = "、".join(
                f"{_fmt_hm(item.start_time)}-{_fmt_hm(item.end_time)}"
                for item in room.reservations
            )
            lines.append(
                f"- {room.name}（{room.capacity} 人）：{occupied or '全天空闲'}"
            )
        return (
            f"{board.date} 会议室情况：\n" + "\n".join(lines),
            [],
        )

    try:
        items = knowledge_service.search_knowledge(db, text, top_k=3)
    except Exception:
        logger.exception("知识库检索失败")
        items = []
    if items:
        body = "\n\n".join(
            f"[{index}] {item['document_name']}：{item['content'][:300]}"
            for index, item in enumerate(items, start=1)
        )
        return (
            "当前未启用大模型，以下是知识库中的相关内容：\n\n" + body,
            items,
        )

    return (
        "当前未启用大模型，暂时无法理解这个问题。请配置 LLM_KEY，或尝试询问会议室、预约、员工手册等问题。",
        [],
    )


def stream_chat(
    user_id: int, session_id: int | None, message: str
) -> Generator[str, None, None]:
    """SSE 生成器：使用独立数据库会话，避免流式响应期间会话被关闭。"""
    db = SessionLocal()
    try:
        user = (
            db.query(User)
            .options(joinedload(User.roles).joinedload(Role.menus))
            .filter(User.id == user_id)
            .first()
        )
        if user is None:
            yield _sse("error", {"message": "用户不存在"})
            return

        if session_id is not None:
            session = _get_session(db, user_id, session_id)
        else:
            title = message.strip()[:30] or "新对话"
            session = ChatSession(user_id=user_id, title=title)
            db.add(session)
            db.commit()
            db.refresh(session)

        _save_message(db, session, "user", message)
        yield _sse("meta", {"session_id": session.id})

        if not llm_client.is_configured():
            fallback, fallback_citations = _fallback_answer(db, user, message)
            for index, item in enumerate(fallback_citations, start=1):
                item["index"] = index
            answer, citations = _filter_citations(
                _clean_answer(fallback), fallback_citations
            )
            if not answer:
                answer = fallback
            citations = _dedup_citations(citations)
            saved = _save_message(
                db,
                session,
                "assistant",
                answer,
                citations=citations or None,
            )
            yield _sse("delta", {"content": fallback})
            for citation in citations:
                yield _sse("citation", citation)
            yield _sse(
                "done",
                {
                    "message_id": saved.id,
                    "session_id": session.id,
                    "usage": {},
                    "answer": answer,
                },
            )
            return

        config = _run_config(session.id)
        graph = _build_chat_graph(db, user, session)

        # 上一轮还有未确认的操作时，视为放弃：作废旧 token 并清空挂起的线程状态
        snapshot = graph.get_state(config)
        if snapshot.next:
            _expire_pending_actions(db, session.id)
            try:
                get_checkpointer().delete_thread(_thread_id(session.id))
            except Exception:
                logger.warning("清理线程状态失败", exc_info=True)

        state: AgentState = {
            "messages": [{"role": "user", "content": message}],
            "answer": "",
            "citations": [],
            "tool_calls": [],
            "write_calls": [],
            "last_content": "",
            "pending": None,
            "usage": {},
            "rounds": 0,
        }
        streamed_any = False
        completed = False

        try:
            for event in graph.stream(state, config, stream_mode="custom"):
                if not isinstance(event, dict):
                    continue
                event_name = event.get("event")
                data = event.get("data", {})
                if event_name == "delta":
                    streamed_any = True
                if event_name == "done":
                    completed = True
                if event_name:
                    yield _sse(event_name, data)

            if not completed:
                snapshot = graph.get_state(config)
                if not snapshot.next:
                    raise RuntimeError("对话图未正常结束")
                # 停在 interrupt 上是正常情况：等待用户确认，前端已收到 action 事件
                return
        except Exception:
            if completed:
                logger.exception("对话图结束后发生异常")
                return
            logger.exception("LangGraph 对话失败，切换本地指令模式")
            fallback, fallback_citations = _fallback_answer(db, user, message)
            for index, item in enumerate(fallback_citations, start=1):
                item["index"] = index
            prefix = (
                "\n\n[模型输出中断，已切换本地结果]\n\n"
                if streamed_any
                else "模型服务暂时不可用，已切换为本地指令模式。\n\n"
            )
            raw_answer = prefix + fallback
            answer, citations = _filter_citations(
                _clean_answer(raw_answer), fallback_citations
            )
            if not answer:
                answer = raw_answer
            citations = _dedup_citations(citations)
            saved = _save_message(
                db,
                session,
                "assistant",
                answer,
                citations=citations or None,
            )
            yield _sse("delta", {"content": raw_answer})
            for citation in citations:
                yield _sse("citation", citation)
            yield _sse(
                "done",
                {
                    "message_id": saved.id,
                    "session_id": session.id,
                    "usage": {},
                    "answer": answer,
                },
            )
    except BusinessException as exc:
        yield _sse("error", {"message": exc.message})
    except Exception:
        logger.exception("智能对话处理失败")
        yield _sse("error", {"message": "智能助手暂时不可用，请稍后再试"})
    finally:
        db.close()


def confirm_action_stream(
    user_id: int, token: str, approve: bool
) -> Generator[str, None, None]:
    """确认/拒绝待执行操作：从 checkpoint 恢复同一个对话线程并继续流式输出。

    写操作在图内执行，成功或失败都会作为 tool 结果回喂模型，
    因此用户可以拿到模型生成的说明，而不是写死的文案。
    """
    db = SessionLocal()
    claimed = False
    try:
        action = _claim_action(db, user_id, token, approve)
        claimed = True

        user = (
            db.query(User)
            .options(joinedload(User.roles).joinedload(Role.menus))
            .filter(User.id == user_id)
            .first()
        )
        if user is None:
            yield _sse("error", {"message": "用户不存在"})
            return

        session = _get_session(db, user_id, action.session_id)
        config = _run_config(session.id)
        graph = _build_chat_graph(db, user, session)
        yield _sse("meta", {"session_id": session.id})

        completed = False
        for event in graph.stream(
            Command(resume={"approve": approve, "token": token}),
            config,
            stream_mode="custom",
        ):
            if not isinstance(event, dict):
                continue
            event_name = event.get("event")
            data = event.get("data", {})
            if event_name == "done":
                completed = True
            if event_name:
                yield _sse(event_name, data)

        if not completed:
            if not graph.get_state(config).next:
                yield _sse("error", {"message": "操作未能完成，请重新发起"})
    except BusinessException as exc:
        if claimed and approve:
            _update_action_status(db, token, "failed")
        yield _sse("error", {"message": exc.message})
    except Exception:
        logger.exception("确认操作失败")
        if claimed and approve:
            _update_action_status(db, token, "failed")
        yield _sse("error", {"message": "操作失败，请稍后重试"})
    finally:
        db.close()
