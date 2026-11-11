import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
import app.models  # noqa: F401 导入所有模型，确保表结构已注册到 Base.metadata
from app.api import api
from app.common.exceptions import (
    BusinessException,
    UnauthorizedException,
    business_exception_handler,
    unauthorized_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)
from app.services.checkpointer import init_checkpointer, shutdown_checkpointer
from app.services.chat_service import run_action_sweeper, sweep_stale_actions

logger = logging.getLogger(__name__)

origins = [item.strip() for item in settings.CORS_ORIGINS.split(",") if item.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 统一建表
    Base.metadata.create_all(bind=engine)
    # 预热 LangGraph checkpointer（postgres 后端会顺带建表）
    init_checkpointer()
    # 回收上一次进程异常退出时遗留的 executing 待确认操作
    try:
        sweep_stale_actions()
    except Exception:
        logger.warning("启动时回收待确认操作失败", exc_info=True)

    sweeper = asyncio.create_task(run_action_sweeper())
    try:
        yield
    finally:
        sweeper.cancel()
        shutdown_checkpointer()


app = FastAPI(
    lifespan=lifespan,
    exception_handlers={
        BusinessException: business_exception_handler,
        UnauthorizedException: unauthorized_exception_handler,
        HTTPException: http_exception_handler,
        RequestValidationError: validation_exception_handler,
        Exception: global_exception_handler,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api)


@app.get("/")
def root():
    return {"message": "company-agent API", "docs": "/docs"}
