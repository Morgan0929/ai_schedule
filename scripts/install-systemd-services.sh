#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-/srv/ai-schedule}"
SOURCE_DIR="$PROJECT_DIR/deploy/systemd"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script as root or with sudo." >&2
  exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Deployment files not found: $SOURCE_DIR" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "Missing production environment file: $PROJECT_DIR/.env" >&2
  exit 1
fi

if ! id ai-schedule >/dev/null 2>&1; then
  useradd --system --home-dir "$PROJECT_DIR" --shell /usr/sbin/nologin ai-schedule
fi

mkdir -p "$PROJECT_DIR/backend/uploads"
chown ai-schedule:ai-schedule "$PROJECT_DIR/.env"
chmod 0600 "$PROJECT_DIR/.env"
chown -R ai-schedule:ai-schedule "$PROJECT_DIR/backend/uploads"

install -m 0644 "$SOURCE_DIR"/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now \
  ai-schedule-app.service \
  ai-schedule-crawler.service \
  ai-schedule-agent.service \
  ai-schedule-timeline.service \
  ai-schedule-rag.service

systemctl --no-pager --full status \
  ai-schedule-app.service \
  ai-schedule-crawler.service \
  ai-schedule-agent.service \
  ai-schedule-timeline.service \
  ai-schedule-rag.service
