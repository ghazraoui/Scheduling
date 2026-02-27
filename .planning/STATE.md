# STATE — Scheduling (Teacher Calendar Management)

## Current State

- **V2 code complete** — diff-based sync, multi-week scraping, per-agenda cron scripts
- **Needs validation** — run test_week_nav.py to confirm week navigation, then test end-to-end on VPS
- **Teacher provisioning**: Complete — 56 active M365 accounts
- **VIP matching logic**: Migrated to UI app (`vip_planner.py`) — no longer in this project

## V2 — Production Sync

Spec: see Hub `.planning/scheduling-v2-spec.md` for full architecture.

### Implementation status

| Change | Purpose | Status |
|--------|---------|--------|
| Week navigation discovery | `test_week_nav.py` — confirm SparkSource week nav | Done (needs manual test) |
| Add `--weeks N` to scraper | Multi-week VIP scraping (3 weeks ahead) | Done |
| Create `diff_sync.py` | Diff engine: compare old/new, only sync changes | Done |
| Refactor `sync_calendars.py` | Use diff engine + `--agenda` for method classes | Done |
| Refactor `sync_private_calendars.py` | Use diff engine + `--agenda` for VIP events | Done |
| Create `sync_method.sh` | Wrapper: scrape + diff-sync one method school | Done |
| Create `sync_vip.sh` | Wrapper: scrape + diff-sync all 3 VIP agendas | Done |
| Update VPS timers | Systemd timers for method (weekly) vs VIP (every 2h) | Ready (see below) |

### VPS systemd timers (to install)

Using systemd timers instead of cron — better logging (`journalctl`), status tracking (`systemctl status`), auto-catch-up on missed runs.

```
scheduling-method-sfs.timer  → Thursday 18:00 UTC (20:00 CET) — after SFS new week opens
scheduling-method-esa.timer  → Friday 18:00 UTC (20:00 CET) — after ESA new week opens
scheduling-vip.timer         → Mon-Sat every 2h 06:00-18:00 UTC (07:00-19:00 CET)
```

Unit files: Hub `.planning/systemd/`. Install: `sudo bash install-timers.sh`

```bash
systemctl list-timers scheduling-*          # See all jobs + next/last run
systemctl status scheduling-vip             # Check status
journalctl -u scheduling-vip --since today  # Read logs
sudo systemctl start scheduling-vip         # Manual trigger
```

### Validation checklist

- [ ] `git push` to GitHub, `git pull` on VPS
- [ ] Run `sync_method.sh sfs_lausanne` on VPS (first run = full sync)
- [ ] Run again — should show 0 changes (diff empty)
- [ ] Run `sync_vip.sh` on VPS — first run creates state for all 3 agendas
- [ ] Wait, run again — should only show real changes
- [ ] Install systemd timers on VPS after validation
- [ ] Remove `scripts/test_week_nav.py` after validation complete

### Key design decisions

- **Diff-based sync** — compare new scrape vs last synced state, only create/delete/update changes
- **State files** in `data/last_synced/` — store synced events with Outlook event IDs for targeted deletes
- **Method classes** stay as recurring events, VIPs as individual dated events
- **First run** (no state file) behaves like v1: full clear + recreate
- **Backward compatible** — `run_full_sync.sh` (v1) still works as fallback

## VPS Deployment — COMPLETE

**Model**: Local PC → GitHub (`ghazraoui/Scheduling`) → VPS (`git clone` at `/opt/slg/scheduling/`)

- [x] GitHub repo created and pushed
- [x] SparkSource scraper extracted from Student Follow Up (self-contained)
- [x] Azure credentials moved to `.env` (no hardcoded secrets)
- [x] `run_full_sync.sh` wrapper script created (v1 fallback)
- [x] VPS: Python 3.13 venv + all deps installed
- [x] VPS: Playwright + Chromium headless working
- [x] VPS: Git clone at `/opt/slg/scheduling/`
- [x] VPS: `.env` created with locked permissions (chmod 600)
- [x] VPS: Full pipeline dry-run successful (5 agendas scraped, both syncs ran)
- [x] VPS: Log directory at `/var/log/scheduling/`

## Completed (V1 / POC)

- [x] Teacher account provisioning — 56 active M365 accounts (A1 for Faculty)
- [x] Data cleanup — removed 4 non-teaching roles, added Rachel Bergin, fixed 5 misspelled names
- [x] Method class scraping — 34 teachers, 124 slots from SparkSource (SFS + ESA)
- [x] Method class sync — 124 recurring "Teaching" events (2026-02-24)
- [x] Private lesson scraping — 3 Lausanne agendas (English/French/German), 306 classes, 43 teachers
- [x] Private lesson sync — 306 one-time events with type-specific subjects + Outlook color categories (2026-02-25)
- [x] Tenant account review — report generated with Office 365 usage activity data
- [x] VIP matching logic migrated to UI app — n8n workflow retired (2026-02-24)
- [x] Project cleanup — admin scripts removed from UI, project renamed Scheduling (2026-02-25)
- [x] SparkSource scraper extracted from Student Follow Up — project fully self-contained (2026-02-27)
- [x] VPS deployment + end-to-end test (2026-02-27)

## Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/scrape_schedules.py` | Scrape SparkSource schedules (Playwright, `--weeks N`) | Done (v2) |
| `scripts/diff_sync.py` | Diff engine: compare + apply changes | Done (v2) |
| `scripts/sync_calendars.py` | Sync method schedules (diff-based, `--agenda`) | Done (v2) |
| `scripts/sync_private_calendars.py` | Sync private lessons (diff-based, `--agenda`) | Done (v2) |
| `scripts/sync_method.sh` | Wrapper: method class scrape + diff sync | Done (v2) |
| `scripts/sync_vip.sh` | Wrapper: VIP scrape + diff sync (all 3 schools) | Done (v2) |
| `scripts/run_full_sync.sh` | V1 full pipeline (kept as fallback) | Done (v1) |
| `scripts/test_week_nav.py` | Week navigation discovery (temporary) | Done (remove after test) |
| `scripts/config.py` | Shared Graph API credentials & helpers | Done |
| `scripts/provision_teachers.py` | Create M365 accounts + assign A1 licenses | Done |
| `scripts/tenant_recon.py` | Query tenant info | Done |
| `scripts/tenant_review.py` | Tenant account review with activity data | Done |

## TODO (future, not blocking)

- [ ] Monday reconciliation — weekly full compare of Outlook vs SparkSource to catch drift
- [ ] WSE schedules — when available in SparkSource (16 teachers, different platform for method)
- [ ] Failure notifications — Teams webhook or email on sync errors
- [ ] Expand to other locations (Geneva, Fribourg, Montreux) when needed
