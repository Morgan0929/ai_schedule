# 林 (Lin) — AI 个人事务秘书 项目蓝图

> 本文档为 AI 助手的核心上下文文件，每次回答前必须阅读。

---

## 一、项目概述

**项目名称**：林 — AI 个人事务秘书  
**项目根目录**：`D:/AIagent日程规划/`  
**代码仓库**：https://gitee.com/<GITEE_USERNAME>/ai-schedule-management  
**远程数据库**：<REMOTE_DB_HOST>:5432 (PostgreSQL 16.14, Ubuntu aarch64)  
**项目类型**：AI Agent 日程管理系统 + 个人事务助手

### Agent 人格

**名字**：林  
**性格**：随性、开朗、积极、有亲和力  
**风格**：自然、轻松、温暖，像一个熟悉用户习惯的私人助理  
**职责**：只处理个人事务管理，无关话题礼貌拒绝

---

## 二、数据栈 (Data Stack)

| 层级 | 技术 | 实际版本 | 用途 |
|------|------|---------|------|
| 语言 | Python | 3.12.5 | 后端核心语言 |
| 后端框架 | FastAPI | 0.136.3 | 5 服务 API |
| 数据验证 | Pydantic v2 | 2.13.4 | LLM 结构化输出 + DTO |
| ORM | SQLAlchemy 2.0 | 2.0.50 | 异步 DB 操作 |
| 关系数据库 | PostgreSQL | 16.14 (远程) | 全部持久化数据 |
| 缓存 | Redis | 7.x (本地) | 工作记忆 (TTL=30min) |
| LLM | DeepSeek | deepseek-chat | API 调用 |
| Agent 框架 | LangGraph | 1.2.5 | 5 节点状态图编排 |
| Agent SDK | LangChain | 1.3.9 | ChatPromptTemplate |
| 可观测 | LangSmith | 0.8.15 | 飞行记录仪 |
| 爬虫 | requests + BS4 + Playwright | — | 4 个注册爬虫 |
| 定时任务 | APScheduler | 3.11.2 | 爬虫定时采集 |
| 向量数据库 | pgvector + BGE-M3 | PostgreSQL 扩展 | RAG 语义检索 (1024d) |
| 移动端 | Flutter | 待开发 | 手机 App |

---

## 三、架构

### 3.1 目录结构

```
D:/AIagent日程规划/
├── venv/                              Python 虚拟环境
├── .env                               环境变量 (gitignored)
│
├── backend/                           Python AI 后端
│   ├── CLAUDE.md                      项目蓝图
│   ├── common/                        公共模块
│   │   ├── config.py                  pydantic-settings 配置
│   │   ├── database.py                SQLAlchemy async 引擎
│   │   ├── schemas/                   Pydantic 数据验证 (7 models)
│   │   └── utils/                     JWT / bcrypt
│   │
│   ├── app_service/         :8000     API 网关 & 用户认证
│   ├── agent_service/       :8002     AI Agent 核心
│   │   ├── graph/            LangGraph (planner/validator/tools/conflict/reply)
│   │   ├── llm/              DeepSeek Client + ChatPromptTemplate
│   │   ├── tools/            Document Analyzer
│   │   ├── memory/           Memory System (3层)
│   │   ├── middleware/       Tool Limit / Retry
│   │   ├── mcp/              MCP Client + Weather/Search Servers
│   │   ├── services/         AgentService
│   │   └── utils/            Tracer (LangSmith) + Coordinator
│   ├── timeline_service/    :8003     任务 CRUD + 冲突检测 + 课表
│   ├── crawler_service/     :8001     爬虫 (4 spiders) + APScheduler
│   ├── rag_service/         :8004     RAG (pgvector + Document Pipeline)
│   │   ├── parser/           分类器 + 多策略Splitter + 加工流水线
│   │   ├── repository/       pgvector 数据访问
│   │   └── services/         Embedding + RagService
│   └── personal/                     本地脚本 (gitignored)
│
└── mobile/                           Flutter App (待开发)
```

### 3.2 Agent 工作流

