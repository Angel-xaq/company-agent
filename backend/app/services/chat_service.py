import json
import logging
import re
import secrets
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any, Generator, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.config import settings
from app.database import SessionLocal
from app.models.chat import ChatMessage, ChatPendingAction, ChatSession
from app.models.meeting_room import MeetingRoom
from app.models.reservation import Reservation
from app.models.role import Role
from app.models.user import User
from app.schemas.chat import ChatMessageResponse, ChatSessionResponse
from app.schemas.reservation import ReservationCreateRequest
from app.services import (
    knowledge_service,
    llm_client,
    reservation_service,
    room_service,
)
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
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _parse_args(raw: str | None) -> dict:
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


def create_session(db: Session, user_id: int, title: str = "新对话") -> ChatSessionResponse:
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
            content=_clean_answer(item.content) if item.role == "assistant" else item.content,
            citations=item.citations,
            create_time=item.create_time,
        )
        for item in messages
    ]


def delete_session(db: Session, user_id: int, session_id: int) -> None:
    session = _get_session(db, user_id, session_id)
    db.delete(session)
    db.commit()


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
    return [
        {"role": item.role, "content": item.content}
        for item in reversed(rows)
    ]


def _system_prompt(user: User) -> str:
    return f"""你是公司智能助手，负责回答员工问题并协助会议室预约。
当前时间：{now_local().strftime('%Y-%m-%d %H:%M')}（{settings.TIMEZONE}）
当前用户：{user.name}
预约规则：营业时间 {settings.BUSINESS_START}-{settings.BUSINESS_END}，{settings.SLOT_MINUTES} 分钟粒度，单次最长 {settings.BOOKING_MAX_HOURS} 小时。

要求：
1. 涉及会议室空闲情况、预约记录时必须调用工具，不要编造房间、时间或预约编号。
2. 创建或取消预约时调用对应工具；系统会要求用户二次确认，不要声称已经完成。
3. 制度、流程类问题先调用 search_knowledge。检索结果每条带 citation_index；只在相关句子末尾使用 [citation_index]（如 [1]），只引用实际使用的条目，不要引用未使用的检索结果。
4. 不要输出来源清单，不要写“来源：xxx”，不要单独输出“[1] 文档名”这类尾注；来源由前端根据上标展示。
5. 未检索到相关内容时明确说明，不要编造制度条款。
6. 使用中文简洁回答，必要时列出要点。"""


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


def _action_summary(db: Session, tool_name: str, params: dict) -> str:
    if tool_name == "create_reservation":
        room_id = params.get("room_id")
        room = (
            db.query(MeetingRoom).filter(MeetingRoom.id == room_id).first()
            if room_id
            else None
        )
        return (
            f"预约 {room.name if room else room_id}，"
            f"{params.get('start_time', '?')} 至 {params.get('end_time', '?')}，"
            f"主题：{params.get('title', '未填写')}"
        )
    if tool_name == "cancel_reservation":
        reservation_id = params.get("reservation_id")
        reservation = (
            db.query(Reservation)
            .options(joinedload(Reservation.room))
            .filter(Reservation.id == reservation_id)
            .first()
            if reservation_id
            else None
        )
        if reservation:
            return (
                f"取消预约 #{reservation.id}：{reservation.room.name} "
                f"{_fmt_time(reservation.start_time)}-{_fmt_time(reservation.end_time)}"
            )
        return f"取消预约 #{reservation_id}"
    return "待确认操作"


def _pending_prompt(tool_name: str) -> str:
    if tool_name == "create_reservation":
        return "已为您整理好预约信息，请确认后执行。"
    if tool_name == "cancel_reservation":
        return "请确认是否取消该预约。"
    return "请确认是否执行该操作。"


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


def _execute_read_tool(db: Session, user: User, name: str, args: dict) -> dict:
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
            result["available_room_ids"] = _filter_available(board, str(start), str(end))
        return result

    if name == "list_my_reservations":
        scope = args.get("scope") if args.get("scope") in ("upcoming", "history") else "upcoming"
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


class AgentState(TypedDict):
    messages: list[dict]
    answer: str
    citations: list[dict]
    tool_calls: list[dict]
    last_content: str
    pending: dict | None
    usage: dict
    rounds: int


