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
| 课表网页登录导入 | App 内置 WebView 登录教务系统，后端解析并保存课程 |

## Agent 行为

- 用户问“有什么安排 / 有什么课 / 查一下日程”时，会合并返回任务和课程。
- 只有在冲突确认环节，移动端才显示“同意 / 取消”快捷按钮。
- 回复语气保持秘书式表达，不再像系统回执。

## Git 工作流

本仓库按“支线开发，主线稳定”的方式管理：

1. 规划、开发、测试、Bug 修复过程都在支线进行，默认分支名使用 `codex/<功能或问题名>`。
2. 支线可以提交过程性改动，但每次提交只包含当前任务相关文件。
3. 功能完成或 Bug 修复验证通过后，再合入 `main` 作为主线稳定版本。
4. `main` 不直接承载未验证的实验、临时调试或半成品改动。
5. 工作区有未提交内容时，先确认文件归属；不得把无关改动一起 stage/commit。

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

## 课表导入

课表导入由移动端和爬虫服务协作完成：

1. 移动端打开内置 WebView，用户在学校教务系统完成登录。
2. WebView 自动扫描“我的课表 / 课表查询 / 课程查询”等入口，并尝试点击进入课表页。
3. 导入时采集当前页面源码、同源 iframe、可见课程卡片、星期/日期表头和候选可点击控件。
4. `crawler_service` 解析标准表格、矩阵课表和视觉卡片兜底数据，保存到 `schedule` 表。

注意：跨域 iframe 受浏览器安全限制，App 能看到画面不代表 JavaScript 能读取其中 DOM；这种情况只能依赖同源页面数据或后续截图/OCR兜底。

## 项目状态

当前阶段：Phase 7，已完成服务器迁移和后端部署，正在做上线收口。

- [x] Phase 1 完成 - 项目骨架、Pydantic 模型、FastAPI 入口、Docker Compose
- [x] Phase 2 - 数据库搭建 + CRUD
- [x] Phase 3 - 爬虫服务
- [x] Phase 4 - AI Agent 核心
- [x] Phase 5 - RAG 知识库
- [x] Phase 6 - Flutter APP 基础端 + 课表导入入口
- [x] Phase 7 - Ubuntu ECS 迁移完成，PostgreSQL / Redis / Qdrant / 后端服务已恢复
- [ ] Phase 7 收尾 - 阿里云安全组和反向代理 / HTTPS

## 当前部署

- 服务器：阿里云 ECS `<ECS_PUBLIC_IP>`
- 系统：Ubuntu 22.04 LTS
- 后端服务：`app_service`、`crawler_service`、`agent_service`、`timeline_service`、`rag_service`
- 数据基础设施：PostgreSQL、Redis、Qdrant 已在服务器恢复
- 端口策略：数据库和向量库仅本机监听，`8001`-`8004` 仅本机监听，`8000` 保留为对外 API 入口

说明：如果后续补上反向代理和 HTTPS，这一阶段就可以视为正式上线完成。

## 生产上线收口

生产环境使用同一个 HTTPS 域名作为移动端入口。Nginx 配置模板位于 `../deploy/nginx/ai-schedule.conf.example`，systemd 服务单元位于 `../deploy/systemd/`。

服务器上的基本顺序：

```bash
sudo bash scripts/install-systemd-services.sh /srv/ai-schedule
sudo nginx -t
sudo systemctl reload nginx
```

生产 `.env` 必须设置强 `POSTGRES_PASSWORD`、`DATABASE_URL`、`JWT_SECRET_KEY` 和 `DEEPSEEK_API_KEY`。`BOOTSTRAP_ADMIN_*` 留空时不会自动创建默认管理员账号。
