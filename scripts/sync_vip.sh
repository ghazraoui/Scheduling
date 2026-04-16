#!/bin/bash
# Sync all 3 VIP agendas: scrape 3 weeks ahead → diff → sync to Outlook
#
# Usage: sync_vip.sh
#
# Cron example (every 2h, 06:00-18:00 UTC, Mon-Sat):
#   0 6-18/2 * * 1-6 /opt/slg/scheduling/scripts/sync_vip.sh >> /var/log/scheduling/vip.log 2>&1

set -euo pipefail

PROJECT_DIR="/opt/slg/scheduling"
VENV="$PROJECT_DIR/.venv/bin/python"
SCRIPTS="$PROJECT_DIR/scripts"
DATA="$PROJECT_DIR/data"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

cd "$PROJECT_DIR"

# Exit handler for failure notifications
on_error() {
    echo "$LOG_PREFIX FAILED at step: $CURRENT_STEP"
    "$VENV" "$SCRIPTS/notify.py" "📅 Cal VIP sync FAILED at step $CURRENT_STEP" || true
    exit 1
}
trap on_error ERR

CURRENT_STEP="init"
echo "$LOG_PREFIX ========== VIP SYNC: ALL AGENDAS =========="

for LANG in english french german; do
    AGENDA="private_${LANG}_lausanne"

    # 1. Scrape next 3 weeks
    CURRENT_STEP="scrape-${AGENDA}"
    echo "$LOG_PREFIX Scraping $AGENDA (3 weeks)..."
    $VENV $SCRIPTS/scrape_schedules.py --weekly-detailed --agenda "$AGENDA" --weeks 3 \
        --output "$DATA/teacher-schedule-${AGENDA}-detailed.json"

    OUTPUT_FILE="$DATA/teacher-schedule-${AGENDA}-detailed.json"
    TEACHER_COUNT=$("$VENV" -c "import json; d=json.load(open('$OUTPUT_FILE')); print(len(d))")
    echo "$LOG_PREFIX Scrape returned $TEACHER_COUNT teachers for $AGENDA"
    if [ "$TEACHER_COUNT" -eq 0 ]; then
        "$VENV" "$SCRIPTS/notify.py" "🚨 Cal VIP sync ABORTED: $AGENDA scrape returned empty data (0 teachers) — sync skipped to prevent calendar wipe" || true
        exit 1
    fi

    # 2. Diff-sync to Outlook
    CURRENT_STEP="sync-${AGENDA}"
    echo "$LOG_PREFIX Diff-syncing $AGENDA to Outlook..."
    $VENV $SCRIPTS/sync_private_calendars.py --agenda "$AGENDA" --execute

    echo "$LOG_PREFIX Completed: $AGENDA"
done

echo "$LOG_PREFIX ========== VIP SYNC COMPLETE =========="
