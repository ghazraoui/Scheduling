# Scheduling — Teacher Calendar Management

## Overview

This project manages teacher Outlook calendar synchronization for Swiss Learning Group. It scrapes schedule data from SparkSource (via its own built-in Playwright scraper) and pushes it to teacher Microsoft 365 Outlook calendars, so the UI app can query teacher availability when processing VIP student requests.

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

## Deployment

**GitHub repo**: `ghazraoui/Scheduling` (private)

```
Local PC (develop on main)  →  merge to deploy branch  →  GitHub Actions auto-SSHs into VPS + git pull
```

- **Develop locally** on `main` — edit code with Claude on this PC
- **Push to `main`** — version control, test changes
- **Merge `main` → `deploy`** — triggers auto-deploy via GitHub Actions
- **GitHub Actions** SSHs into VPS, runs `git pull origin deploy`
- **VPS** at `/opt/slg/scheduling/` tracks the `deploy` branch

### Deploy workflow

```bash
# Normal deploy cycle:
git push origin main               # push your changes
git checkout deploy                 # switch to deploy branch
git merge main                     # merge main into deploy
git push origin deploy              # triggers GitHub Actions → VPS auto-pulls
git checkout main                   # switch back to develop

# Or merge from GitHub UI:
# Create PR: main → deploy, merge it
```

**GitHub Actions workflow**: `.github/workflows/deploy.yml`
- Trigger: push to `deploy` branch
- Action: SSH into VPS via `appleboy/ssh-action`, `git pull origin deploy`
- Secrets: `VPS_SSH_KEY`, `VPS_HOST`, `VPS_USER`

### VPS Details

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

### Deploying Changes

Merge `main` → `deploy` and push. GitHub Actions handles the rest.

```bash
# If dependencies changed, SSH into VPS manually:
cd /opt/slg/scheduling
.venv/bin/pip install -r requirements.txt
```

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
├── scripts/
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
│   └── tenant_review.py           # Generate tenant account review report
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
└── reports/                       # Sync and provisioning reports (timestamped JSON)
```

## Scripts

### `config.py` — Shared Graph API Helpers

Imported by all other scripts. Provides:
- `get_token()` — app-only access token via client credentials
- `graph_get()`, `graph_get_all()`, `graph_post()`, `graph_delete()` — Graph API wrappers
- `resolve_license_sku()` — look up A1 Faculty license SKU ID
- `CALENDAR_EVENT_SUBJECT = "Teaching"` — subject prefix for method class events
- Azure AD credentials loaded from `.env` (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_DOMAIN`)

### `scrape_schedules.py` — SparkSource Schedule Scraper

Scrapes teacher schedules from SparkSource using Playwright. Self-contained replacement for the Student Follow Up project dependency.

```bash
python scripts/scrape_schedules.py --weekly-teachers --agenda sfs_lausanne           # method classes (1 week)
python scripts/scrape_schedules.py --weekly-detailed --agenda private_english_lausanne # private lessons (1 week)
python scripts/scrape_schedules.py --weekly-detailed --agenda private_english_lausanne --weeks 3  # 3 weeks ahead
python scripts/scrape_schedules.py --table --agenda esa_lausanne                      # today's schedule as table
python scripts/scrape_schedules.py --headed                                            # debug with visible browser
```

- Uses `src/scraper/` module (SchedulePage, session management, read-only guardrails)
- Supports all agendas: `sfs_lausanne`, `esa_lausanne`, `private_english_lausanne`, etc.
- `--weeks N`: scrape N consecutive weeks (default: 1). Used by VIP sync to get 3 weeks ahead.
- Week navigation via URL: `/ffdates/week/booking/YYYY/MM/DD/` — any date shows its containing Mon-Sat week
- Outputs JSON files to `data/` directory (same format as sync scripts expect)
- SparkSource credentials loaded from `.env` (`SPARKSOURCE_URL`, `SPARKSOURCE_USER`, `SPARKSOURCE_PASS`)

### `diff_sync.py` — Diff Engine (V2)

Core diff engine for V2 sync. Compares new schedule data against last-synced state and produces targeted Graph API operations.

- `load_last_synced(agenda)` / `save_synced_state(agenda, sync_type, events)` — state file I/O
- `compute_method_diff(old, new)` — identity key: (upn, day, start_time)
- `compute_vip_diff(old, new)` — identity key: (upn, date, start_time, activity_code)
- `apply_method_diff()` / `apply_vip_diff()` — execute Graph API calls for diff
- `merge_synced_events()` — combine unchanged + new events for state persistence
- State files: `data/last_synced/{agenda}.json` (gitignored)
- First run (no state): full clear + create (same as V1), then saves state

### `sync_calendars.py` — Method Class Sync

Syncs SFS + ESA method class schedules as **recurring weekly** "Teaching" events. V2: diff-based sync.

```bash
python scripts/sync_calendars.py                              # dry-run (all agendas)
python scripts/sync_calendars.py --agenda sfs_lausanne         # dry-run (single agenda)
python scripts/sync_calendars.py --execute                     # diff-sync all agendas
python scripts/sync_calendars.py --agenda sfs_lausanne --execute  # diff-sync single agenda
python scripts/sync_calendars.py --clear-only                  # remove all "Teaching" events
```

