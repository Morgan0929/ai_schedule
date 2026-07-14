# AI Schedule Agent（日程智能助手）— 项目蓝图

> 本文档为 AI 助手的核心上下文文件，每次回答前必须阅读。包含完整的数据栈、架构、目标、框架定义。

---

## 一、项目概述

**项目名称**：AI Schedule Agent（日程智能助手）  
**项目根目录**：`D:/AIagent日程规划/`  
**项目结构**：`backend/` (Python AI后端) + `mobile/` (Flutter手机App) + `venv/` (Python虚拟环境)
**代码仓库**：https://gitee.com/<GITEE_USERNAME>/ai-schedule-management  
**项目类型**：Python AI Agent + 日程管理系统 + 数据采集平台 + 移动端应用

### 核心业务场景
本项目是一个 **AI Agent 日程管理系统**，核心特点是 **AI 自动感知冲突、协调决策、管理时间线**，而非简单的 CRUD 日历应用。

### 核心能力
| 能力 | 描述 |
|------|------|
| 爬虫获取外部数据 | 自动采集会议、航班、天气等外部信息 |
| 自动生成时间线 | 将零散任务整理为可视化时间线 |
| AI 对话管理行程 | 自然语言交互，Agent 理解意图并操作日程 |
| AI 冲突检测 | 多任务时间重叠自动发现 |
| AI 协调决策 | 冲突时给出多方案，用户选择或 AI 自动决策 |
| 手机 APP 使用 | Flutter 跨平台移动端 |

### 典型交互场景

```
用户：下周帮我安排上海出差

AI：已发现：
    1. 3月10日 北京客户会议
    2. 3月11日 上海出差
    3. 3月12日 产品发布会

存在冲突：
    上海出差与产品发布会时间重叠

解决方案：
    方案A：提前一天飞上海
    方案B：线上参加发布会
    方案C：委托张三代为出席
```

---

## 二、数据栈 (Data Stack)

| 层级 | 技术 | 用途 |
|------|------|------|
| 语言 | Python 3.11+ | 后端核心语言（从 Java 转型） |
| 后端框架 | FastAPI | 类似 Spring Boot，类型注解完整，AI 生态最好 |
| 数据验证 | Pydantic v2 | 请求/响应模型验证，类似 Java Bean Validation |
| ORM | SQLAlchemy 2.0 | 异步数据库操作 |
| 关系数据库 | PostgreSQL 16 | 用户、行程、时间线、AI 日志、Agent 状态、爬虫数据 |
| 缓存/队列 | Redis 7.x | 缓存、会话、任务队列、消息队列 |
| 向量数据库 | Qdrant | RAG 知识库（比 Milvus 简单） |
| 嵌入模型 | BGE-M3 | 中文嵌入向量生成 |
| LLM | DeepSeek V4 / DeepSeek R1 | 成本低、中文强、API 便宜 |
| Agent 框架 | LangGraph | 任务编排、状态图、工具调用（最值得学） |
| 爬虫 | requests + BeautifulSoup4 + Playwright | 4 个爬虫: weather(httpx) / news(BS4+lxml解析HTML) / calendar(httpx+离线) / dynamic(Playwright渲染JS) |
| 定时任务 | APScheduler | 定时自动采集数据 |
| 语音 | Whisper（输入） + CosyVoice（输出） | 后期升级语音交互 |
| 移动端 | Flutter | 一套代码 Android + iOS |
| 容器化 | Docker + Docker Compose | 全部容器化部署 |
| 反向代理 | Nginx | 生产环境前端 |

---

## 三、架构 (Architecture)

### 3.1 微服务拆分（企业级标准）

