"""初始化 RBAC 基础数据：默认角色、基础菜单与管理员账号。

在 backend 目录下执行：

    python -m app.init_data

脚本是幂等的：已存在的角色/菜单不会重复创建，重复执行不会报错。
"""

from sqlalchemy.orm import Session

import app.models  # noqa: F401  注册所有 ORM 模型
from app.database import Base, SessionLocal, engine
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


def seed(db: Session) -> None:
    """写入默认角色、菜单，并保证 admin 账号可用。"""
    roles = {
        "admin": get_or_create_role(db, "admin", "系统管理员", "拥有全部权限"),
        "teacher": get_or_create_role(db, "boss", "经理", "经理"),
        "student": get_or_create_role(db, "employee", "同学", "注册时默认绑定的角色"),
    }

    home = get_or_create_menu(
        db,
        "首页",
        type_="menu",
        path="/manager/home",
        icon="House",
        permission="dashboard:view",
        sort=1,
    )
    personal = get_or_create_menu(
        db,
        "个人中心",
        type_="dir",
        icon="User",
        sort=90,
    )
    profile = get_or_create_menu(
        db,
        "个人信息",
        type_="menu",
        path="/manager/profile",
        icon="User",
        permission="profile:view",
        sort=1,
        parent=personal,
    )
    password = get_or_create_menu(
        db,
        "修改密码",
        type_="menu",
        path="/manager/password",
        icon="Setting",
        permission="password:update",
        sort=2,
        parent=personal,
    )

    menus = [home, personal, profile, password]
    for role in roles.values():
        existing = {menu.id for menu in role.menus}
        for menu in menus:
            if menu.id not in existing:
                role.menus.append(menu)

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

    if not any(role.code == "admin" for role in admin.roles):
        admin.roles.append(roles["admin"])


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
