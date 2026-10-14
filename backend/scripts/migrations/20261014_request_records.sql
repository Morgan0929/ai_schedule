-- Durable request history intentionally has no cascading FK to the task table.
CREATE TABLE IF NOT EXISTS request_record (
    user_id INTEGER NOT NULL,
    operation VARCHAR(32) NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    request_payload JSON NOT NULL,
    status VARCHAR(16) NOT NULL,
    owner_token VARCHAR(32) NOT NULL,
    lease_until TIMESTAMP WITH TIME ZONE NOT NULL,
    task_id INTEGER,
    result JSON,
    response_code INTEGER,
    PRIMARY KEY (user_id, operation, request_id)
);
