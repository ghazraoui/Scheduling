# Scheduling — Teacher Calendar Management

Manages teacher Outlook calendar synchronization for Swiss Learning Group. Scrapes schedule data from SparkSource (via Playwright) and pushes it to teacher Microsoft 365 Outlook calendars, so the UI app can query teacher availability when processing VIP student requests.

## How It Fits

```
Scheduling (this project)                                    UI App
(scrape SparkSource + sync to Outlook calendars)    →    (query calendars)
  scrape_schedules.py      sync_calendars.py                vip_planner.py
  src/scraper/             sync_private_calendars.py
                           config.py (Graph API auth)
```

| Project | Location | Role |
|---------|----------|------|
| **Scheduling** (this) | `C:\Users\zackg\OneDrive\Desktop\AI Projects\Scheduling` | Scrapes SparkSource + syncs to teacher Outlook calendars via Graph API |
| **UI** | `C:\Users\zackg\OneDrive\Desktop\Work\SLG\APPS\UI` | Streamlit app — queries Outlook calendars for VIP teacher matching |

## Project Structure

```
Scheduling/
├── CLAUDE.md
├── pyproject.toml                 # Project metadata + dependencies
├── .env.example                   # Template for secrets (SparkSource + Azure AD)
├── .planning/
│   └── STATE.md
├── src/
│   └── scraper/                   # SparkSource schedule scraper (extracted from Student Follow Up)
│       ├── __init__.py
│       ├── config.py              # Scraper config (pydantic-settings, loads from .env)
│       ├── errors.py              # Error hierarchy for retry classification
│       ├── logging.py             # Structured logging (structlog)
│       ├── models.py              # ScheduleEntry pydantic model
│       ├── session.py             # Playwright session management + auth
│       ├── utils.py               # Resource blocking + read-only guardrails
│       └── pages/
│           ├── __init__.py
│           └── schedule.py        # SchedulePage — weekly schedule extraction + week navigation
├── .github/
│   └── workflows/
│       └── deploy.yml             # GitHub Actions: on push to deploy → webhook → VPS git pull
├── scripts/
│   ├── deploy_webhook.py          # Deploy webhook listener (localhost:9000, Nginx proxied)
│   ├── config.py                  # Azure AD credentials (from .env) + Graph API helpers
│   ├── diff_sync.py               # V2 diff engine: compare old/new state, apply targeted changes
│   ├── scrape_schedules.py        # Scrape SparkSource schedules (--weeks N for multi-week)
│   ├── sync_calendars.py          # Sync method classes → recurring events (diff-based, --agenda)
│   ├── sync_private_calendars.py  # Sync private lessons → one-time events (diff-based, --agenda)
│   ├── sync_method.sh             # V2 wrapper: scrape + diff-sync one method school
│   ├── sync_vip.sh                # V2 wrapper: scrape + diff-sync all 3 VIP agendas (3 weeks)
│   ├── run_full_sync.sh           # V1 full pipeline (kept as fallback)
│   ├── provision_teachers.py      # Create M365 teacher accounts + assign A1 licenses
│   ├── parse_teachers.py          # Extract teacher data from .docx → teachers.json
│   ├── tenant_recon.py            # Query tenant info (org, licenses, users, domains)
│   └── tenant_review.py          # Generate tenant account review report
├── data/
│   ├── teachers.json              # 56 teachers (name, phone, email, tags, section)
│   ├── Teachers.xlsx              # Teacher directory (also on SharePoint)
│   ├── sparksource-schedules.md   # Reference: all 28 SparkSource agendas
│   ├── last_synced/               # V2 state files: synced events with Outlook IDs (gitignored)
│   ├── teacher-schedule-sfs_lausanne.json                       # SFS method (20 teachers, 69 slots)
│   ├── teacher-schedule-esa_lausanne.json                       # ESA method (15 teachers, 55 slots)
│   ├── teacher-schedule-private_english_lausanne-detailed.json   # Private English detailed (85 classes)
│   ├── teacher-schedule-private_french_lausanne-detailed.json    # Private French detailed (113 classes)
│   └── teacher-schedule-private_german_lausanne-detailed.json    # Private German detailed (108 classes)
├── docs/
│   ├── deployment.md              # Deploy workflow and VPS details
│   ├── scripts.md                 # All scripts with CLI examples
│   ├── sync-architecture.md       # V2 diff-based sync engine
│   ├── azure.md                   # Azure app registration and teacher accounts
│   └── setup.md                   # Credentials and environment setup
└── reports/                       # Sync and provisioning reports (timestamped JSON)
```

## Quick Start

See [docs/setup.md](docs/setup.md) for full installation instructions.

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # Fill in credentials

# Scrape + sync method classes
scripts/sync_method.sh sfs_lausanne

# Scrape + sync VIP lessons (3 weeks)
scripts/sync_vip.sh
```

## Documentation

- [Setup & Credentials](docs/setup.md)
- [Deployment Guide](docs/deployment.md)
- [Scripts Reference](docs/scripts.md)
- [Sync Architecture (V2)](docs/sync-architecture.md)
- [Azure Configuration](docs/azure.md)
- [SparkSource Agendas](data/sparksource-schedules.md)

## History

- Project originally created as "VIPs" — codebase behind an n8n workflow for VIP teacher assignment
- VIP matching logic migrated to UI app (`vip_planner.py`) on 2026-02-24 — n8n workflow retired
- Project repurposed as "Scheduling" — focused on teacher calendar management
- Method class sync completed 2026-02-24: 34 teachers, 124 recurring events
- Private lesson sync completed 2026-02-25: 43 teachers, 306 one-time events
- SparkSource scraper extracted from Student Follow Up into `src/scraper/` on 2026-02-27 — project fully self-contained
- Azure credentials migrated from hardcoded values to `.env` on 2026-02-27
- V2 implemented 2026-02-27: diff-based sync, multi-week scraping, per-agenda cron scripts
