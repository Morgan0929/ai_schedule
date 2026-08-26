#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="${1:-/srv/ai-schedule/backend}"
LOG_DIR="$BACKEND_DIR/logs"
PYTHON="$BACKEND_DIR/venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python venv not found: $PYTHON" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

services=(
  "app_service.main:app:8000:app-service:0.0.0.0"
  "crawler_service.main:app:8001:crawler-service:127.0.0.1"
  "agent_service.main:app:8002:agent-service:127.0.0.1"
  "timeline_service.main:app:8003:timeline-service:127.0.0.1"
  "rag_service.main:app:8004:rag-service:127.0.0.1"
)

for item in "${services[@]}"; do
  IFS=':' read -r module attr port name host <<< "$item"
  if ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "$name already listening on $port, skipping"
    continue
  fi

  nohup "$PYTHON" -m uvicorn "$module:$attr" --host "$host" --port "$port" > "$LOG_DIR/$name.out.log" 2> "$LOG_DIR/$name.err.log" &
  echo $! > "$LOG_DIR/$name.pid"
  echo "started $name on $port"
done

sleep 3

for port in 8000 8001 8002 8003 8004; do
  url="http://127.0.0.1:$port/health"
  if curl -fsS --max-time 5 "$url" >/dev/null; then
    echo "$url OK"
  else
    echo "$url not ready"
  fi
done
