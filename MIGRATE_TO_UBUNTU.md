# Migration to Ubuntu 22.04 / 24.04

This is the recommended path for the new ECS instance.

## Current Stage

Migration status: completed on the Ubuntu ECS.

- Ubuntu 22.04 LTS is installed.
- PostgreSQL, Redis, and Qdrant have been restored.
- Backend services are running on the server.
- Database and vector infrastructure are bound to localhost.
- `8001`-`8004` are bound to localhost.
- `8000` is reserved as the public API entry, but the Aliyun security group still needs the matching inbound rule if you want it reachable from outside.

Remaining production work:

- Add the Aliyun security group inbound rules for `80` and `443`.
- Configure the Nginx template at `deploy/nginx/ai-schedule.conf.example`.
- Install the systemd units with `scripts/install-systemd-services.sh`.
- Issue an HTTPS certificate and build the mobile app with one `API_BASE_URL`.

## Target

- ECS public IP: `<ECS_PUBLIC_IP>`
- ECS instance ID: `<ECS_INSTANCE_ID>`
- Current backup source:
  - `D:\AIagent日程规划\migration-backup-20260819-112443`
  - `D:\AIagent日程规划\migration-backup-20260819-112443.zip`

## Why Ubuntu

The backend stack is already Linux-oriented:

- PostgreSQL 16
- Redis 7
- Qdrant
- Python async services
- Flutter mobile app companion

Running the project on Ubuntu avoids the extra layer of Windows Server + WSL and is the cleanest restore path.

## Before Reimage

Use the Aliyun console to reinstall the system disk to Ubuntu 22.04 LTS or 24.04 LTS.

Recommended choice:

- Ubuntu 22.04 LTS if you want maximum package stability
- Ubuntu 24.04 LTS if you want the newest base image and are comfortable with slightly newer defaults

Keep the data backup outside the system disk, or upload it again after reinstall.

## Security Group

Open only what you need:

- `22/tcp` for SSH
- `80/tcp` and `443/tcp` if you add a reverse proxy
- `8000/tcp` temporarily for direct API access

For the final deployment, expose `80/tcp` and `443/tcp` for Nginx instead of exposing the internal service ports.

Keep these private:

- `5432/tcp`
- `6380/tcp`
- `6333-6334/tcp`

## Server Prep

After reinstall, SSH in as root or your sudo user and install dependencies:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release unzip rsync
```

Install Docker Engine with the official Ubuntu packages, then add your user to the `docker` group.

## Restore Flow

1. Copy `migration-backup-20260819-112443.zip` to the server, for example `/srv/deploy/`.
2. Verify the SHA256 hash.
3. Extract the archive.
4. Copy `project/source` to the deploy root.
5. Create a real `.env` from `project/config-templates/root.env.example` and `backend.env.example`.
6. Run `scripts/restore-on-ubuntu.sh`.
7. Start the backend services with `scripts/start-backend-services.sh`.

For a persistent production deployment, use:

```bash
sudo bash scripts/install-systemd-services.sh /srv/ai-schedule
```

The service units bind all Python services to `127.0.0.1`. Nginx routes `/api/v1/auth` to port `8000`, `/api/v1/crawl` to `8001`, `/api/v1/agent` to `8002`, `/api/v1/` to `8003`, and `/api/v1/rag` to `8004`.

## Example Paths

Backup archive on server:

```text
/srv/deploy/migration-backup-20260819-112443.zip
```

Deploy root:

```text
/srv/ai-schedule
```

## Environment File

The backup intentionally excludes real secrets.

Create a real `/srv/ai-schedule/.env` using the templates from the backup and fill in current values manually.

Do not reuse the placeholder passwords from the templates.

## Verify

After restore, check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/health
curl http://127.0.0.1:8003/health
curl http://127.0.0.1:8004/health
```

External check:

```bash
curl http://<ECS_PUBLIC_IP>:8000/health
```

If the public `8000` check fails while local checks pass, the server is healthy and the remaining block is the cloud security group, not the app stack.
