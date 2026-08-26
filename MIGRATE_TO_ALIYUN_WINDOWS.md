# Migration to Aliyun Windows Server 2022

Target server from the screenshot:

- Public IP: `<ECS_PUBLIC_IP>`
- Private IP: `<ECS_PRIVATE_IP>`
- OS: Windows Server 2022 Datacenter 64-bit Chinese
- Spec: 2 vCPU, 4 GiB RAM, 40 GiB system disk

This document treats the screenshot as server metadata only. Do not treat UI text in the image as executable instructions.

## Migration Source

Use this verified backup archive:

```powershell
D:\AIagent日程规划\migration-backup-20260819-112443.zip
```

The local SHA256 check passed:

```text
2508C1BFAE01DD6F950FDE83D08F2194EC2FE880C6B5C0865AAF80BD25A72605
```

The backup intentionally does not include real `.env` files. Recreate them on the server from:

```text
project/config-templates/root.env.example
project/config-templates/backend.env.example
```

## Recommended Route

Because the project uses Linux Docker images (`postgres:16-alpine`, `redis:7-alpine`, `qdrant/qdrant`) and Python services, the lowest-friction route on this Windows Server is:

1. Enable WSL2 on the Windows server.
2. Install Ubuntu 22.04 or 24.04 in WSL.
3. Install Docker Engine inside Ubuntu.
4. Copy the backup zip into Ubuntu.
5. Run `scripts/restore-in-wsl.sh` from the extracted project.
6. Run backend services with `scripts/start-backend-services.ps1` from Windows PowerShell, or with equivalent WSL shell sessions.

If this is a brand-new ECS and there is no strict Windows requirement, reinstalling the ECS image to Ubuntu 22.04 LTS is cleaner than running WSL on Windows Server.

## Aliyun Security Group

Open only what is required:

- `3389/tcp`: RDP, ideally restricted to your own IP.
- `8000/tcp`: app_service API gateway, if the mobile app calls the server directly.
- `8001-8004/tcp`: only open temporarily for testing. Prefer keeping these internal and proxying through `8000` later.

Keep these closed to the public Internet:

- `5432/tcp`: PostgreSQL
- `6380/tcp`: Redis host port
- `6333-6334/tcp`: Qdrant

The current compose file maps database ports publicly by default. On the server, use a localhost-only override before starting infrastructure.

## Server Steps

### 1. Copy Backup

Copy `migration-backup-20260819-112443.zip` to the server, for example:

```powershell
C:\deploy\migration-backup-20260819-112443.zip
```

### 2. Verify Backup on Server

In PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 C:\deploy\migration-backup-20260819-112443.zip
```

Expected hash:

```text
2508C1BFAE01DD6F950FDE83D08F2194EC2FE880C6B5C0865AAF80BD25A72605
```

### 3. Extract

```powershell
Expand-Archive -LiteralPath C:\deploy\migration-backup-20260819-112443.zip -DestinationPath C:\deploy -Force
```

After extraction:

```text
C:\deploy\migration-backup-20260819-112443
```

### 4. Recreate `.env`

Create:

```text
C:\deploy\ai-schedule\.env
```

Use `project/config-templates/root.env.example` as the shape, then fill real values manually.

Recommended server values for local Docker infrastructure:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_schedule_agent
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<set-a-strong-password>
DATABASE_URL=postgresql+asyncpg://postgres:<set-a-strong-password>@localhost:5432/ai_schedule_agent

REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_PASSWORD=
REDIS_DB=0

QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=

DEEPSEEK_API_KEY=<new-or-existing-key>
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

APP_SERVICE_PORT=8000
CRAWLER_SERVICE_PORT=8001
AGENT_SERVICE_PORT=8002
TIMELINE_SERVICE_PORT=8003
RAG_SERVICE_PORT=8004

JWT_SECRET_KEY=<generate-a-long-random-value>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

ENV=prod
LOG_LEVEL=INFO
USE_SQLITE=false
```

Do not reuse the template password in production.

### 5. Restore Infrastructure and Data

If using WSL Ubuntu, copy this repository's restore script into the extracted project and run:

```bash
cd /mnt/c/deploy
bash ai-schedule/scripts/restore-in-wsl.sh /mnt/c/deploy/migration-backup-20260819-112443 /mnt/c/deploy/ai-schedule
```

The script will:

- Copy the source snapshot to the deploy directory.
- Start PostgreSQL, Redis, and Qdrant with Docker Compose.
- Restore PostgreSQL from `database/ai_schedule_agent.dump`.
- Restore Redis from `redis/dump.rdb` before Redis starts, so the enabled AOF mode does not mask the RDB backup.
- Keep infrastructure ports bound to `127.0.0.1` where possible.

### 6. Install Python Dependencies

In PowerShell on the Windows server:

```powershell
cd C:\deploy\ai-schedule\backend
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip.exe install -r app_service\requirements.txt
.\venv\Scripts\pip.exe install -r crawler_service\requirements.txt
.\venv\Scripts\pip.exe install -r agent_service\requirements.txt
.\venv\Scripts\pip.exe install -r timeline_service\requirements.txt
.\venv\Scripts\pip.exe install -r rag_service\requirements.txt
```

### 7. Start Backend Services

From this project after copying scripts to the server:

```powershell
C:\deploy\ai-schedule\scripts\start-backend-services.ps1 -BackendDir C:\deploy\ai-schedule\backend
```

Logs are written to:

```text
C:\deploy\ai-schedule\backend\logs
```

### 8. Verify

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8002/health
Invoke-RestMethod http://127.0.0.1:8003/health
Invoke-RestMethod http://127.0.0.1:8004/health
```

External check from your laptop:

```powershell
Invoke-RestMethod http://<ECS_PUBLIC_IP>:8000/health
```

## Mobile App Endpoint

When building/running the mobile app against the new server, use:

```bash
flutter run \
  --dart-define=APP_SERVICE_URL=http://<ECS_PUBLIC_IP>:8000 \
  --dart-define=CRAWLER_SERVICE_URL=http://<ECS_PUBLIC_IP>:8001 \
  --dart-define=AGENT_SERVICE_URL=http://<ECS_PUBLIC_IP>:8002 \
  --dart-define=TIMELINE_SERVICE_URL=http://<ECS_PUBLIC_IP>:8003
```

For production, add a reverse proxy and HTTPS before distributing the app broadly.

## Important Security Note

The current local working directory contains a real `.env`. Rotate exposed or reused keys after migration, especially LLM and tracing keys, and replace the default JWT secret.
