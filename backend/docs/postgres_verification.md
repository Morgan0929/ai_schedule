# PostgreSQL 集成验证

2026 年 10 月 14 日验证记录：真实 PostgreSQL 17.4 上的完整后端测试共 80 项全部通过，
包含数据库集成用例；根目录另有 17 项测试通过。测试实例已在结束后停止并清理。

业务数据库配置使用 PostgreSQL。新增的数据库测试支持真实 PostgreSQL，并为每个测试创建独立随机 schema。
测试读取专用的 `SCHEDULE_TEST_DATABASE_URL`，不会自动读取 `.env` 中的业务连接地址。

## 本机临时实例

安装 PostgreSQL 后，从项目根目录执行：

```powershell
./venv/Scripts/python.exe backend/scripts/verify_postgres.py --pg-bin D:/pgsql/pgsql/bin
```

启动器在系统临时目录初始化一个新实例，仅监听 `127.0.0.1` 的临时端口，使用独立测试账号，
运行完整后端 unittest 测试，然后停止该实例并清理临时目录。
它不启动或停止现有业务实例，也不修改业务数据库。Windows 下后台进程不显示控制台窗口。

每个数据库测试只创建和删除 `schedule_test_` 加随机 UUID 的 schema。
清理器校验 schema 名格式后才执行删除，不对业务 schema 执行 drop 或 truncate。

## CI 或已有专用测试实例

也可以设置 `SCHEDULE_TEST_DATABASE_URL` 为专用 PostgreSQL 实例的 SQLAlchemy asyncpg URL，
再运行 `python -m unittest discover -s backend/tests -v`。
测试账号需要创建与删除测试 schema 的权限；不应使用业务数据库作为测试目标。

未提供测试 URL 时，快速离线测试仍可使用隔离的 SQLite。
发布前应执行 PG 验证，检查真实的时间类型、数据库时间、行锁等待、并发接管及事务回滚行为。

## 覆盖

PG 验证覆盖版本号条件更新、两个连接竞争同一版本、旧 ORM 实例写入冲突、旧表字段迁移、
日程创建幂等、同键并发重试、租期过期接管、旧执行者隔离、取消和故障后的回滚、
成功结果重放、删除日程后的幂等记录保留、用户鉴权及 Agent 确认恢复。
模型网络调用和 Redis 会话使用对应测试替身；该流程不代表外部模型或线上 Redis 压测。