```
用户输入 → Memory Load (画像+摘要) → Token Check
    │
    ▼
Planner Node        ChatPromptTemplate → Pydantic(PlannerOutput)
  │ (LLM优先, 失败→Event Detector→UNKNOWN, 不伪装)
  │ 去关键词: 有未来时间+事件名→create_task
  │ 置信度: source=llm/mock, confidence=0.0~1.0
    │
    ▼
Validator Node      检查 intent/sub_tasks/title/time/confidence
  │ 缺字段→从输入提取事件名补全
  │ 低置信度(<0.6)→要求确认
    │
    ├─ 通过 ──────────────────────┐
    │                             │
    ▼                             ▼
Tools Executor              Reply Node
  Tool Call Limit(5)          (确认消息/
  Tool Retry(指数退避)          拒绝回复)
    │
    ▼
Conflict Check
    │
    ▼
Coordinator Node
    │
    ▼
Reply Node           ChatPromptTemplate → SSE流式
    │
    ▼
Memory Manager       Extract→Save(PG)
    │
    ▼
LangSmith Trace      飞行记录仪
```

### 3.3 Agent 分层规则

```
Node = 流程控制 (Planner/Validator/Reply)
Prompt = 思考 (ChatPromptTemplate, 每个 Node 独立)
Tool = 执行 (asyncpg直连PG, 不经过SQLAlchemy)
Middleware = 拦截 (ToolCallLimit/Retry/Summarize)

换模型: 只改 deepseek_client.py
改工具: 只改 graph/tools.py
改冲突: 只改 prompts.py
```

---

## 四、当前进度

| Phase | 状态 | 交付 |
|-------|------|------|
| Phase 1 — 骨架 | ✅ | FastAPI 5服务 + common |
| Phase 2 — CRUD | ✅ | User/Task CRUD + JWT + PostgreSQL |
| Phase 3 — 爬虫 | ✅ | 4爬虫 (BS4/Playwright/httpx) |
| Phase 4 — Agent | ✅ | LangGraph + Pydantic + 流式SSE + 中间件 + 记忆系统 |
| Phase 5 — RAG | ✅ | pgvector + BGE-M3(1024d) + Document Pipeline (8类型分类+5种Splitter) |
| Phase 6 — Flutter | 🔲 | 移动端 |
| Phase 7 — 部署 | 🔲 | Docker + Nginx |

### Agent 核心能力清单

| 能力 | 实现 |
|------|------|
| 自然语言 → 结构化输出 | PlannerOutput (Pydantic) |
| 工具调用 + 限流 | ToolCallLimiter (max 5) + Retry |
| 冲突检测 + 协调 | ConflictDetector + Coordinator Node |
| 流式 SSE 输出 | stream_reply() → EventSource |
| 结构化记忆 | 3层 (Working/Short/Long) + Summary Node |
| AI Trace | LangSmith + 本地 Tracer |
| 文档分析 | Document Analyzer (7种文档类型) |
| 消息裁剪 | Token Counter + prune_messages + 重要消息保护 |
| 安全 | Key不放APP / AI不直连DB / 手机只是客户端 |

---

## 五、数据库 (PostgreSQL)

**服务器**：<REMOTE_DB_HOST>:5432  
**数据库**：<DB_NAME> | **用户**：<DB_USER>  
**表**：13 张

| 表 | 用途 |
|------|------|
| sys_user | 用户认证 |
| task | 任务/行程 |
| timeline | 时间线 |
| conflict | 冲突记录 |
| schedule | 课表 |
| crawl_data | 爬虫数据 |
| agent_session | Agent Trace |
| user_profile | 用户画像 (key/value/confidence) |
| conversation_summary | 短期摘要 (7天) |
| user_memory | 通用记忆 (habit/preference/fact/event) |
| rag_document | RAG 原始文件元信息 |
| rag_chunk | 文档分段 + VECTOR(1024) embedding |
| rag_memory | 语义个人记忆 + VECTOR(1024) embedding |

---

## 六、API 设计

### Agent 对话

```
POST /api/v1/agent/chat          非流式 JSON
POST /api/v1/agent/chat/stream   SSE 流式 (EventSource)
GET  /api/v1/agent/mode          当前模式 (llm/mock)
```

