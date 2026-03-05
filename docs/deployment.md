# Deployment Guide

## Overview

**GitHub repo**: `ghazraoui/Scheduling` (private)

```
Local PC (develop on main)  →  merge to deploy branch  →  GitHub Actions curls VPS webhook → git pull
```

- **Develop locally** on `main` — edit code with Claude on this PC
- **Push to `main`** — version control, test changes
- **Merge `main` → `deploy`** — triggers auto-deploy via GitHub Actions
- **GitHub Actions** POSTs to VPS webhook with shared secret
- **Webhook listener** (`scripts/deploy_webhook.py`) runs `git pull origin deploy`
- **VPS** at `/opt/slg/scheduling/` tracks the `deploy` branch

## Deploy Workflow

```bash
# Normal deploy cycle:
git push origin main               # push your changes
git checkout deploy                 # switch to deploy branch
git merge main                     # merge main into deploy
git push origin deploy              # triggers GitHub Actions → VPS webhook → git pull
git checkout main                   # switch back to develop

# Or merge from GitHub UI:
# Create PR: main → deploy, merge it
```

**GitHub Actions workflow**: `.github/workflows/deploy.yml`
- Trigger: push to `deploy` branch
- Action: POST to `https://swisslanguagegroup.cloud/webhook/deploy-scheduling`
- Secret: `DEPLOY_WEBHOOK_SECRET` (shared between GitHub and VPS)

**Webhook listener**: `scripts/deploy_webhook.py`
- Runs on `127.0.0.1:9000`, Nginx proxies HTTPS traffic to it
- Validates `X-Deploy-Token` header against `DEPLOY_SECRET` env var
- Runs `git pull origin deploy` in `/opt/slg/scheduling/`
- Systemd service: `scheduling-deploy-webhook.service`
- Health check: `curl http://localhost:9000/health`

## VPS Details

| | |
|---|---|
| **Server** | Hostinger KVM 4 — `187.124.12.175` (`swisslanguagegroup.cloud`) |
| **Path** | `/opt/slg/scheduling/` (git clone) |
| **Runtime** | Python 3.13 venv at `.venv/`, Playwright + Chromium headless |
| **Credentials** | `.env` on VPS only (gitignored) — SparkSource + Azure AD |
| **Logs** | `journalctl -u scheduling-*` (systemd journal) |
| **Timers** | Systemd: method-sfs (Thu 12:00 CET), method-esa (Fri 12:00 CET), vip (every 2h Mon-Sat 07-19 CET) |
| **Scripts** | `sync_method.sh`, `sync_vip.sh` (v2), `run_full_sync.sh` (v1 fallback) |
| **Timer management** | `systemctl list-timers scheduling-*`, `systemctl status scheduling-vip` |

## Deploying Changes

Merge `main` → `deploy` and push. GitHub Actions handles the rest.

```bash
# If dependencies changed, SSH into VPS manually:
cd /opt/slg/scheduling
.venv/bin/pip install -r requirements.txt
```
