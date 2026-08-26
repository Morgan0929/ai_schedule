# Production Deployment Checklist

This directory contains the production entrypoint configuration for the Ubuntu ECS.

`ai-schedule-http.conf.example` is only a temporary IP-based validation gateway. Use the HTTPS configuration after a real domain has been registered and its DNS record points to the ECS.

For temporary public-IP validation, add an Aliyun security-group inbound rule for `80/tcp` to `<ECS_PUBLIC_IP>`. The host UFW rule is already present. Do not expose `8000-8004` directly.

## Required values from the operator

- SSH host, port, username, and an existing private-key path on the deployment machine.
- A DNS name pointing to `<ECS_PUBLIC_IP>` for HTTPS. `<YOUR_DOMAIN>` is currently pointed at the ECS.
- Production values for `POSTGRES_PASSWORD`, `DATABASE_URL`, `JWT_SECRET_KEY`, and `DEEPSEEK_API_KEY`.
- Whether the first release should create a bootstrap admin account. Leave `BOOTSTRAP_ADMIN_*` empty when it should not.

Do not commit or send secret values in this repository.

## Server sequence

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
cd /srv/ai-schedule
sudo bash scripts/install-systemd-services.sh /srv/ai-schedule
sudo cp deploy/nginx/ai-schedule.conf.example /etc/nginx/sites-available/ai-schedule
sudo ln -sf /etc/nginx/sites-available/ai-schedule /etc/nginx/sites-enabled/ai-schedule
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d <YOUR_DOMAIN>
```

Before enabling HTTPS, make sure DNS resolves to the ECS. Open only `22`, `80`, and `443` in the Aliyun security group. Keep ports `8000-8004`, `5432`, `6380`, and `6333-6334` private.

## Mobile build

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://<YOUR_DOMAIN>
```

The app will use the same base URL for auth, agent, timeline, and crawler calls. The Nginx path rules select the internal service.
