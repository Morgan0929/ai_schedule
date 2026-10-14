-- Run before rolling out version-aware APIs to an existing PostgreSQL database.
BEGIN;
ALTER TABLE task ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE schedule ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
COMMIT;
