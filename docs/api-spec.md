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
    "conflicts": [],
    "suggestions": [],
    "tasks_created": [],
    "actions_taken": []
  }
}
```

---

## 三、任务 CRUD (timeline-service:8003)

### GET /api/v1/tasks?start=...&end=...
### POST /api/v1/tasks
### PUT /api/v1/tasks/{id}
### DELETE /api/v1/tasks/{id}

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

---

## 七、知识库 (rag-service:8004)

### POST /api/v1/rag/documents
### GET /api/v1/rag/search?q=...
### GET /api/v1/rag/documents
