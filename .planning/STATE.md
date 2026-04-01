# STATE — Scheduling (Teacher Calendar Management)

## Current State

- **V2 LIVE on VPS** — diff-based sync, multi-week scraping, systemd timers running
- **Services fixed Mar 29** — User=slg, chmod +x, venv installed. Timers active again after 5-10 days broken.
- .env populated (Apr 1) — live sync unblocked
- **Teacher provisioning**: Complete — 56 active M365 accounts
- **VIP matching logic**: Migrated to UI app (`vip_planner.py`) — no longer in this project
- **Diff-sync tests merged** (Cal #2, Mar 29)
- **Enriched sync reports merged** (Cal #3, Mar 29)

## Next Actions

1. [ ] Add integration tests for the full sync pipeline (not just diff_sync unit tests)
2. [ ] Add Outlook calendar validation — after sync, verify created events actually appear in Outlook
3. [ ] Add sync monitoring — post sync results to CC API so Dash can display calendar health
4. [ ] Investigate WSE schedule data availability in SparkSource
5. [x] Add error alerting — on sync failure, notify via Telegram (similar to Momo pattern)

## V2 — Production Sync (LIVE)

Spec: see Hub `.planning/scheduling-v2-spec.md` for full architecture.

### Systemd timers (active on VPS)

```
scheduling-method-sfs.timer  → Thursday 11:00 UTC (12:00 CET) — after SFS new week opens
scheduling-method-esa.timer  → Friday 11:00 UTC (12:00 CET) — after ESA new week opens
scheduling-vip.timer         → Mon-Sat every 2h 06:00-18:00 UTC (07:00-19:00 CET)
```

Unit files: Hub `.planning/systemd/`. Installed to `/etc/systemd/system/` on VPS.

```bash
systemctl list-timers scheduling-*          # See all jobs + next/last run
systemctl status scheduling-vip             # Check status
journalctl -u scheduling-vip --since today  # Read logs
sudo systemctl start scheduling-vip         # Manual trigger
```

### Validation results (Feb 27, 2026)

- [x] Method sync first run: 20 teachers, 68 events, 0 failures
- [x] Method sync second run: `Added: 0, Removed: 0, Changed: 0, Unchanged: 68`
- [x] VIP sync first run: 380 events across 3 agendas (3 weeks each)
- [x] Systemd timers installed and active
- [x] Services fixed (Mar 29) — User=slg, chmod +x, venv installed
- [x] Diff-sync tests merged (Cal #2, Mar 29)
- [x] Enriched sync reports merged (Cal #3, Mar 29)
- [ ] Monitor first automated runs — .env populated Apr 1
- [x] Remove `scripts/test_week_nav.py` after confidence established

### Key design decisions

- **Diff-based sync** — compare new scrape vs last synced state, only create/delete/update changes
- **State files** in `data/last_synced/` — store synced events with Outlook event IDs for targeted deletes
- **Method classes** stay as recurring events, VIPs as individual dated events
- **First run** (no state file) behaves like v1: full clear + recreate
- **Backward compatible** — `run_full_sync.sh` (v1) still works as fallback

## VPS Deployment — COMPLETE

**Model**: Local PC (`main`) → GitHub → VPS auto-pulls (repo-sync every 5 min)

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

## Blocked

| Item | Blocked By | Since |
|------|-----------|-------|
| Actual sync runs | .env needs SparkSource + Azure credentials | Mar 2026 |
| WSE schedule sync | SparkSource has no WSE schedule data | Feb 2026 |

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
| `scripts/deploy_webhook.py` | Deploy webhook listener (GitHub Actions → git pull) | Done |
| `scripts/config.py` | Shared Graph API credentials & helpers | Done |
| `scripts/provision_teachers.py` | Create M365 accounts + assign A1 licenses | Done |
| `scripts/tenant_recon.py` | Query tenant info | Done |
| `scripts/tenant_review.py` | Tenant account review with activity data | Done |

---
*Last updated: 2026-04-01*