```
D:/AIagent日程规划/
├── venv/                          # Python 3.12 虚拟环境
├── .env / .env.example            # 环境变量 (API Key等)
├── .gitignore
│
├── backend/                       # Python AI 后端
│   ├── CLAUDE.md                  # ← 本文件（项目核心上下文）
│   ├── README.md
│   ├── docker-compose.yml
│   ├── requirements.txt (各服务独立)
│   │
│   ├── common/                    # 公共模块
│   │   ├── config.py / database.py / exceptions.py
│   │   ├── schemas/               # Pydantic 数据验证模型
│   │   └── utils/                 # JWT / bcrypt
│   │
│   ├── app_service/     8000      # API 网关 & 用户认证
│   ├── agent_service/   8002      # AI Agent (LangGraph + DeepSeek)
│   ├── timeline_service/ 8003     # 时间线 & 冲突检测
│   ├── crawler_service/ 8001      # 爬虫数据采集
│   ├── rag_service/     8004      # RAG 知识库
│   └── personal/                  # 本地个人脚本(不提交)
│
└── mobile/                        # Flutter 手机 App
    ├── lib/                       # Dart 源码
    ├── android/ / ios/
    └── pubspec.yaml
```

> **注意**：服务目录使用下划线（`app_service`）而非连字符，因为 Python 无法从含连字符的目录 import 包。
> 运行方式：从项目根目录 `python backend/app_service/main.py`

### 3.2 系统架构图

```
  ┌──────────┐     HTTP/WebSocket     ┌──────────────────────────┐
  │  Flutter  │ ◄──────────────────► │  Python AI 后端           │
  │  手机 App │                       │  (backend/)              │
  │ (mobile/) │                       │                          │
  └──────────┘                       │  ┌────────────────────┐  │
                                     │  │ app_service :8000  │  │
                                     │  │ agent_service:8002 │  │
                                     │  │ timeline_svc :8003 │  │
                                     │  │ crawler_svc  :8001 │  │
                                     │  │ rag_service  :8004 │  │
                                     │  └────────┬───────────┘  │
                                     │           │              │
                                     │  ┌────────▼───────────┐  │
                                     │  │ PostgreSQL 16       │  │
                                     │  │ Redis 7             │  │
                                     │  │ Qdrant (向量数据库)  │  │
                                     │  └────────────────────┘  │
                                     └──────────────────────────┘

  手机只是客户端 — AI/爬虫/数据库全部在后端运行
```

### 3.3 分层架构（以 agent-service 为例）

```
┌──────────────────────────────────────────┐
│            FastAPI Router 层             │  ← REST API 入口
├──────────────────────────────────────────┤
│            LangGraph StateGraph          │  ← Agent 编排引擎
├──────────────────────────────────────────┤
│         Tools / Function Calling         │  ← 工具调用层
├──────────────────────────────────────────┤
│            LLM Client 层                 │  ← DeepSeek API 封装
├──────────────────────────────────────────┤
│         Repository / Model 层            │  ← 数据访问 (SQLAlchemy)
├──────────────────────────────────────────┤
│         Infrastructure 层                │  ← Redis、Qdrant、外部服务调用
└──────────────────────────────────────────┘
```

### 3.4 Agent 工作流（LangGraph 状态图）

```
用户输入
    │
    ▼
┌──────────┐   ┌─────────────────────────┐
│ Planner  │──►│ AgentTracer (AI Trace)  │  ← 全程记录每一步
└────┬─────┘   │ 记录: 输入/输出/耗时/成功 │
     │         └─────────────────────────┘
     ▼
┌──────────────┐
│ 调用工具      │  ← 查询日历 / 创建任务 / 查天气
└────┬─────────┘
     │
     ▼
┌──────────────┐
│ 冲突检测      │  ← if task1.end > task2.start → 冲突
└────┬─────────┘
     │
     ▼
┌──────────────┐
│ AI 协调决策   │  ← 生成 A/B/C 多方案 + 推荐最佳
└────┬─────────┘
     │
     ▼
┌──────────────┐
│ 生成回复      │  ← 格式化输出给用户
└──────────────┘
     │
     ▼
  AgentTracer.finish()  ← 持久化到 PostgreSQL agent_session 表
```

Trace 输出示例:
```
[Trace:a1b2c3] [Plan] planner      [OK] 9349ms → intent: CREATE_TASK
[Trace:a1b2c3] [Tool] tools        [OK] 9349ms → tasks_created: [1]
[Trace:a1b2c3] [Reply] reply        [OK] 9349ms
[Trace:a1b2c3] 会话结束 — 3步 耗时9349ms OK
```

---

## 四、目标 (Goals)

