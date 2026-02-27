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
│           └── schedule.py        # SchedulePage — weekly schedule extraction
├── scripts/
│   ├── config.py                  # Azure AD credentials (from .env) + Graph API helpers
│   ├── scrape_schedules.py        # Scrape SparkSource schedules (self-contained)
│   ├── sync_calendars.py          # Sync method classes → recurring "Teaching" events
│   ├── sync_private_calendars.py  # Sync private lessons → one-time events with colors
│   ├── provision_teachers.py      # Create M365 teacher accounts + assign A1 licenses
│   ├── parse_teachers.py          # Extract teacher data from .docx → teachers.json
│   ├── tenant_recon.py            # Query tenant info (org, licenses, users, domains)
│   └── tenant_review.py           # Generate tenant account review report
├── data/
│   ├── teachers.json              # 56 teachers (name, phone, email, tags, section)
│   ├── Teachers.xlsx              # Teacher directory (also on SharePoint)
│   ├── sparksource-schedules.md   # Reference: all 28 SparkSource agendas
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
python scripts/scrape_schedules.py --weekly-teachers --agenda sfs_lausanne           # method classes
python scripts/scrape_schedules.py --weekly-detailed --agenda private_english_lausanne # private lessons
python scripts/scrape_schedules.py --table --agenda esa_lausanne                      # today's schedule as table
python scripts/scrape_schedules.py --headed                                            # debug with visible browser
```

- Uses `src/scraper/` module (SchedulePage, session management, read-only guardrails)
- Supports all agendas: `sfs_lausanne`, `esa_lausanne`, `private_english_lausanne`, etc.
- Outputs JSON files to `data/` directory (same format as sync scripts expect)
- SparkSource credentials loaded from `.env` (`SPARKSOURCE_URL`, `SPARKSOURCE_USER`, `SPARKSOURCE_PASS`)

### `sync_calendars.py` — Method Class Sync

Syncs SFS + ESA method class schedules as **recurring weekly** "Teaching" events.

```bash
python scripts/sync_calendars.py              # dry-run (default)
python scripts/sync_calendars.py --execute    # clear old + create events
python scripts/sync_calendars.py --clear-only # just remove "Teaching" events
```

- Reads: `data/teacher-schedule-{sfs,esa}_lausanne.json`
- Creates: weekly recurring events, `showAs: busy`, no end date
- Subject: `Teaching`
- Idempotent (clear-before-create) — safe to re-run
- Last run (2026-02-24): 34 teachers, 124 events, 0 failures

### `sync_private_calendars.py` — Private Lesson Sync

Syncs private/VIP lessons as **one-time dated** events with type-specific subjects and Outlook color categories.

```bash
python scripts/sync_private_calendars.py              # dry-run
python scripts/sync_private_calendars.py --execute    # clear old + create events
python scripts/sync_private_calendars.py --clear-only # just remove "Private:" events
```

- Reads: `data/teacher-schedule-private_*_lausanne-detailed.json`
- Creates: single-occurrence events per class, each with activity type subject and color category
- Subject format: `Private: VAD - VIP Adults` or `Private: VAD - VIP Adults (Online)`
- Idempotent (clear-before-create)
- Last run (2026-02-25): 43 teachers, 306 events, 0 failures
- **Needs weekly re-sync** — private lessons change each week

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

| Type | Script | Subject | Recurrence | Re-sync frequency |
|------|--------|---------|------------|-------------------|
| Method classes | `sync_calendars.py` | `Teaching` | Weekly (no end date) | When schedule changes |
| Private lessons | `sync_private_calendars.py` | `Private: {type}` | One-time (dated) | Weekly |

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

## Future

- **Automate weekly re-sync** of private lessons (they change each week)
- **Scrape WSE schedules** when available in SparkSource (16 teachers, 0 data currently)
- Research best approach for periodic automation (n8n, cron, or other)

## History

- Project originally created as "VIPs" — codebase behind an n8n workflow for VIP teacher assignment
- VIP matching logic migrated to UI app (`vip_planner.py`) on 2026-02-24 — n8n workflow retired
- Project repurposed as "Scheduling" — focused on teacher calendar management
- Method class sync completed 2026-02-24: 34 teachers, 124 recurring events
- Private lesson sync completed 2026-02-25: 43 teachers, 306 one-time events
- SparkSource scraper extracted from Student Follow Up into `src/scraper/` on 2026-02-27 — project fully self-contained
- Azure credentials migrated from hardcoded values to `.env` on 2026-02-27
