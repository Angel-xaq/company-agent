from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.user import router as user_router
from app.api.room import router as room_router
from app.api.reservation import router as reservation_router
from app.api.knowledge import router as knowledge_router
from app.api.chat import router as chat_router

api = APIRouter(prefix="/api")
api.include_router(auth_router)
api.include_router(user_router)
api.include_router(room_router)
api.include_router(reservation_router)
api.include_router(knowledge_router)
api.include_router(chat_router)


