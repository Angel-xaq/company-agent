"""LangGraph checkpointer 单例。

一个对话会话对应一个 thread，图在每个节点之后把 state 写入 checkpoint，
用于多轮上下文、断点续跑以及 interrupt（人工确认）的挂起与恢复。

后端选择由 settings.CHECKPOINT_BACKEND 决定：
- memory：InMemorySaver，进程重启后线程状态丢失（默认，开箱即用）
- postgres：PostgresSaver，写入现有 PostgreSQL，需要安装
  langgraph-checkpoint-postgres
"""

import logging
from threading import Lock
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_lock = Lock()
_saver: Any = None
_manager: Any = None


def _memory_saver() -> Any:
    from langgraph.checkpoint.memory import InMemorySaver

    logger.info("LangGraph checkpointer 使用内存实现（进程重启后线程状态会丢失）")
    return InMemorySaver()


def get_checkpointer() -> Any:
    """返回全局唯一的 checkpointer，进程内只初始化一次。"""
    global _saver, _manager
    if _saver is not None:
        return _saver

    with _lock:
        if _saver is not None:
            return _saver

        backend = (settings.CHECKPOINT_BACKEND or "memory").strip().lower()
        if backend != "postgres":
            _saver = _memory_saver()
            return _saver

        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            dsn = settings.CHECKPOINT_DSN or settings.DATABASE_URL
            manager = PostgresSaver.from_conn_string(dsn)
            saver = manager.__enter__()
            saver.setup()
            _manager = manager
            _saver = saver
            logger.info("LangGraph checkpointer 使用 PostgreSQL")
        except Exception:
            logger.warning(
                "PostgreSQL checkpointer 初始化失败，回退内存实现", exc_info=True
            )
            _saver = _memory_saver()

        return _saver


def init_checkpointer() -> None:
    """应用启动时预热，避免首个请求才建表。"""
    get_checkpointer()


def shutdown_checkpointer() -> None:
    global _saver, _manager
    with _lock:
        if _manager is not None:
            try:
                _manager.__exit__(None, None, None)
            except Exception:
                logger.warning("关闭 PostgreSQL checkpointer 失败", exc_info=True)
        _manager = None
        _saver = None
