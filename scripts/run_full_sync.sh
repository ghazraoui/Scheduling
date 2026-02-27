#!/bin/bash
# Full Scheduling Pipeline: Scrape SparkSource → Sync to Outlook
# Usage: /opt/slg/scheduling/scripts/run_full_sync.sh [--dry-run]
#
# Cron example (weekly, Monday 05:00 CET):
#   0 4 * * 1 /opt/slg/scheduling/scripts/run_full_sync.sh >> /var/log/scheduling/sync.log 2>&1

set -euo pipefail

PROJECT_DIR="/opt/slg/scheduling"
VENV="$PROJECT_DIR/.venv/bin/python"
SCRIPTS="$PROJECT_DIR/scripts"
DATA="$PROJECT_DIR/data"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

DRY_RUN=""
SYNC_FLAG="--execute"
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="yes"
    SYNC_FLAG=""
    echo "$LOG_PREFIX Running in DRY-RUN mode"
fi

cd "$PROJECT_DIR"

# Exit handler for failure notifications
on_error() {
    echo "$LOG_PREFIX FAILED at step: $CURRENT_STEP"
    # TODO: Add Teams/email webhook notification here
    exit 1
}
trap on_error ERR

CURRENT_STEP="init"
echo "$LOG_PREFIX ========== SCHEDULING PIPELINE START =========="

# --- PHASE 1: Scrape SparkSource schedules ---

CURRENT_STEP="scrape-sfs"
echo "$LOG_PREFIX Scraping SFS Lausanne method schedule..."
$VENV $SCRIPTS/scrape_schedules.py --weekly-teachers --agenda sfs_lausanne \
    --output $DATA/teacher-schedule-sfs_lausanne.json

CURRENT_STEP="scrape-esa"
echo "$LOG_PREFIX Scraping ESA Lausanne method schedule..."
$VENV $SCRIPTS/scrape_schedules.py --weekly-teachers --agenda esa_lausanne \
    --output $DATA/teacher-schedule-esa_lausanne.json

CURRENT_STEP="scrape-private-english"
echo "$LOG_PREFIX Scraping Private English Lausanne..."
$VENV $SCRIPTS/scrape_schedules.py --weekly-detailed --agenda private_english_lausanne \
    --output $DATA/teacher-schedule-private_english_lausanne-detailed.json

CURRENT_STEP="scrape-private-french"
echo "$LOG_PREFIX Scraping Private French Lausanne..."
$VENV $SCRIPTS/scrape_schedules.py --weekly-detailed --agenda private_french_lausanne \
    --output $DATA/teacher-schedule-private_french_lausanne-detailed.json

CURRENT_STEP="scrape-private-german"
echo "$LOG_PREFIX Scraping Private German Lausanne..."
$VENV $SCRIPTS/scrape_schedules.py --weekly-detailed --agenda private_german_lausanne \
    --output $DATA/teacher-schedule-private_german_lausanne-detailed.json

echo "$LOG_PREFIX All 5 agendas scraped successfully"

# --- PHASE 2: Sync to Outlook calendars ---

CURRENT_STEP="sync-method"
echo "$LOG_PREFIX Syncing method class schedules to Outlook..."
$VENV $SCRIPTS/sync_calendars.py $SYNC_FLAG

CURRENT_STEP="sync-private"
echo "$LOG_PREFIX Syncing private lesson schedules to Outlook..."
$VENV $SCRIPTS/sync_private_calendars.py $SYNC_FLAG

echo "$LOG_PREFIX ========== SCHEDULING PIPELINE COMPLETE =========="
