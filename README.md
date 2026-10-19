# company-agent 公司智能管理系统

一个前后端分离的公司智能管理系统，提供账号认证、基于角色的访问控制（RBAC）、用户管理与个人中心等基础能力。

## 主要功能

- **账号认证**：账号密码登录、注册，JWT 无状态鉴权，密码使用 bcrypt 加密存储
- **RBAC 权限模型**：用户与角色多对多、角色与菜单多对多，支持多角色权限并集
- **后台界面**：动态侧边栏、菜单折叠、头像下拉操作、登录态与菜单权限路由守卫
- **统一响应与异常处理**：后端统一返回 `{ code, message, data }`，前端统一拦截提示与登录失效处理

## 技术栈

### 后端

| 分类     | 技术                            |
| -------- | ------------------------------- |
| 语言     | Python 3.10+                    |
| Web 框架 | FastAPI                         |
| ORM      | SQLAlchemy 2.0                  |
| 数据库   | PostgreSQL（psycopg 3 驱动）    |
| 数据校验 | Pydantic v2 / pydantic-settings |
| 认证     | PyJWT、bcrypt                   |
| 服务器   | Uvicorn                         |

### 前端

| 分类      | 技术           |
| --------- | -------------- |
| 框架      | React 18       |
| 语言      | TypeScript 5   |
| 构建工具  | Vite 8         |
| UI 组件库 | Ant Design 5   |
| 路由      | React Router 7 |
| 请求      | Axios          |

## 项目结构

```
company-agent/
├── backend/
│   ├── app/
│   │   ├── api/            # 接口路由（auth、user）
│   │   ├── common/         # 统一响应、异常与异常处理器
│   │   ├── dependencies/   # JWT 鉴权、角色/权限校验依赖
│   │   ├── models/         # User、Role、Menu ORM 模型
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── services/       # 登录注册、用户管理等业务逻辑
│   │   ├── utils/          # JWT、密码哈希工具
│   │   ├── config.py       # 环境变量配置
│   │   ├── database.py     # 引擎、会话与 Base
│   │   ├── init_data.py    # RBAC 初始化脚本
│   │   └── main.py         # 应用入口
│   ├── requirements.txt
│   └── .env                # 本地配置
├── frontend/
│   ├── src/
│   │   ├── api/            # 接口封装
│   │   ├── layouts/        # 后台布局（顶栏 + 侧边菜单）
│   │   ├── router/         # 路由与登录/菜单权限守卫
│   │   ├── store/          # 用户、菜单、权限状态
│   │   ├── styles/         # 全局样式
│   │   ├── types/          # TypeScript 类型定义
│   │   ├── utils/          # Axios 封装、本地存储工具
│   │   └── views/          # 登录、注册、首页、个人信息等页面
│   ├── package.json
│   └── vite.config.ts
├── .gitignore
├── package.json
└── README.md
```

## 快速开始

### 环境要求

- Python 3.10 及以上（建议 3.11 / 3.12）
- Node.js `^22.18.0` 或 `>=24.12.0`
- PostgreSQL 数据库

### 1. 启动后端

```bash
cd backend
```

创建并激活虚拟环境：

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

创建数据库（示例）：

```sql
CREATE DATABASE company_agent;
```

在 `backend` 目录下创建 `.env` 文件：

```ini
# PostgreSQL 连接串，按实际用户名、密码、端口修改
DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5432/company_agent

# JWT 配置
JWT_SECRET_KEY=please-replace-with-a-random-secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=24
```

初始化基础数据（创建默认角色、基础菜单和管理员账号）：

```bash
python -m app.init_data
```

启动服务：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 服务地址：http://127.0.0.1:8000
- 接口文档：http://127.0.0.1:8000/docs

> 应用启动时会自动创建缺失的数据表；`init_data.py` 只负责写入业务初始化数据，可重复执行。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 。

开发环境下，Vite 已将 `/api` 与 `/uploads` 代理到 `http://127.0.0.1:8000`，无需额外配置跨域。