- Reads: `data/teacher-schedule-{sfs,esa}_lausanne.json`
- Creates: weekly recurring events, `showAs: busy`, no end date
- Subject: `Teaching`
- **V2**: Diff-based — only creates/deletes what changed. State in `data/last_synced/`
- `--agenda`: sync a single school (for per-agenda cron jobs)
- First run (no state file): full clear + create (like V1), saves state for future diffs

### `sync_private_calendars.py` — Private Lesson Sync

Syncs private/VIP lessons as **one-time dated** events with type-specific subjects and Outlook color categories. V2: diff-based sync.

```bash
python scripts/sync_private_calendars.py                                          # dry-run (all agendas)
python scripts/sync_private_calendars.py --agenda private_english_lausanne         # dry-run (single agenda)
python scripts/sync_private_calendars.py --execute                                 # diff-sync all agendas
python scripts/sync_private_calendars.py --agenda private_english_lausanne --execute  # diff-sync single agenda
python scripts/sync_private_calendars.py --clear-only                              # remove all "Private:" events
```

- Reads: `data/teacher-schedule-private_*_lausanne-detailed.json`
- Creates: single-occurrence events per class, each with activity type subject and color category
- Subject format: `Private: VAD - VIP Adults` or `Private: VAD - VIP Adults (Online)`
- **V2**: Diff-based — only creates/deletes what changed. State in `data/last_synced/`
- `--agenda`: sync a single school (for per-agenda cron jobs)

### `sync_method.sh` — Method Class Pipeline (V2)

Wrapper script: scrapes one method school + diff-syncs to Outlook.

```bash
scripts/sync_method.sh sfs_lausanne   # scrape SFS + diff-sync
scripts/sync_method.sh esa_lausanne   # scrape ESA + diff-sync
```

### `sync_vip.sh` — VIP Pipeline (V2)

Wrapper script: scrapes all 3 VIP agendas (3 weeks ahead) + diff-syncs to Outlook.

```bash
scripts/sync_vip.sh   # scrape English/French/German private (3 weeks) + diff-sync
```

### `provision_teachers.py` — Account Provisioning

Creates Microsoft 365 accounts for teachers and assigns A1 Faculty licenses.

```bash
python scripts/provision_teachers.py --dry-run  # preview
python scripts/provision_teachers.py --execute  # create accounts
```

- Reads: `data/teachers.json`
- UPN format: `firstname.lastname@swisslearninggroup.onmicrosoft.com`
- License: Office 365 A1 for faculty (SKU: `STANDARDWOFFPACK_FACULTY`)

## Calendar Event Types

Two distinct types of events, managed by separate scripts with separate subject prefixes:

| Type | Script | Subject | Recurrence | Systemd timer |
|------|--------|---------|------------|---------------|
| Method classes | `sync_method.sh` | `Teaching` | Weekly (no end date) | `scheduling-method-sfs.timer` Thu, `scheduling-method-esa.timer` Fri |
| Private lessons | `sync_vip.sh` | `Private: {type}` | One-time (dated, 3 weeks) | `scheduling-vip.timer` every 2h Mon-Sat |

### Private Lesson Activity Types

| Code | Label | Outlook Color | Preset |
|------|-------|---------------|--------|
| VAD | VIP Adults | Purple | preset8 |
| TPC | Test Prep | Red | preset0 |
| JPR | Junior Private | Blue | preset7 |
| JGP | Junior Group | Green | preset4 |
| ICO | In Company | Orange | preset1 |
| VIP | VIP Class | Yellow | preset3 |

## Schedule Data Formats

### Method class schedule (recurring)

```json
{ "Teacher NAME": [{ "day": "Monday", "start": "09:00", "end": "12:00" }, ...] }
```

### Private lesson schedule (detailed, dated)

```json
{ "Teacher NAME": [{ "date": "2026-02-25", "start": "09:00", "end": "10:00", "type": "VAD", "name": "VIP Adults", "online": false }, ...] }
```

Schedule data is scraped using the built-in scraper:
- `python scripts/scrape_schedules.py --weekly-teachers` for method classes
- `python scripts/scrape_schedules.py --weekly-detailed` for private lessons (preserves date, type, online flag)

## SparkSource Name Matching

Both sync scripts share name-matching logic from `sync_calendars.py`:

- `clean_sparksource_name()`: strips known tokens (MAIN, CR, ESA, SFS, WSE, VIP, TP, VAD, TPC, JPR, JGP, JNR, ICO), handles slash-separated tokens (e.g. "Emily VIP/TP TAYLOR"), normalises case
- `build_teacher_lookup()`: exact match (accent-stripped) + fuzzy match (first 3 chars firstname + first 4 chars lastname)
- `match_teacher()`: tries skip list → hardcoded overrides → exact → fuzzy
- SparkSource names are the source of truth for spelling

## SparkSource Agendas

