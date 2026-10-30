"""角色、权限与业务状态常量，避免魔法字符串散落各处。"""

# 角色
ROLE_ADMIN = "admin"
ROLE_EMPLOYEE = "employee"
DEFAULT_ROLE_CODE = ROLE_EMPLOYEE

# 权限码
PERM_DASHBOARD_VIEW = "dashboard:view"
PERM_PROFILE_VIEW = "profile:view"
PERM_PASSWORD_UPDATE = "password:update"
PERM_CHAT_USE = "chat:use"
PERM_ROOM_VIEW = "room:view"
PERM_ROOM_BOOK = "room:book"
PERM_BOOKING_VIEW = "booking:view"
PERM_BOOKING_MANAGE = "booking:manage"
PERM_KB_VIEW = "kb:view"
PERM_KB_MANAGE = "kb:manage"
PERM_USER_MANAGE = "user:manage"

# 预约状态
RESERVATION_CONFIRMED = "confirmed"
RESERVATION_CANCELLED = "cancelled"

# 知识库文档状态
DOC_PENDING = "pending"
DOC_PROCESSING = "processing"
DOC_READY = "ready"
DOC_FAILED = "failed"
