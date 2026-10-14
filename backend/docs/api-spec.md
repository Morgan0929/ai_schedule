# API 接口文档 (v0.1.0)

## 基础信息

- 基础路径：`http://localhost:8000`
- 认证方式：Bearer Token (JWT)
- Content-Type：`application/json`

## 统一响应格式

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

| code | 含义 |
|------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 请求参数错误 |
| 401 | 未登录 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突 |
| 500 | 服务器错误 |

---

## 一、认证模块 (app-service:8000)

### POST /api/v1/auth/login
### POST /api/v1/auth/register

---

## 二、Agent 对话 (agent-service:8002)

### POST /api/v1/agent/chat

```json
// Request
{
  "message": "帮我安排下周上海出差",
  "session_id": "uuid-optional"
}

// Response
{
  "code": 200,
  "data": {
    "reply": "已发现：...",
    "needs_confirmation": false,
    "confirmation_stage": "",
    "conflicts": [],
    "suggestions": [],
    "tasks_created": [],
    "actions_taken": []
  }
}
```

查询“安排 / 课表 / 日程”时，Agent 会合并返回当天任务和课程。只有在冲突确认环节，移动端才会显示“同意 / 取消”快捷按钮。

---

## 三、任务 CRUD (timeline-service:8003)

### GET /api/v1/tasks?start=...&end=...
### POST /api/v1/tasks

创建任务要求 `Idempotency-Key` 请求头。相同用户、相同键、相同内容重试返回首次结果；
处理中返回 202，内容不一致返回 409，原任务已删除返回 410。
`GET /api/v1/task-requests/{request_id}` 查询当前用户的请求状态。
租期接管和客户端重试边界见 [创建幂等说明](task_idempotency.md)。
### PUT /api/v1/tasks/{id}
### DELETE /api/v1/tasks/{id}

任务和课表响应包含 `version`（初始值 1）。
`PUT /api/v1/tasks/{id}` 和 `PUT /api/v1/schedules/{id}` 必须携带读取时的版本号，例如：

```json
{"version": 1, "location": "图书馆"}
```

更新成功返回递增后的版本；版本冲突返回 HTTP 409，提示刷新后确认修改内容并重新提交。
缺少或传入无效版本号返回 HTTP 422。身份来源和归属校验见 [用户鉴权说明](user_authorization.md)。
已有数据库迁移与并发控制见 [版本号乐观锁](optimistic_locking.md)。

### GET /api/v1/schedules?user_id=1&date=2026-08-12

按日期查询当前学期课程。

---

## 四、时间线 (timeline-service:8003)

### GET /api/v1/timeline?date=2026-03-11
### POST /api/v1/timeline/generate

---

## 五、冲突检测 (timeline-service:8003)

### GET /api/v1/conflicts?user_id=1&start=...&end=...
### POST /api/v1/conflicts/resolve/{id}

---

## 六、爬虫 (crawler-service:8001)

### POST /api/v1/crawl/trigger

### POST /api/v1/crawl/schedule/from-url

从可公开访问的 URL 导入课表。适合目标页面不需要 App 内登录态，或用户提供的是可直接访问的课表地址。

```json
// Request
{
  "user_id": 1,
  "url": "https://jxfw.gdut.edu.cn/login!welcome.action"
}

// Response data
{
  "status": "IMPORTED | LOGIN_REQUIRED | NOT_FOUND | FAILED",
  "message": "课表采集完成，共识别 5 门课程。",
  "course_count": 5,
  "record_id": 123,
  "menu_url": "https://example.edu.cn/student/schedule"
}
```

### POST /api/v1/crawl/schedule/from-html

从 App 内置 WebView 读取到的当前页面内容导入课表。适合学校教务系统需要登录、Cookie 或动态页面状态的场景。

```json
// Request
{
  "user_id": 1,
  "html": "<html>...</html>",
  "source_url": "https://jxfw.gdut.edu.cn/login!welcome.action"
}

// Response data
{
  "status": "IMPORTED | LOGIN_REQUIRED | NOT_FOUND | FAILED",
  "message": "课表采集完成，共识别 5 门课程。",
  "course_count": 5,
  "record_id": 123,
  "menu_url": "https://jxfw.gdut.edu.cn/login!welcome.action"
}
```

WebView 导入时，`html` 不只包含 `document.documentElement.outerHTML`，还可能包含以下 App 合成的辅助表格：

| 标记 | 用途 |
|------|------|
| `data-codex-visible-text="true"` | 当前页面可见文本兜底 |
| `data-codex-clickable-controls="true"` | 候选课表入口/按钮文本 |
| `data-codex-visual-courses="true"` | 可见课程卡片的文本和屏幕位置 |
| `data-codex-visual-headers="true"` | 星期/日期表头的文本和屏幕位置 |

返回值里的 `record_id` 可直接用于查询本次导入日志：`GET /api/v1/crawl/records/{record_id}`。

解析优先级：标准列式表格 → 矩阵课表 → WebView 视觉卡片兜底。

---

## 七、知识库 (rag-service:8004)

### POST /api/v1/rag/documents
### GET /api/v1/rag/search?q=...
### GET /api/v1/rag/documents
