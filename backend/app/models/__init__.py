"""统一注册所有 ORM 模型，确保 create_all 能建出全部表"""

from app.models.role import Role, role_menus, user_roles
from app.models.user import User
from app.models.menu import Menu
from app.models.meeting_room import MeetingRoom
from app.models.reservation import Reservation
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.chat import ChatMessage, ChatPendingAction, ChatSession
from app.models.refresh_token import RefreshToken

__all__ = [
    "Role",
    "User",
    "Menu",
    "MeetingRoom",
    "Reservation",
    "KnowledgeDocument",
    "KnowledgeChunk",
    "ChatSession",
    "ChatMessage",
    "ChatPendingAction",
    "RefreshToken",
    "user_roles",
    "role_menus",
]

