#!/bin/bash
# Sync one method school: scrape SparkSource → diff → sync to Outlook
#
# Usage: sync_method.sh <agenda>
#   e.g., sync_method.sh sfs_lausanne
#         sync_method.sh esa_lausanne
#
# Cron examples:
#   0 18 * * 4 /opt/slg/scheduling/scripts/sync_method.sh sfs_lausanne >> /var/log/scheduling/method_sfs.log 2>&1
#   0 18 * * 5 /opt/slg/scheduling/scripts/sync_method.sh esa_lausanne >> /var/log/scheduling/method_esa.log 2>&1

set -euo pipefail

PROJECT_DIR="/opt/slg/scheduling"
VENV="$PROJECT_DIR/.venv/bin/python"
SCRIPTS="$PROJECT_DIR/scripts"
DATA="$PROJECT_DIR/data"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

AGENDA="${1:?Usage: sync_method.sh <agenda>}"

cd "$PROJECT_DIR"

# Exit handler for failure notifications
on_error() {
    echo "$LOG_PREFIX FAILED at step: $CURRENT_STEP (agenda: $AGENDA)"
    # TODO: Add Teams/email webhook notification here
    exit 1
}
trap on_error ERR

CURRENT_STEP="init"
echo "$LOG_PREFIX ========== METHOD SYNC: $AGENDA =========="

# 1. Scrape current week
CURRENT_STEP="scrape"
echo "$LOG_PREFIX Scraping $AGENDA method schedule..."
$VENV $SCRIPTS/scrape_schedules.py --weekly-teachers --agenda "$AGENDA" \
    --output "$DATA/teacher-schedule-${AGENDA}.json"

# 2. Diff-sync to Outlook
CURRENT_STEP="sync"
echo "$LOG_PREFIX Diff-syncing $AGENDA to Outlook..."
$VENV $SCRIPTS/sync_calendars.py --agenda "$AGENDA" --execute

echo "$LOG_PREFIX ========== METHOD SYNC COMPLETE: $AGENDA =========="
