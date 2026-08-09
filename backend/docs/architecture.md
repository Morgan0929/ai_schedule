# 林 (Lin) — Agent 架构文档

> 最后更新: 2026-08-05
> 涵盖: 实体模型 / 工作记忆 / 冲突解决 / 所有已修复 Bug

---

## 一、实体分层

```
UserIntent (用户输入)
     │
     ▼
PendingTask (Redis, 待确认)          Task (PostgreSQL, 已确认)
  ref_id: "pending_abc123"             id: 21
  title: "滑雪"                        title: "客户沟通"
  start_time: "2026-08-06T15:00"       start_time: 2026-08-06 15:00
  status: "conflict_blocked"           status: ACTIVE
  source: "user_request"
     │                                    │
     └──────────┬─────────────────────────┘
                │
          Conflict (Redis)
          {
            "pending_ref": "pending_abc123",
            "existing_task_id": 21,
            "options": { A, B, C }
          }
```

### 规则

| 实体 | 存储 | ID | 操作 |
|------|------|-----|------|
| `Task` | PostgreSQL | `id: int` | UPDATE / DELETE |
| `PendingTask` | Redis (`pending:task:{ref_id}`) | `ref_id: str` | reschedule / commit / discard |
| `Conflict` | Redis (`working:mem:{session_id}.conflict`) | — | A/B/C 选择 |

---

## 二、Working Memory 三层结构

```
Redis: working:mem:{session_id}
├── active_flow: "conflict_resolution" | None
├── conflict: { type, stage, options, entities, ... }
└── pending_tasks: [{ ref_id, title, ... }]
```

### 生命周期

```
active_flow = None
     │
     │ 冲突产生
     ▼
active_flow = "conflict_resolution"
conflict = { stage: WAITING_CHOICE, options: {A,B,C} }
     │
     │ 用户确认/取消
     ▼
active_flow = None
conflict = (删除)
```

**关键**: `conflict` 不占用整个会话。新事件路由到 `event_detector`，旧冲突保留在 Redis，互不污染。

---

## 三、Agent 工作流

```
Input → check_pending_action
           │
    active_flow == "conflict_resolution"?
           │
     YES ──┼── NO
           │     │
    ┌──────┘     └──────┐
    ▼                   ▼
waiting_confirm?    event_detector
    │                   │
    │ (锁)         high confidence?
    │              YES ──┼── NO
    ▼              │         │
conflict       tools_exec  planner
resolver       (跳过LLM)   (LLM)
    │              │         │
    └──────────────┴────┬────┘
                        ▼
                 tools_executor
                        │
                 conflict_check
                        │
                  coordinator
                        │
                     reply
```

### Router 规则

| active_flow | stage | 输入 | 路由 |
|-------------|-------|------|------|
| None | — | 任意 | `event_detector` |
| conflict_resolution | waiting_confirm | 确认/取消/A/B/C | `conflict_resolver` |
| conflict_resolution | waiting_confirm | 其他一切 | `conflict_resolver` (锁住) |
| conflict_resolution | waiting_choice | A/B/C/确认/取消 | `conflict_resolver` |
| conflict_resolution | waiting_choice | 明显新事件 | `event_detector` + 提醒 |
| conflict_resolution | waiting_choice | 模糊输入 | `conflict_resolver` (clarification) |

---

## 四、Conflict Resolution 状态机

```
WAITING_CHOICE ──(A/B/C 选择)──► WAITING_CONFIRM ──(确认)──► clear
      │                                │
      │ (取消)                          │ (取消)
      ▼                                ▼
   CANCELLED                       CANCELLED
```

### A/B/C 选项结构

```json
{
  "A": {
    "label": "保留「客户沟通」, 调整「滑雪」",
    "preview": {"keep": "客户沟通", "change": "滑雪 → 19:00"},
    "actions": [{"type": "reschedule_pending", "ref_id": "pending_abc"}],
    "requires_time": true
  },
  "B": {
    "label": "保留「滑雪」, 调整「客户沟通」",
    "preview": {"keep": "滑雪", "change": "客户沟通 → 18:00"},
    "actions": [{"type": "update_task", "task_id": 21}],
    "requires_time": true
  },
  "C": {
    "label": "取消「滑雪」",
    "preview": {"discard": "滑雪"},
    "actions": [],
    "requires_time": false
  }
}
```