See `data/sparksource-schedules.md` for the full reference of all 28 SparkSource agendas. Key Lausanne agendas:

| Agenda | ID | Type | Status |
|--------|-----|------|--------|
| SFS Lausanne | 17 | Method classes | Synced |
| ESA Lausanne | 18 | Method classes | Synced |
| Private English Lausanne | 57 | Private/VIP | Synced |
| Private French Lausanne | 100 | Private/VIP | Synced |
| Private German Lausanne | 101 | Private/VIP | Synced |

## Teacher Accounts

- **56 teachers** total: 40 Lausanne (In Person) + 16 Online
- UPN format: `firstname.lastname@swisslearninggroup.onmicrosoft.com`
- License: Office 365 A1 for faculty (SKU: `STANDARDWOFFPACK_FACULTY`)
- Temp passwords stored in `reports/provision_*.json`

## Azure App Registration

App ID: `63a2f848-ceb5-497f-aed2-3936893c3247`

| Permission (Application) | Purpose |
|--------------------------|---------|
| `User.Read.All` | Read tenant users |
| `User.ReadWrite.All` | Create users + assign licenses |
| `Organization.Read.All` | Read subscribed SKUs (license lookup) |
| `Calendars.ReadWrite` | Create/delete events on teacher calendars |
| `Files.Read.All` | Read SharePoint Excel (teacher directory) |
| `Tasks.ReadWrite.All` | Create/update Planner tasks (used by UI app) |
| `AuditLog.Read.All` | Sign-in activity (requires Azure AD Premium — not available) |
| `Reports.Read.All` | Office 365 usage reports |

## Key Identifiers

| Resource | ID |
|----------|-----|
| A1 Faculty License SKU | `94763226-9b3c-4e75-a931-5c89701abe66` |
| Microsoft 365 Group | `3e1567b2-40ad-4ab3-b91c-ac9a12062b0c` |
| SharePoint Drive ID | `b!RBattyx0GEKBlUMx4h6grijjsEzWaIpPozUrzEG1hTpuS2MIEC8DS58MqVXPuQzG` |
| SharePoint Item ID | `01LPNJR5PKQDWVLKVPOJD3LEPWI3LEL45P` |


## Project State

Current progress is tracked in [`.planning/STATE.md`](.planning/STATE.md).

## Credentials

All secrets are loaded from a `.env` file (see `.env.example`):

| Variable | Used by | Purpose |
|----------|---------|---------|
| `SPARKSOURCE_URL` | `scrape_schedules.py` | SparkSource ERP URL |
| `SPARKSOURCE_USER` | `scrape_schedules.py` | SparkSource login username |
| `SPARKSOURCE_PASS` | `scrape_schedules.py` | SparkSource login password |
| `AZURE_TENANT_ID` | `config.py` | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | `config.py` | Azure AD app client ID |
| `AZURE_CLIENT_SECRET` | `config.py` | Azure AD app client secret |
| `AZURE_DOMAIN` | `config.py` | M365 domain (default: `swisslearninggroup.onmicrosoft.com`) |

## V2 Sync Architecture

V2 replaces V1's "clear everything + recreate" approach with diff-based sync:

1. **Scrape** current schedule from SparkSource (multi-week for VIP)
2. **Load** previous state from `data/last_synced/{agenda}.json`
3. **Diff** — compute added/removed/changed events
4. **Apply** — targeted Graph API calls (DELETE removed, POST added)
5. **Save** — write new state with Outlook event IDs

**First run** (no state file): behaves like V1 (full clear + create), saves state.
**Subsequent runs**: only touches what changed — faster, fewer API calls, lower risk.

### State file format

```json
{
  "synced_at": "2026-02-27T13:00:00Z",
  "agenda": "private_english_lausanne",
  "sync_type": "vip",
  "events": {
    "teacher.email@domain.com": [
      {
        "outlook_event_id": "AAMk...",
        "date": "2026-03-04",
        "start": "09:00",
        "end": "10:00",
        "type": "VAD",
        "subject": "Private: VAD - VIP Adults"
      }
    ]
  }
}
```

## Future

- **Scrape WSE schedules** when available in SparkSource (16 teachers, 0 data currently)
- Monday reconciliation — weekly full compare of Outlook vs SparkSource to catch drift
- Add failure notifications (Teams webhook or email) to sync scripts
- Expand to other locations (Geneva, Fribourg, Montreux) when needed

## History

- Project originally created as "VIPs" — codebase behind an n8n workflow for VIP teacher assignment
- VIP matching logic migrated to UI app (`vip_planner.py`) on 2026-02-24 — n8n workflow retired
- Project repurposed as "Scheduling" — focused on teacher calendar management
- Method class sync completed 2026-02-24: 34 teachers, 124 recurring events
- Private lesson sync completed 2026-02-25: 43 teachers, 306 one-time events
- SparkSource scraper extracted from Student Follow Up into `src/scraper/` on 2026-02-27 — project fully self-contained
- Azure credentials migrated from hardcoded values to `.env` on 2026-02-27
- V2 implemented 2026-02-27: diff-based sync, multi-week scraping, per-agenda cron scripts
