#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-}"
DEPLOY_DIR="${2:-/srv/ai-schedule}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

if [[ -z "$BACKUP_DIR" ]]; then
  echo "Usage: bash scripts/restore-on-ubuntu.sh <backup-dir> [deploy-dir]" >&2
  exit 2
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "Backup directory not found: $BACKUP_DIR" >&2
  exit 1
fi

if [[ -z "$POSTGRES_PASSWORD" ]]; then
  echo "Set POSTGRES_PASSWORD to the production PostgreSQL password before restoring." >&2
  exit 1
fi

if [[ ! -f "$BACKUP_DIR/database/ai_schedule_agent.dump" ]]; then
  echo "Missing PostgreSQL dump: $BACKUP_DIR/database/ai_schedule_agent.dump" >&2
  exit 1
fi

if [[ ! -f "$BACKUP_DIR/redis/dump.rdb" ]]; then
  echo "Missing Redis dump: $BACKUP_DIR/redis/dump.rdb" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required" >&2
  exit 1
fi

mkdir -p "$DEPLOY_DIR"
rsync -a --delete \
  --exclude '.env' \
  --exclude 'venv' \
  --exclude '.dart_appdata' \
  --exclude '.dart_localappdata' \
  "$BACKUP_DIR/project/source/" "$DEPLOY_DIR/"

cd "$DEPLOY_DIR"

if [[ ! -f .env ]]; then
  echo ".env is missing in $DEPLOY_DIR" >&2
  echo "Create it from project/config-templates/root.env.example before continuing." >&2
  exit 1
fi

echo "Starting PostgreSQL and Qdrant..."
docker compose up -d postgres qdrant

echo "Waiting for PostgreSQL..."
until docker exec ai-schedule-postgres pg_isready -U postgres >/dev/null 2>&1; do
  sleep 2
done

echo "Restoring PostgreSQL globals..."
docker cp "$BACKUP_DIR/database/postgres_globals.sql" ai-schedule-postgres:/tmp/postgres_globals.sql
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" ai-schedule-postgres psql -U postgres -f /tmp/postgres_globals.sql || true

echo "Recreating application database..."
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" ai-schedule-postgres psql -U postgres -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'ai_schedule_agent' AND pid <> pg_backend_pid();" || true
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" ai-schedule-postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ai_schedule_agent;"
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" ai-schedule-postgres psql -U postgres -d postgres -c "CREATE DATABASE ai_schedule_agent;"

echo "Restoring PostgreSQL dump..."
docker cp "$BACKUP_DIR/database/ai_schedule_agent.dump" ai-schedule-postgres:/tmp/ai_schedule_agent.dump
docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" ai-schedule-postgres pg_restore -U postgres -d ai_schedule_agent --no-owner --no-privileges /tmp/ai_schedule_agent.dump

echo "Preparing Redis volume..."
docker compose stop redis >/dev/null 2>&1 || true
docker volume create ai_schedule_redis_data >/dev/null
docker run --rm \
  -v ai_schedule_redis_data:/data \
  -v "$BACKUP_DIR/redis:/backup:ro" \
  redis:7-alpine \
  sh -c 'rm -rf /data/appendonlydir /data/dump.rdb && cp /backup/dump.rdb /data/dump.rdb'

echo "Starting Redis and the rest of the infrastructure..."
docker compose up -d

echo "Restore complete. Check status with:"
echo "docker compose ps"