### 用户认证 (app_service:8000)

```
POST /api/v1/auth/register /login
GET  /api/v1/users/me  /users
```

### 任务 CRUD (timeline_service:8003)

```
GET/POST/PUT/DELETE /api/v1/tasks
```

### 爬虫 (crawler_service:8001)

```
GET  /api/v1/crawl/spiders       列出爬虫
POST /api/v1/crawl/trigger       手动触发
GET  /api/v1/crawl/records       查询记录
POST /api/v1/crawl/schedule/refresh  课表刷新(延迟双删)
```

### RAG (rag_service:8004)

```
POST /api/v1/rag/documents       上传文档
GET  /api/v1/rag/search?q=       语义搜索
```

---

## 七、RAG — Document Pipeline

```
上传文档
    │
    ▼
DocumentClassifier (8种类型, 关键词+LLM)
    │
    ├── course     → CourseExtractor → 结构化 → SQL schedule + pgvector
    ├── assignment → AssignmentExtractor → 提取事件 → SQL task + pgvector
    ├── meeting    → MeetingSplitter → 按#标题切 (decision/todo/discussion)
    ├── ticket     → NoSplitter → 整条保存
    └── general    → RecursiveSplitter(800/150) → embedding → pgvector
```

| 文档类型 | 策略 | chunk? |
|----------|------|--------|
| 课程表 | 正则提取 课程/教师/教室/节次 | ❌ 结构化 |
| 作业通知 | 提取 标题/截止/课程 | ❌ 事件 |
| 会议纪要 | 按 # 标题切 + 标记类型 | ✅ |
| 项目文档 | RecursiveSplitter(1000/200) | ✅ |
| 通用文档 | RecursiveSplitter(800/150) | ✅ |
| 票据 | 不切, 整条 | ❌ |

核心原则: **分类优先 → 结构化提取优先 → 必要时才 Chunk → Embedding**。不是所有东西都塞向量库。

### 模型分工

```
林 Agent
    │
    ├── DeepSeek-V3 (推理/生成)  — deepseek-chat
    ├── DeepSeek-VL (图片理解)   — Document Analyzer Tool
    └── BGE-M3 (向量检索, 1024d) — RAG Infrastructure 层
              │
              ├── HuggingFaceBgeEmbeddings (langchain_community)
              ├── SentenceTransformer (直接调用)
              └── Fallback (字符特征, 零依赖)

Agent 只调用 Retriever, 不关心向量如何生成。换模型只改 EmbeddingService。
```

---

## 八、Middleware 层

| Middleware | 作用 |
|------|------|
| ToolCallLimiter | max 5次工具调用, 防死循环 |
| with_retry | Tool 失败→指数退避重试 |
| model_retry | LLM 超时/限流→重试→Fallback |
| ChatSummarizer | 对话 >20轮压缩为摘要 |
| TodoExtractor | 规则+LLM提取待办 |
| Token Counter | 超6000 token触发 Summary |
| Message Pruner | System永久 + 重要(score>0.7) + 最近20轮 |

---

## 九、Memory System

```
Working  (Redis, TTL=30min) : 当前对话状态
Short    (PG, 7天)           : conversation_summary
Long     (PG)                : user_profile + user_memory
Vector   (Qdrant, 未来)      : 语义搜索
```

**记忆规则**：
- ✅ 保存：固定习惯/课程/工作规律/偏好 (多次确认→置信度↑)
- ❌ 不保存：临时抱怨/一次性事件/敏感信息/随口表达

---

## 十、安全原则

| # | 原则 | 状态 |
|---|------|------|
| 1 | DeepSeek Key 不放 APP | ✅ `.env` 仅后端 |
| 2 | AI 不直操作 DB | ✅ Agent→Function→Service→Repo→DB |
| 3 | 不自己部署大模型 | ✅ DeepSeek API |
| 4 | AI 全链路 Trace | ✅ LangSmith + AgentTracer |
| 5 | 手机只是客户端 | ✅ AI/爬虫/DB 全部在后端 |

---

*最后更新：2026-07-15*
*维护者：Claude AI Assistant*
