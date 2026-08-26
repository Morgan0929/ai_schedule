-- Repair migration for deployments created before the Agent tables were added.
-- Safe to run repeatedly.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS agent_session (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    title VARCHAR(256),
    messages JSONB DEFAULT '[]',
    agent_state JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_session_user
    ON agent_session(user_id, is_active);

CREATE TABLE IF NOT EXISTS todo_queue (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(id) ON DELETE CASCADE,
    title VARCHAR(256) NOT NULL,
    note TEXT DEFAULT '',
    priority VARCHAR(16) DEFAULT 'MEDIUM'
        CHECK (priority IN ('HIGH', 'MEDIUM', 'LOW')),
    status VARCHAR(16) DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'DONE', 'ARCHIVED')),
    remind_count INTEGER DEFAULT 0,
    max_remind INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_todo_queue_user_status
    ON todo_queue(user_id, status);
