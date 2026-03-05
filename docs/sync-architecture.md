# V2 Sync Architecture

V2 replaces V1's "clear everything + recreate" approach with diff-based sync:

1. **Scrape** current schedule from SparkSource (multi-week for VIP)
2. **Load** previous state from `data/last_synced/{agenda}.json`
3. **Diff** — compute added/removed/changed events
4. **Apply** — targeted Graph API calls (DELETE removed, POST added)
5. **Save** — write new state with Outlook event IDs

**First run** (no state file): behaves like V1 (full clear + create), saves state.
**Subsequent runs**: only touches what changed — faster, fewer API calls, lower risk.

## State File Format

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

## Key Design Decisions

- **Diff-based sync** — compare new scrape vs last synced state, only create/delete/update changes
- **State files** in `data/last_synced/` — store synced events with Outlook event IDs for targeted deletes
- **Method classes** stay as recurring events, VIPs as individual dated events
- **First run** (no state file) behaves like V1: full clear + recreate
- **Backward compatible** — `run_full_sync.sh` (V1) still works as fallback
