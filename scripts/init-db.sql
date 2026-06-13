-- ============================================
-- AI Schedule Agent 数据库初始化脚本
-- ============================================

-- 用户表
CREATE TABLE IF NOT EXISTS sys_user (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(128),
    password_hash VARCHAR(256) NOT NULL,
    role VARCHAR(32) DEFAULT 'USER' CHECK (role IN ('ADMIN', 'USER')),
    avatar_url VARCHAR(512),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 任务/行程表
CREATE TABLE IF NOT EXISTS task (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    title VARCHAR(256) NOT NULL,
    description TEXT,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    priority VARCHAR(16) DEFAULT 'MEDIUM' CHECK (priority IN ('HIGH', 'MEDIUM', 'LOW')),
    status VARCHAR(32) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    location VARCHAR(512),
    category VARCHAR(32) DEFAULT 'PERSONAL' CHECK (category IN ('MEETING', 'TRIP', 'PERSONAL', 'WORK')),
    tags JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_user_id ON task(user_id);
CREATE INDEX IF NOT EXISTS idx_task_start_time ON task(start_time);
CREATE INDEX IF NOT EXISTS idx_task_end_time ON task(end_time);
CREATE INDEX IF NOT EXISTS idx_task_user_time ON task(user_id, start_time, end_time);

-- 时间线表
CREATE TABLE IF NOT EXISTS timeline (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    events JSONB DEFAULT '[]',
    generated_by VARCHAR(16) DEFAULT 'MANUAL' CHECK (generated_by IN ('AI', 'MANUAL')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_timeline_user_date ON timeline(user_id, date);

-- 冲突表
CREATE TABLE IF NOT EXISTS conflict (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    task_a_id BIGINT NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    task_b_id BIGINT NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    overlap_start TIMESTAMPTZ,
    overlap_end TIMESTAMPTZ,
    severity VARCHAR(16) DEFAULT 'WARNING' CHECK (severity IN ('CRITICAL', 'WARNING', 'INFO')),
    resolution JSONB,           -- AI 建议解决方案
    resolved BOOLEAN DEFAULT FALSE,
    resolved_by VARCHAR(16) DEFAULT NULL CHECK (resolved_by IN ('USER', 'AI')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT conflict_different_tasks CHECK (task_a_id <> task_b_id)
);

CREATE INDEX IF NOT EXISTS idx_conflict_user_id ON conflict(user_id);
CREATE INDEX IF NOT EXISTS idx_conflict_resolved ON conflict(resolved);

-- Agent 会话表
CREATE TABLE IF NOT EXISTS agent_session (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    title VARCHAR(256),
    messages JSONB DEFAULT '[]',
    agent_state JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_session_user ON agent_session(user_id, is_active);

-- 爬虫数据表
CREATE TABLE IF NOT EXISTS crawl_data (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    source VARCHAR(64) NOT NULL,
    source_url TEXT,
    raw_data JSONB NOT NULL,
    extracted_info JSONB,
    crawled_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crawl_data_source ON crawl_data(source);
CREATE INDEX IF NOT EXISTS idx_crawl_data_crawled ON crawl_data(crawled_at);

-- 知识库文档表（RAG 使用）
CREATE TABLE IF NOT EXISTS knowledge_doc (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(256) NOT NULL,
    content TEXT NOT NULL,
    doc_type VARCHAR(32) DEFAULT 'GENERAL',
    embedding_id VARCHAR(256),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 插入默认 admin 用户（密码: <CHANGE_ME>，需通过应用层 bcrypt 加密）
-- INSERT INTO sys_user (username, email, password_hash, role)
-- VALUES ('admin', 'admin@example.com', '$2b$12$...', 'ADMIN');
