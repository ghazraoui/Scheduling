# Scheduling — Index

## Start here
Syncs SparkSource schedules to teacher Outlook calendars via Graph API. Owned by **Cal** (Scheduling Assistant), supervised by Sparky.

## Navigate
- [Identity](CLAUDE.md)
- [Current state](.planning/STATE.md)
- [Active plans](.planning/)
- [Setup & credentials](docs/setup.md)
- [Sync architecture (V2)](docs/sync-architecture.md)
- [Deployment & VPS](docs/deployment.md)
- [Azure app registration](docs/azure.md)
- [All scripts reference](docs/scripts.md)
- [SparkSource agendas](data/sparksource-schedules.md)

## Key entities
- **SparkSource** — schedule source of truth (Playwright scraper, no API)
- **Microsoft Graph API** — pushes events to teacher Outlook calendars (56 teachers provisioned)
- **Diff-sync engine** — `scripts/diff_sync.py` compares scrape vs `data/last_synced/` state files
- **VPS** — `/opt/slg/scheduling/`, systemd timers (method Thu/Fri, VIP every 2h Mon-Sat)
- **UI app (Rex)** — downstream consumer, reads teacher calendars for VIP matching

## Status
- **V2 live** on VPS with diff-based sync and systemd timers
- **Blocked:** .env needs SparkSource + Azure credentials for WSE schedules
