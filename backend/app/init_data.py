"""初始化 RBAC 基础数据：默认角色、基础菜单与管理员账号。

在 backend 目录下执行：

    python -m app.init_data

脚本是幂等的：已存在的角色/菜单不会重复创建，重复执行不会报错。
"""

from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

import app.models  # noqa: F401  注册所有 ORM 模型
from app.config import settings
from app.core.constants import (
    DOC_PENDING,
    PERM_BOOKING_MANAGE,
    PERM_BOOKING_VIEW,
    PERM_CHAT_USE,
    PERM_KB_MANAGE,
    PERM_KB_VIEW,
    PERM_ROOM_BOOK,
    PERM_ROOM_VIEW,
    PERM_USER_MANAGE,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
)
from app.database import Base, SessionLocal, engine
from app.models.knowledge import KnowledgeDocument
from app.models.meeting_room import MeetingRoom
from app.models.menu import Menu
from app.models.role import Role
from app.models.user import User
from app.utils.password import hash_password

DEFAULT_ADMIN = {
    "username": "admin",
    "password": "admin123",
    "name": "系统管理员",
}


def get_or_create_role(
    db: Session, code: str, name: str, remark: str | None = None
) -> Role:
    """按 code 获取角色，不存在则创建。"""
    role = db.query(Role).filter(Role.code == code).first()
    if role:
        role.name = name
        role.status = 1
        if remark is not None:
            role.remark = remark
        return role

    role = Role(code=code, name=name, status=1, remark=remark)
    db.add(role)
    db.flush()
    print(f"[角色] 创建 {name}（{code}）")
    return role


def get_or_create_menu(
    db: Session,
    name: str,
    *,
    type_: str = "menu",
    path: str | None = None,
    icon: str | None = None,
    permission: str | None = None,
    sort: int = 0,
    parent: Menu | None = None,
) -> Menu:
    """按名称（同一父级下）获取菜单，不存在则创建。"""
    query = db.query(Menu).filter(Menu.name == name)
    if parent is None:
        query = query.filter(Menu.parent_id.is_(None))
    else:
        query = query.filter(Menu.parent_id == parent.id)

    menu = query.first()
    if menu:
        return menu

    menu = Menu(
        name=name,
        type=type_,
        path=path,
        icon=icon,
        permission=permission,
        sort=sort,
        visible=1,
        status=1,
    )
    if parent is not None:
        menu.parent = parent
    db.add(menu)
    db.flush()
    print(f"[菜单] 创建 {name}（{path or type_}）")
    return menu


def upsert_menu(
    db: Session,
    name: str,
    *,
    type_: str = "menu",
    path: str | None = None,
    icon: str | None = None,
    permission: str | None = None,
    sort: int = 0,
    parent: Menu | None = None,
    visible: int = 1,
) -> Menu:
    """按权限码 / 路径 / 名称幂等写入菜单，并同步展示字段。"""
    query = db.query(Menu)
    if permission:
        query = query.filter(Menu.permission == permission)
    elif path:
        query = query.filter(Menu.path == path)
    else:
        query = query.filter(Menu.name == name)
        if parent is None:
            query = query.filter(Menu.parent_id.is_(None))
        else:
            query = query.filter(Menu.parent_id == parent.id)

    menu = query.first()
    if menu is None:
        menu = Menu(name=name, type=type_, path=path, permission=permission)
        if parent is not None:
            menu.parent = parent
        db.add(menu)

    menu.name = name
    menu.type = type_
    menu.path = path
    menu.icon = icon
    menu.permission = permission
    menu.sort = sort
    menu.visible = visible
    menu.status = 1
    if parent is not None:
        menu.parent = parent
    db.flush()
    return menu


def seed_rooms(db: Session) -> None:
    """幂等写入会议室基础数据。"""
    seeds = [
        {
            "name": "3F-A 大会议室",
            "location": "3 楼东侧",
            "capacity": 12,
            "equipment": ["投影", "白板", "视频会议"],
            "description": "适合部门会议与客户接待",
            "sort": 1,
        },
        {
            "name": "3F-B 小会议室",
            "location": "3 楼西侧",
            "capacity": 6,
            "equipment": ["白板", "电视"],
            "description": "适合小组讨论",
            "sort": 2,
        },
        {
            "name": "5F-A 董事会议室",
            "location": "5 楼",
            "capacity": 16,
            "equipment": ["投影", "视频会议", "电话会议"],
            "description": "适合管理层会议",
            "sort": 3,
        },
        {
            "name": "2F 培训室",
            "location": "2 楼",
            "capacity": 30,
            "equipment": ["投影", "音响", "白板"],
            "description": "适合培训与分享会",
            "sort": 4,
        },
    ]
    for item in seeds:
        room = (
            db.query(MeetingRoom)
            .filter(MeetingRoom.name == item["name"])
            .first()
        )
        if room is None:
            db.add(MeetingRoom(**item))
            continue
        for field, value in item.items():
            setattr(room, field, value)
    db.flush()


