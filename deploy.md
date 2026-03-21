Deployment Guide (systemd + gunicorn + nginx)
=============================================

Prerequisites
- Ubuntu/Debian host with Python 3.11+, systemd, nginx.
- App checked out to `/opt/amw_analytics` (adjust paths as needed).
- `.env` file with production secrets (SECRET_KEY, DB creds, etc.) stored in `/etc/amw_analytics.env`.

Install dependencies
```bash
sudo apt-get update && sudo apt-get install -y python3-venv nginx
cd /opt/amw_analytics
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Gunicorn
- Config: `gunicorn_conf.py` (binds unix socket `run/gunicorn.sock`, workers, timeouts).
- Run manually for smoke:
```bash
. .venv/bin/activate
gunicorn -c gunicorn_conf.py "app:create_app()"
```

systemd service
- Unit file: `deploy/amw_analytics.service` (EnvironmentFile=/etc/amw_analytics.env, WorkingDirectory=/opt/amw_analytics).
- Install:
```bash
sudo cp deploy/amw_analytics.service /etc/systemd/system/amw_analytics.service
sudo systemctl daemon-reload
sudo systemctl enable --now amw_analytics
sudo systemctl status amw_analytics
```

nginx
- Site config: `deploy/nginx_amw.conf` (serves `/static`, proxies `/` to unix socket, sensible timeouts, gzip).
- Install:
```bash
sudo cp deploy/nginx_amw.conf /etc/nginx/sites-available/amw_analytics
sudo ln -s /etc/nginx/sites-available/amw_analytics /etc/nginx/sites-enabled/amw_analytics
sudo nginx -t && sudo systemctl reload nginx
```

Health + logs
- Liveness: `GET /healthz`
- Readiness: `GET /readyz`
- App logs: `logs/app.jsonl` (rotating). systemd: `journalctl -u amw_analytics -f`
- nginx: `/var/log/nginx/access.log`, `/var/log/nginx/error.log`

Rolling restart
```bash
sudo systemctl restart amw_analytics
sudo systemctl reload nginx
```