### 4.1 总体目标
构建一个接近真实 AI Agent 产品架构的项目，覆盖 **数据采集 → 时间线管理 → AI 冲突检测 → AI 协调决策 → 移动端交互** 的全链路，作为从资深 Java 后端转型 AI 应用开发的作品集项目。

### 4.2 阶段目标

| 阶段 | 周期 | 目标 | 产出 |
|------|------|------|------|
| **Phase 1** | 2 周 | Python 基础 + FastAPI | 项目骨架、Pydantic 模型、SQLAlchemy 配置 |
| **Phase 2** | 3 周 | 数据库搭建 | PostgreSQL 建表、Redis 集成、基础 CRUD |
| **Phase 3** | 3 周 | 爬虫服务 | BeautifulSoup → Playwright、APScheduler 定时采集 |
| **Phase 4** | 4 周 | AI Agent 核心 | DeepSeek 接入、LangGraph 编排、Function Calling、冲突检测引擎 |
| **Phase 5** | 2 周 | RAG 知识库 | Qdrant 部署、BGE-M3 嵌入、文档检索 |
| **Phase 6** | 2 周 | Flutter APP | 移动端完成、端到端联调 |
| **Phase 7** | — | 部署上线 | Docker 容器化、Nginx 配置、CI/CD |

### 4.3 当前进度

| Phase | 状态 | 关键交付 |
|-------|------|----------|
| Phase 1 — 骨架 | ✅ | FastAPI 5服务 + common模块 |
| Phase 2 — CRUD | ✅ | User/Task CRUD + bcrypt + JWT + PostgreSQL + SQLite |
| Phase 3 — 爬虫 | ✅ | 4爬虫(BS4/Playwright/httpx) + APScheduler |
| Phase 4 — Agent | ✅ | LangGraph + DeepSeek + Pydantic结构化输出 + 流式SSE |
| Phase 5 — RAG | ✅ | SimpleEmbedding + 内存向量 + Agent集成 |
| Phase 6 — Flutter | 🔲 | 移动端 (Flutter + Dart) |
| Phase 7 — 部署 | 🔲 | Docker Compose + Nginx |

### Agent 架构详情

```
林 Agent
├── System Prompt: messages[0] = LIN_SYSTEM_PROMPT (固定人格)
├── Planner Node: ChatPromptTemplate → Pydantic(PlannerOutput) → intent/sub_tasks
├── Tools: 16 个工具 (calendar/task/weather/travel/vision/knowledge)
├── Coordinator Node: ChatPromptTemplate → Pydantic(ConflictOutput) → solutions
└── Reply Node: ChatPromptTemplate → stream_reply() → SSE 流式输出

每个 Node 独立 ChatPromptTemplate + Pydantic Structured Output
Node=流程 Prompt=思考 Tool=执行
换模型(Qwen/GPT-4V)只改 deepseek_client.py
```

### 4.4 V1 MVP 范围（当前焦点）

**做**：
- ✅ 用户登录/注册
- ✅ 手动创建/删除/查询任务
- ✅ AI 添加/删除/修改任务
- ✅ 时间冲突检测
- ✅ 课表爬取 + 双层存储
- 🔲 手机 App (Flutter)

**不做**：
- ❌ 爬100个网站
- ❌ 自训练/自部署大模型
- ❌ 多 Agent 协作

### 4.5 安全原则

| # | 原则 | 实现 |
|---|------|------|
| 1 | DeepSeek Key 不放 APP | `.env` 仅后端，Flutter→后端→DeepSeek |
| 2 | AI 不直操作 DB | Agent → Function → Service → Repository → DB |
| 3 | 不自己部署大模型 | DeepSeek API (deepseek-chat) |
| 4 | AI 全链路 Trace | `AgentTracer` 记录每一步决策 |
| 5 | 手机只是客户端 | AI/爬虫/数据库全部在后端运行 |

---

## 五、框架 (Framework)

### 5.1 后端框架

