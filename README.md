# AI Schedule Agent（日程智能助手）

> AI Agent + 日程管理系统 + 数据采集平台 + 移动端应用

## 项目定位

构建一个接近真实 AI Agent 产品架构的项目，覆盖**数据采集 → 时间线管理 → AI 冲突检测 → AI 协调决策 → 移动端交互**的全链路。

## 核心能力

| 能力 | 描述 |
|------|------|
| 爬虫获取外部数据 | 自动采集会议、航班、天气等外部信息 |
| 自动生成时间线 | 将零散任务整理为可视化时间线 |
| AI 对话管理行程 | 自然语言交互，Agent 理解意图并操作日程 |
| AI 冲突检测 | 多任务时间重叠自动发现 |
| AI 协调决策 | 冲突时给出多方案，用户选择或 AI 自动决策 |
| 手机 APP 使用 | Flutter 跨平台移动端 |

## 快速启动

### 1. 启动基础设施

```bash
docker-compose up -d
```

### 2. 创建虚拟环境 & 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r app_service/requirements.txt
pip install -r crawler_service/requirements.txt
pip install -r agent_service/requirements.txt
pip install -r timeline_service/requirements.txt
pip install -r rag_service/requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 DeepSeek API Key 等配置
```

### 4. 启动各服务

```bash
# 终端 1 — API 网关（从项目根目录运行）
python app_service/main.py

# 终端 2 — 爬虫服务
python crawler_service/main.py

# 终端 3 — AI Agent 服务
python agent_service/main.py

# 终端 4 — 时间线服务
python timeline_service/main.py

# 终端 5 — RAG 知识库服务
python rag_service/main.py
```

### 5. 验证

```bash
curl http://localhost:8000/health
# {"code":200,"message":"success","data":{"status":"ok","service":"app-service"}}
```

## 服务架构

| 服务 | 端口 | 已验证 |
|------|------|--------|
| app_service | 8000 | ✅ |
| crawler_service | 8001 | ✅ |
| agent_service | 8002 | ✅ |
| timeline_service | 8003 | ✅ |
| rag_service | 8004 | ✅ |

## 项目状态

- [x] Phase 1 完成 — 项目骨架、Pydantic 模型、FastAPI 入口、Docker Compose
- [ ] Phase 2 — 数据库搭建 + CRUD
- [ ] Phase 3 — 爬虫服务
- [ ] Phase 4 — AI Agent 核心
- [ ] Phase 5 — RAG 知识库
- [ ] Phase 6 — Flutter APP
- [ ] Phase 7 — 部署上线
