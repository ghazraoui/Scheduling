# STATE — Scheduling (Teacher Calendar Management)

## Current State

- **Project renamed**: VIPs → Scheduling (2026-02-25) — focused on teacher calendar management
- **Method class sync**: Complete — 124 recurring "Teaching" events for 34 teachers (SFS + ESA)
- **Private lesson sync**: Complete — 306 one-time events for 43 teachers (3 Lausanne agendas)
- **Teacher provisioning**: Complete — 56 active M365 accounts
- **VIP matching logic**: Migrated to UI app (`vip_planner.py`) — no longer in this project

## Completed

- [x] Teacher account provisioning — 56 active M365 accounts (A1 for Faculty)
- [x] Data cleanup — removed 4 non-teaching roles, added Rachel Bergin, fixed 5 misspelled names
- [x] Method class scraping — 34 teachers, 124 slots from SparkSource (SFS + ESA)
- [x] Method class sync — 124 recurring "Teaching" events (2026-02-24)
- [x] Private lesson scraping — 3 Lausanne agendas (English/French/German), 306 classes, 43 teachers
- [x] Private lesson sync — 306 one-time events with type-specific subjects + Outlook color categories (2026-02-25)
- [x] Tenant account review — report generated with Office 365 usage activity data
- [x] VIP matching logic migrated to UI app — n8n workflow retired (2026-02-24)
- [x] Project cleanup — admin scripts removed from UI, project renamed Scheduling (2026-02-25)

## Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/config.py` | Shared Graph API credentials & helpers | Done |
| `scripts/provision_teachers.py` | Create M365 accounts + assign A1 licenses | Done |
| `scripts/sync_calendars.py` | Sync method schedules as recurring "Teaching" events | Done |
| `scripts/sync_private_calendars.py` | Sync private lessons as one-time events with colors | Done |
| `scripts/tenant_recon.py` | Query tenant info | Done |
| `scripts/tenant_review.py` | Tenant account review with activity data | Done |

## Next Up

1. **Scrape WSE schedules** from SparkSource when available (16 teachers, 0 data)
2. **Re-sync calendars** after WSE data arrives
3. **Automate weekly re-sync** of private lessons (they change each week)
4. **Research automation approach** — n8n, cron, or other for periodic scrape + sync