```txt
# FastAPI 核心
fastapi==0.115.*
uvicorn[standard]==0.34.*
pydantic==2.*
pydantic-settings==2.*

# 数据库
sqlalchemy[asyncio]==2.0.*
asyncpg==0.30.*           # PostgreSQL 异步驱动
alembic==1.14.*           # 数据库迁移

# Redis
redis==5.2.*
hiredis==2.*              # Redis 高性能解析器

# 向量数据库
qdrant-client==1.12.*

# LLM / Agent
langgraph==0.2.*
langchain==0.3.*
openai==1.*               # DeepSeek 兼容 OpenAI SDK

# 爬虫
requests==2.32.*
beautifulsoup4==4.12.*
playwright==1.50.*

# 定时任务
apscheduler==3.10.*

# 工具
httpx==0.28.*             # 异步 HTTP 客户端（服务间调用）
python-jose[cryptography]==3.3.*  # JWT 认证
```

### 5.2 编码规范
- 包名：`ai_schedule_agent.*` 各服务内
- 统一返回格式：`{"code": 200, "message": "success", "data": {...}}`
- 异常处理：FastAPI `exception_handler` 全局异常处理
- 日志：Python `logging` + `structlog`（结构化日志）
- 配置：`pydantic-settings` 多环境（dev / prod）
- 类型注解：所有函数必须标注参数和返回值类型
- 异步优先：FastAPI 路由和数据库操作一律 `async/await`

### 5.3 API 风格对比（Java → Python）

```java
// Java Spring Boot
@PostMapping("/task")
public Result createTask(@RequestBody TaskDTO dto) {
    return Result.success(taskService.createTask(dto));
}
```

```python
# Python FastAPI
@router.post("/task")
async def create_task(dto: TaskCreateDTO) -> Result[TaskDTO]:
    task = await task_service.create_task(dto)
    return Result.success(task)
```

---

## 六、核心业务模型

### 6.1 实体关系

```
User (用户)
  ├── id, username, email, password_hash
  ├── role (ADMIN/USER)
  │
  ├── 1 : N → Task (任务/行程)
  │     ├── id, user_id, title, description
  │     ├── start_time, end_time
  │     ├── priority (HIGH/MEDIUM/LOW)
  │     ├── status (PENDING/IN_PROGRESS/COMPLETED/CANCELLED)
  │     ├── location (地点)
  │     ├── category (MEETING/TRIP/PERSONAL/WORK)
  │     └── created_at, updated_at
  │
  ├── 1 : N → Timeline (时间线)
  │     ├── id, user_id, date
  │     ├── events: JSON[]  (排序后的事件列表)
  │     └── generated_by: AI/MANUAL
  │
  ├── 1 : N → Conflict (冲突)
  │     ├── id, user_id
  │     ├── task_a_id, task_b_id
  │     ├── overlap_start, overlap_end
  │     ├── severity (CRITICAL/WARNING/INFO)
  │     ├── resolution (建议方案)
  │     └── resolved: bool
  │
  ├── 1 : N → AgentSession (Agent 会话)
  │     ├── id, user_id
  │     ├── messages: JSON[]
  │     ├── state: JSON (LangGraph 状态)
  │     └── created_at
  │
  └── 1 : N → CrawlData (爬虫数据)
        ├── id, user_id
        ├── source (航班/天气/新闻)
        ├── raw_data: JSON
        └── created_at
```

### 6.2 冲突检测规则

| 规则 | 描述 |
|------|------|
| **时间重叠** | `task_a.end_time > task_b.start_time` → 冲突 |
| **优先级排序** | HIGH > MEDIUM > LOW，低优先级让位高优先级 |
| **地点冲突** | 同一时间段不同地点 → 物理不可达（需要交通时间） |
| **缓冲时间** | 相邻任务之间至少 15 分钟缓冲 |
| **AI 决策权重** | 优先级(40%) + 历史习惯(30%) + 参与人数(20%) + 可调整性(10%) |

### 6.3 AI 协调决策模型

```
输入：冲突列表 + 用户偏好 + 历史数据
  ↓
AI 分析维度：
  1. 任务重要性（能否延期？能否委托？能否取消？）
  2. 参与者影响（多少人受影响？是否有外部客户？）
  3. 时间敏感性（截止日期、不可变更性）
  4. 用户历史选择偏好
  ↓
输出：
  方案A（推荐）：具体调整方案 + 影响分析
  方案B：备选方案 + 影响分析
  方案C：兜底方案 + 影响分析
```

### 6.4 课表存储架构（Redis + PostgreSQL 双层）

