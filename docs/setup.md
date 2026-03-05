# Setup

## Prerequisites

- Python 3.13+
- Playwright with Chromium (`playwright install chromium`)

## Environment Variables

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

## Installation

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/Mac
# .venv\Scripts\activate        # Windows
pip install -r requirements.txt
playwright install chromium
cp .env.example .env            # Fill in credentials
```

## Quick Start

```bash
# Scrape method class schedules
python scripts/scrape_schedules.py --weekly-teachers --agenda sfs_lausanne

# Dry-run sync (preview changes)
python scripts/sync_calendars.py --agenda sfs_lausanne

# Execute sync
python scripts/sync_calendars.py --agenda sfs_lausanne --execute
```
