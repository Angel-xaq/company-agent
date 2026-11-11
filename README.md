# company-agent 公司智能管理系统

一个前后端分离的公司智能管理系统，提供账号认证、基于角色的访问控制（RBAC）、智能对话、会议室预约与知识库等能力。

## 主要功能

- **智能对话**：基于 **LangGraph** 编排的 Agent，支持查询空会议室、预约/取消预约、查询我的预约、知识库问答；写操作需二次确认；回答支持 Markdown 与行内引用上标，采用 token 级 SSE 流式输出
- **会议室看板**：按日期展示会议室 × 时段占用情况，点击空闲时段直接预约，20 秒轮询同步
- **我的预约**：即将开始 / 历史记录，支持修改与取消
- **知识库**：员工查看文档列表；管理员上传、删除、重建索引；对话回答带来源引用
- **RBAC 权限**：仅 `admin` / `employee` 两个角色；侧边栏所有用户一致，知识库管理按钮与接口按 `kb:manage` 控制
- **账号认证**：账号密码登录、注册；Access Token 15 分钟、Refresh Token 7 天（HttpOnly Cookie），密码使用 bcrypt 加密存储
- **后台界面**：固定侧边栏、菜单折叠、头像下拉操作、登录态路由守卫
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
| 大模型   | DeepSeek OpenAI 兼容 API（`deepseek-flash`） |
| Agent 编排 | LangGraph（agent → tools → finalize 状态图） |
| 向量检索 | Chroma + `BAAI/bge-m3`（支持本地或 OpenAI 兼容 Embedding） |
| 文档解析 | pypdf、python-docx              |
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
│   │   ├── api/            # 认证、用户、会议室、预约、知识库、对话
│   │   ├── common/         # 统一响应、异常与异常处理器
│   │   ├── core/           # 角色、权限与状态常量
│   │   ├── dependencies/   # JWT 鉴权、角色/权限校验依赖
│   │   ├── models/         # User、Role、Menu、Room、Reservation、Knowledge、Chat
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── services/       # 业务逻辑、LLM、RAG、向量库封装
│   │   ├── seed_docs/      # 员工手册、IT 指南样例文档
│   │   ├── utils/          # JWT、密码哈希工具
│   │   ├── config.py       # 环境变量配置
│   │   ├── database.py     # 引擎、会话与 Base
│   │   ├── init_data.py    # RBAC / 会议室 / 样例文档初始化
│   │   └── main.py         # 应用入口
│   ├── requirements.txt
│   └── .env                # 本地配置
├── frontend/
│   ├── src/
│   │   ├── api/            # 接口封装（含 SSE 对话）
│   │   ├── components/     # 预约弹窗等通用组件
│   │   ├── hooks/          # 看板轮询等 Hook
│   │   ├── layouts/        # 后台布局（顶栏 + 固定侧边栏）
│   │   ├── router/         # 路由与登录态守卫
│   │   ├── store/          # 用户、权限状态
│   │   ├── styles/         # 全局样式
│   │   ├── types/          # TypeScript 类型定义
│   │   ├── utils/          # Axios 封装、本地存储、时间工具
│   │   └── views/          # 登录、对话、会议室、预约、知识库、修改密码
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
JWT_ACCESS_EXPIRE_MINUTES=15
JWT_REFRESH_EXPIRE_DAYS=7
REFRESH_COOKIE_NAME=refresh_token
COOKIE_SECURE=false

# 大模型（OpenAI 兼容，当前使用 deepseek-flash）
LLM_KEY=your-deepseek-key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-flash

# Embedding（OpenAI 兼容接口；local 模式需能访问 HuggingFace）
EMBEDDING_PROVIDER=openai
EMBEDDING_KEY=your-embedding-key
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024

# 向量库
VECTOR_STORE=chroma
CHROMA_DIR=./data/chroma

# 会议室预约
BUSINESS_START=09:30
BUSINESS_END=21:00
SLOT_MINUTES=30
BOOKING_MAX_HOURS=4
```

初始化基础数据（创建默认角色、菜单、管理员账号、4 间会议室与样例文档）：

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
> 默认管理员账号：`admin / admin123`，登录后请及时修改密码。
> 「员工手册」「IT 指南」样例文档初始为「待索引」，管理员在知识库页面点击「重建索引」后即可被检索（首次会下载 `BAAI/bge-m3` 模型）。

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 。

开发环境下，Vite 已将 `/api` 与 `/uploads` 代理到 `http://127.0.0.1:8000`，无需额外配置跨域。

## 页面说明

- 登录后默认进入「智能对话」，它同时是系统首页
- 侧边栏固定展示：智能对话、会议室看板、我的预约、知识库
- 修改密码不在侧边栏，通过右上角头像下拉菜单进入
- 个人信息页面与资料更新接口已移除