```
[GDUT 爬虫 / 手动刷新]
        │
        ▼
  POST /api/v1/crawl/schedule/refresh
        │
  延迟双删 (Cache-Aside Double-Delete):
  ① 删 Redis (本周7天)
  ② 更新 PostgreSQL (删旧 + 插新)
  ③ sleep 500ms (等并发完成)
  ④ 再删 Redis (清脏数据)
  ⑤ 预热今日数据
        │
   ┌────┴────┐
   ▼         ▼
[Redis]   [PostgreSQL]
 TTL=1d    schedule 表
 今日视图   持久化+学期清理
```

### 6.5 时间线数据结构

```json
{
  "date": "2026-03-11",
  "events": [
    {
      "time": "09:00",
      "duration": 120,
      "event": "客户会议",
      "category": "MEETING",
      "location": "北京办公室",
      "priority": "HIGH"
    },
    {
      "time": "13:00",
      "duration": 180,
      "event": "飞往上海",
      "category": "TRIP",
      "location": "首都机场→虹桥机场"
    },
    {
      "time": "18:00",
      "duration": 90,
      "event": "晚餐",
      "category": "PERSONAL",
      "location": "上海外滩"
    }
  ]
}
```

---

## 七、API 设计（初版）

### 7.1 Agent 对话 API

```
POST /api/v1/agent/chat
  Request:  { "message": "帮我安排下周上海出差", "session_id": "uuid" }
  Response: { "reply": "...", "conflicts": [...], "suggestions": [...] }
```

### 7.2 时间线 API

```
GET    /api/v1/timeline?date=2026-03-11
POST   /api/v1/timeline/generate   ← AI 自动生成
PUT    /api/v1/timeline/{id}
```

### 7.3 任务 CRUD API

```
GET    /api/v1/tasks?start=...&end=...
POST   /api/v1/tasks
PUT    /api/v1/tasks/{id}
DELETE /api/v1/tasks/{id}
```

### 7.4 冲突检测 API

```
GET    /api/v1/conflicts?start=...&end=...
POST   /api/v1/conflicts/resolve/{id}  ← AI 协调解决
```

---

## 八、开发工具配置

| 工具 | 用途 |
|------|------|
| VSCode | 代码编辑器 |
| Claude Code | AI 辅助编码 |
| DeepSeek V4 | 方案设计 + 模型调用 |
| GitHub Copilot | 代码补全 |

---

## 九、部署架构

```
docker-compose.yml
├── nginx (80:80)
├── app-service (8000)
├── crawler-service (8001)
├── agent-service (8002)
├── timeline-service (8003)
├── rag-service (8004)
├── postgres (5432)
├── redis (6379)
└── qdrant (6333)
```

### 爬虫注册表

| 爬虫 | 技术栈 | 数据源 |
|------|--------|--------|
| `weather` | httpx | wttr.in JSON API |
| `news` | **BeautifulSoup4 + lxml** | HackerNews HTML 页面解析 |
| `calendar` | httpx + 离线回退 | nager.at API / 中国法定节假日 |
| `dynamic` | **Playwright (Chromium headless)** | 任意 JS 渲染页面 |

---

## 十、与电商平台项目的差异

| 维度 | 电商平台 | AI Schedule Agent |
|------|----------|-------------------|
| 语言 | Java / Spring Boot | Python / FastAPI |
| 核心 | CRUD + 业务规则 | AI Agent + 智能决策 |
| ORM | MyBatis-Plus | SQLAlchemy 2.0 async |
| 数据库 | MySQL 8.0 | PostgreSQL 16 |
| 向量数据库 | 无 | Qdrant |
| Agent 框架 | 无 | LangGraph |
| 爬虫 | 无 | BeautifulSoup4 + Playwright |
| 移动端 | Electron 桌面端 | Flutter 移动端 |
| 知识库 | 无 | RAG + BGE-M3 |

---

## 十一、文档维护说明

> **重要**：本文件是项目的「大脑」，所有核心决策和架构信息在此维护。
> 每次修改项目结构、新增服务、调整业务规则后，必须同步更新本文件。
> AI 助手的第一个动作始终是阅读本文件，确保上下文一致。

---

*创建日期：2026-06-13*
*维护者：Claude AI Assistant & 项目负责人*
