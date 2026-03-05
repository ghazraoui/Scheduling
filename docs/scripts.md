# Scripts Reference

## `config.py` — Shared Graph API Helpers

Imported by all other scripts. Provides:
- `get_token()` — app-only access token via client credentials
- `graph_get()`, `graph_get_all()`, `graph_post()`, `graph_delete()` — Graph API wrappers
- `resolve_license_sku()` — look up A1 Faculty license SKU ID
- `CALENDAR_EVENT_SUBJECT = "Teaching"` — subject prefix for method class events
- Azure AD credentials loaded from `.env` (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_DOMAIN`)

## `scrape_schedules.py` — SparkSource Schedule Scraper

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

## `diff_sync.py` — Diff Engine (V2)

Core diff engine for V2 sync. Compares new schedule data against last-synced state and produces targeted Graph API operations.

- `load_last_synced(agenda)` / `save_synced_state(agenda, sync_type, events)` — state file I/O
- `compute_method_diff(old, new)` — identity key: (upn, day, start_time)
- `compute_vip_diff(old, new)` — identity key: (upn, date, start_time, activity_code)
- `apply_method_diff()` / `apply_vip_diff()` — execute Graph API calls for diff
- `merge_synced_events()` — combine unchanged + new events for state persistence
- State files: `data/last_synced/{agenda}.json` (gitignored)
- First run (no state): full clear + create (same as V1), then saves state

## `sync_calendars.py` — Method Class Sync

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

## `sync_private_calendars.py` — Private Lesson Sync

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

## `sync_method.sh` — Method Class Pipeline (V2)

Wrapper script: scrapes one method school + diff-syncs to Outlook.

```bash
scripts/sync_method.sh sfs_lausanne   # scrape SFS + diff-sync
scripts/sync_method.sh esa_lausanne   # scrape ESA + diff-sync
```

## `sync_vip.sh` — VIP Pipeline (V2)

Wrapper script: scrapes all 3 VIP agendas (3 weeks ahead) + diff-syncs to Outlook.

```bash
scripts/sync_vip.sh   # scrape English/French/German private (3 weeks) + diff-sync
```

## `provision_teachers.py` — Account Provisioning

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
