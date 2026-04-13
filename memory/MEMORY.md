# Scheduling Project Memory (formerly VIPs)

Last consolidated: 2026-03-31 (Dream run 24 — added .env blocker)

## Project Identity
- **Name**: Scheduling (renamed from VIPs on 2026-02-25)
- **Purpose**: Teacher calendar management — sync SparkSource schedule data to Outlook calendars
- **Location**: `C:\Users\zackg\OneDrive\Desktop\AI Projects\Scheduling`

## Three-Project Architecture
```
Student Follow Up              Scheduling (this project)           UI App
(scrape SparkSource)    →    (sync to Outlook calendars)    →    (query calendars)
  get_daily_schedule.py         sync_calendars.py                  vip_planner.py
  schedule.py                   sync_private_calendars.py
```
- **UI** (`Desktop\Work\SLG\APPS\UI`) — Streamlit sales tool. `vip_planner.py` reads all data live from Graph API. No local file dependencies on this project.
- **Student Follow Up** (`Desktop\AI Projects\Student Follow Up`) — SparkSource scraper. Outputs schedule JSONs to its own `data/`. Copied to Scheduling for sync.
- **Scheduling** (this) — Owns all calendar sync scripts, teacher provisioning, schedule data files.

## Completed Work
- [x] Teacher provisioning — 56 active M365 accounts (A1 for Faculty)
- [x] Method class sync — 124 recurring "Teaching" events for 34 teachers (SFS + ESA, 2026-02-24)
- [x] Private lesson sync — 306 one-time events for 43 teachers (3 Lausanne agendas, 2026-02-25)
- [x] VIP matching logic migrated to UI app (2026-02-24)
- [x] Project cleanup — admin scripts removed from UI, docs updated across all 3 projects (2026-02-25)

## Private Lesson Sync Details
- SparkSource agenda IDs: Private English (57), Private French (100), Private German (101)
- Scraping mode: `--weekly-detailed` preserves date, type, name, online flag
- Activity types: VAD (Purple), TPC (Red), JPR (Blue), JGP (Green), ICO (Orange), VIP (Yellow)
- Event subject: `Private: VAD - VIP Adults` or `Private: VAD - VIP Adults (Online)`
- `sync_private_calendars.py`: idempotent clear-before-create, separate from "Teaching" events
- Heavy teacher overlap: Private French shares 17/19 with SFS, German shares all 12 with ESA

## Key Learnings
- Windows console UTF-8: `io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")`
- Guard against double-wrap when importing: `if not isinstance(sys.stdout, io.TextIOWrapper):`
- Always pass `encoding='utf-8'` when opening files on Windows
- SparkSource names can have slash-separated tokens (e.g. "Emily VIP/TP TAYLOR") — split on "/" before filtering
- Method classes = recurring weekly ("Teaching"); Private lessons = one-time dated ("Private: TYPE")
- Private lessons vary weekly — need regular re-sync
- Azure AD permission grants can take 1-5 minutes to propagate
- SharePoint Excel workbook API needs direct drive path, not `/shares` with app-only tokens
- Planner API requires `Tasks.ReadWrite.All` (Application) for app-only token access

## Credentials / Config
- Shared config in `scripts/config.py` — all scripts import from there
- Azure app: `63a2f848-ceb5-497f-aed2-3936893c3247`
- A1 Faculty SKU: `94763226-9b3c-4e75-a931-5c89701abe66`
- Domain: `swisslearninggroup.onmicrosoft.com`

## Blockers
- **VPS .env missing credentials**: SparkSource login + Azure app secret needed for VPS deployment. Local works, VPS sync scripts cannot run without these.

## Next Up
1. Scrape WSE schedules from SparkSource (16 teachers, 0 data)
2. Automate weekly re-sync of private lessons (systemd timer or cron — n8n canceled)
3. Test VIP matching from Streamlit UI (in UI project)