def seed_knowledge(db: Session, admin_user: User) -> None:
    """写入员工手册与 IT 指南样例文档（等待管理员建立索引）。"""
    seed_dir = Path(__file__).resolve().parent / "seed_docs"
    target_dir = Path(settings.UPLOAD_DIR) / "knowledge"
    target_dir.mkdir(parents=True, exist_ok=True)

    seeds = [
        ("员工手册", "employee_handbook.md", "handbook"),
        ("IT 指南", "it_guide.md", "it"),
    ]
    for name, filename, category in seeds:
        exists = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.name == name)
            .first()
        )
        if exists:
            continue

        source = seed_dir / filename
        if not source.exists():
            continue

        content = source.read_bytes()
        ext = source.suffix.lower().lstrip(".")
        stored_path = target_dir / f"{uuid4().hex}.{ext}"
        stored_path.write_bytes(content)
        db.add(
            KnowledgeDocument(
                name=name,
                category=category,
                filename=filename,
                file_path=str(stored_path),
                file_type=ext,
                file_size=len(content),
                status=DOC_PENDING,
                chunk_count=0,
                uploaded_by=admin_user.id,
                error_message="等待建立索引（首次索引会下载 bge-m3 模型）",
            )
        )
    db.flush()


def seed(db: Session) -> None:
    """写入默认角色、菜单，并保证 admin 账号可用。"""
    admin_role = get_or_create_role(db, ROLE_ADMIN, "管理员", "拥有全部权限")
    employee_role = get_or_create_role(db, ROLE_EMPLOYEE, "员工", "默认角色")

    # 兼容历史角色：boss / student / teacher / manager 统一并入员工后删除
    for legacy_code in ("boss", "student", "teacher", "manager"):
        legacy = db.query(Role).filter(Role.code == legacy_code).first()
        if not legacy or legacy.id in (admin_role.id, employee_role.id):
            continue
        for legacy_user in list(legacy.users):
            if employee_role not in legacy_user.roles:
                legacy_user.roles.append(employee_role)
        legacy.users.clear()
        legacy.menus.clear()
        db.delete(legacy)
    db.flush()

    chat = upsert_menu(
        db,
        "智能对话",
        type_="menu",
        path="/manager/chat",
        icon="ChatDotRound",
        permission=PERM_CHAT_USE,
        sort=1,
    )
    rooms = upsert_menu(
        db,
        "会议室看板",
        type_="menu",
        path="/manager/rooms",
        icon="OfficeBuilding",
        permission=PERM_ROOM_VIEW,
        sort=2,
    )
    bookings = upsert_menu(
        db,
        "我的预约",
        type_="menu",
        path="/manager/bookings",
        icon="Tickets",
        permission=PERM_BOOKING_VIEW,
        sort=3,
    )
    knowledge = upsert_menu(
        db,
        "知识库",
        type_="menu",
        path="/manager/knowledge",
        icon="DocumentChecked",
        permission=PERM_KB_VIEW,
        sort=4,
    )

    # 按钮级权限：不参与侧边栏展示
    room_book = upsert_menu(
        db,
        "会议室预约",
        type_="button",
        permission=PERM_ROOM_BOOK,
        sort=2,
        parent=rooms,
        visible=0,
    )
    booking_manage = upsert_menu(
        db,
        "预约管理",
        type_="button",
        permission=PERM_BOOKING_MANAGE,
        sort=3,
        parent=bookings,
        visible=0,
    )
    kb_manage = upsert_menu(
        db,
        "知识库管理",
        type_="button",
        permission=PERM_KB_MANAGE,
        sort=1,
        parent=knowledge,
        visible=0,
    )
    user_manage = upsert_menu(
        db,
        "用户管理",
        type_="button",
        permission=PERM_USER_MANAGE,
        sort=1,
        visible=0,
    )

    # 侧边栏所有角色一致；权限差异只体现在按钮与接口
    common_menus = [chat, rooms, room_book, bookings, knowledge]
    employee_role.menus = common_menus
    admin_role.menus = [*common_menus, kb_manage, booking_manage, user_manage]

    admin = db.query(User).filter(User.username == DEFAULT_ADMIN["username"]).first()
    if admin is None:
        admin = User(
            username=DEFAULT_ADMIN["username"],
            password=hash_password(DEFAULT_ADMIN["password"]),
            name=DEFAULT_ADMIN["name"],
            status=1,
        )
        db.add(admin)
        db.flush()
        print(
            f"[用户] 创建管理员 {DEFAULT_ADMIN['username']} / {DEFAULT_ADMIN['password']}（请尽快修改密码）"
        )

    if not any(role.code == ROLE_ADMIN for role in admin.roles):
        admin.roles.append(admin_role)

    seed_rooms(db)
    seed_knowledge(db, admin)


def main() -> None:
    """建表并写入初始化数据。"""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("RBAC 基础数据初始化完成。")


if __name__ == "__main__":
    main()