三层解耦:
- `label` → Reply 展示
- `preview` → UI 预览
- `actions` → Executor 执行

### Action 类型

| Action Type | target | 选择阶段 | confirm 阶段 |
|-------------|--------|---------|-------------|
| `reschedule_pending` | `ref_id: str` | 立即执行: 更新 Redis PendingTask 时间 | `commit_pending` → INSERT |
| `update_task` | `task_id: int` | 无操作 | `update_task` → UPDATE |
| `discard_pending` | `ref_id: str` | 无操作 | 无操作 (不创建) |

### A方案两步分离 (Fix1)

```
用户: A方案 延后到晚上七点
  → _execute_plan_with_override
  → immediate sub_tasks: [reschedule_pending(ref_id, new_time)]  ← 本轮执行
  → pending_action.proposed_actions: [commit_pending(ref_id)]     ← confirm 时执行

本轮: Redis PendingTask.start_time = 19:00
confirm: commit_pending → INSERT INTO task → 获得真实 DB id
```

---

## 五、Commit 流程

```
_handle_confirm("确认")
  → 不依赖 proposed_actions (可能在 Redis 往返中丢失)
  → _build_commit_actions(plan, options, entities, move_to)
  → 从 options[plan].actions 重建 sub_tasks

  RESCHEDULE_PENDING → commit_pending(ref_id)  → INSERT
  RESCHEDULE_TASK    → update_task(task_id)     → UPDATE (+ _check_conflict)
  DISCARD_PENDING    → 无操作
```

---

## 六、已修复 Bug 清单

| # | Bug | 根因 | 修复 |
|---|-----|------|------|
| 1 | pending_action 存在时进 planner | Router 未检查 pending | `check_pending_action` 最高优先级 |
| 2 | update_task handler 不更新 state | tools_executor 只打日志 | 提取 title/new_time → actions_taken + updated_tasks |
| 3 | Reply 缺 update_event 分支 | 只判断 create/query | 按结果优先级: actions_taken > conflicts > query > chat |
| 4 | pending_action 清理不干净 | `{}` 不写入 Redis | commit 清 `active_flow=None`, agent_service 删 key |
| 5 | 时间漂移 (晚上九点 → 昨天) | 解析用 today, 非冲突日期 | `reference_date` 从 `options.move_time` 继承 |
| 6 | Coordinator 调 LLM (12s 延迟) | A/B/C 是确定逻辑 | 纯 Python 生成, 零 LLM token |
| 7 | options 语义混乱 (keep_new/existing) | 字段不一致 | 统一 `existing_task`/`new_task` → `keep`/`move` → action type |
| 8 | update_task 靠 title 查找 | 危险, "跳绳" vs "跳绳训练" | 传 `task_id`, tools 层用 ID 直查 |
| 9 | HARD 冲突 new_task id=0 | 假 ID | `source: "pending"`, `id: None`, commit 时才 INSERT |
| 10 | 新事件污染旧冲突 | pending_action 占整个会话 | `active_flow` / `conflict` / `pending_tasks` 三层分离 |
| 11 | confirm → COMMIT 0 actions | proposed_actions 为空 | `_build_commit_actions` 从 options 重建, 不依赖 proposed |
| 12 | A方案 update_task(id=0) | pending task 走 update | `reschedule_pending` → Redis, `commit_pending` → DB |
| 13 | A方案无时间时 proposed=[] | 空列表 | 无时间也生成 commit_pending (使用原时间) |
| 14 | waiting_confirm 不锁 | 新事件可绕过 | waiting_confirm 锁: 只接受 确认/取消/修改 |

---

## 七、关键设计决策

1. **Event Detector 优先于 Planner** — 日程类确定任务不浪费 LLM token
2. **Coordinator 零 LLM** — A/B/C 方案是纯 Python 逻辑
3. **Conflict Resolver 不调 Planner** — 状态机独立, pending_action 最高优先级
4. **PendingTask 不立即入库** — 先存 Redis, 冲突解决后才 INSERT
5. **Commit 从 options 重建 actions** — 不依赖 proposed_actions (Redis 往返可能丢失)
6. **waiting_confirm 是锁** — 只接受 确认/取消/修改方案, 不接受新事件
7. **三层选项结构** — label (展示) / preview (预览) / actions (执行) 完全解耦