def _build_chat_graph(db: Session, user: User, session: ChatSession):
    """构建单次对话的 LangGraph：agent → tools → agent → finalize。"""
    workflow = StateGraph(AgentState)

    def agent_node(state: AgentState) -> dict:
        writer = get_stream_writer()
        messages = list(state["messages"])
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
        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                }
            )

        return {
            "messages": messages,
            "answer": state.get("answer", "") + content,
            "tool_calls": tool_calls,
            "last_content": content,
            "usage": usage or state.get("usage", {}),
            "rounds": state.get("rounds", 0) + 1,
        }

    def tools_node(state: AgentState) -> dict:
        writer = get_stream_writer()
        messages = list(state["messages"])
        citations = list(state.get("citations", []))
        citation_by_key = {
            (item.get("document_id"), item.get("chunk_index")): item
            for item in citations
        }
        pending: dict | None = None
        answer_extra = ""

        for tool_call in state.get("tool_calls", []):
            name = tool_call["function"]["name"]
            args = _parse_args(tool_call["function"].get("arguments"))

            if name in WRITE_TOOLS:
                action = _create_pending_action(db, session, user, name, args)
                pending = {
                    "token": action.token,
                    "tool_name": action.tool_name,
                    "params": action.params,
                    "summary": _action_summary(db, action.tool_name, action.params),
                }
                if not state.get("last_content", "").strip():
                    prompt = _pending_prompt(name)
                    answer_extra += prompt
                    writer({"event": "delta", "data": {"content": prompt}})
                break

            try:
                result = _execute_read_tool(db, user, name, args)
            except Exception as exc:
                logger.warning("工具执行失败：%s", name, exc_info=True)
                result = {"error": str(exc)}

            if name == "search_knowledge":
                enriched: list[dict] = []
                for item in result.get("items", []):
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

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

        return {
            "messages": messages,
            "citations": citations,
            "tool_calls": [],
            "pending": pending,
            "answer": state.get("answer", "") + answer_extra,
        }

    def finalize_node(state: AgentState) -> dict:
        writer = get_stream_writer()
        raw_answer = state.get("answer", "").strip()
        answer, used = _filter_citations(
            _clean_answer(raw_answer), state.get("citations", [])
        )
        if not answer and state.get("pending") is None:
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

        pending = state.get("pending")
        if pending is not None:
            writer({"event": "action", "data": pending})

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

    def after_agent(state: AgentState) -> str:
        return "tools" if state.get("tool_calls") else "finalize"

    def after_tools(state: AgentState) -> str:
        if state.get("pending") is not None:
            return "finalize"
        if state.get("rounds", 0) >= 3:
            return "finalize"
        return "agent"

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent", after_agent, {"tools": "tools", "finalize": "finalize"}
    )
    workflow.add_conditional_edges(
        "tools", after_tools, {"agent": "agent", "finalize": "finalize"}
    )
    workflow.add_edge("finalize", END)
    return workflow.compile()


CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")
SOURCE_LINE_RE = re.compile(r"^(\[\d+\])+\s*\S{0,40}$")
SOURCE_HEADING_RE = re.compile(
    r"^(#+\s*)?(\*\*)?(来源|参考来源|参考资料|引用来源)(\*\*)?[:：]?$"
)
SOURCE_PREFIX_RE = re.compile(
    r"^(\*\*)?(来源|参考来源|参考资料|引用来源)(\*\*)?[:：]"
)


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


def _filter_citations(
    answer: str, citations: list[dict]
) -> tuple[str, list[dict]]:
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

        state: AgentState = {
            "messages": [
                {"role": "system", "content": _system_prompt(user)},
                *_history(db, session.id),
            ],
            "answer": "",
            "citations": [],
            "tool_calls": [],
            "last_content": "",
            "pending": None,
            "usage": {},
            "rounds": 0,
        }
        graph = _build_chat_graph(db, user, session)
        streamed_any = False
        completed = False

        try:
            for event in graph.stream(
                state,
                stream_mode="custom",
                config={"recursion_limit": 8},
            ):
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
                raise RuntimeError("对话图未正常结束")
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


def confirm_action(db: Session, user: User, token: str, approve: bool) -> str:
    action = (
        db.query(ChatPendingAction)
        .filter(
            ChatPendingAction.token == token,
            ChatPendingAction.user_id == user.id,
        )
        .first()
    )
    if action is None:
        raise BusinessException(message="操作不存在或已失效", code=404)
    if action.status != "pending":
        raise BusinessException(message="该操作已处理")
    if action.expire_at < now_local():
        action.status = "expired"
        db.commit()
        raise BusinessException(message="操作已过期，请重新发起")

    if not approve:
        action.status = "rejected"
        db.commit()
        _save_session_message(db, action.session_id, "已取消本次操作。")
        return "已取消本次操作"

    params = action.params or {}
    if action.tool_name == "create_reservation":
        try:
            payload = ReservationCreateRequest(
                title=params["title"],
                purpose=params.get("purpose"),
                attendees=params.get("attendees"),
                start_time=params["start_time"],
                end_time=params["end_time"],
            )
            room_id = int(params["room_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BusinessException(message="预约参数不完整或格式错误") from exc
        except Exception as exc:
            raise BusinessException(message="预约参数无效，请重新描述预约时间") from exc

        result = reservation_service.create_reservation(
            db, room_id, user, payload
        )

        action.status = "confirmed"
        db.commit()
        message = (
            f"预约成功：{result.room_name} "
            f"{_fmt_time(result.start_time)}-{_fmt_time(result.end_time)}，"
            f"主题「{result.title}」。"
        )
        _save_session_message(db, action.session_id, message)
        return message

    if action.tool_name == "cancel_reservation":
        try:
            reservation_id = int(params["reservation_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BusinessException(message="预约编号无效") from exc
        result = reservation_service.cancel_reservation(
            db, reservation_id, user, "通过智能助手取消"
        )
        action.status = "confirmed"
        db.commit()
        message = (
            f"已取消预约：{result.room_name} "
            f"{_fmt_time(result.start_time)}-{_fmt_time(result.end_time)}。"
        )
        _save_session_message(db, action.session_id, message)
        return message

    raise BusinessException(message="不支持的操作类型")
