from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from app.database import Base, engine
import app.models  # noqa: F401 导入所有模型，确保表结构已注册到 Base.metadata
from app.api import api
from app.common.exceptions import (
    BusinessException,
    business_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    global_exception_handler,
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 统一建表
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    lifespan=lifespan,
    exception_handlers={
        BusinessException: business_exception_handler,
        HTTPException: http_exception_handler,
        RequestValidationError: validation_exception_handler,
        Exception: global_exception_handler,
    },
)
app.include_router(api)


@app.get("/")
def root():
    return {"message": "FastAPI..."}
