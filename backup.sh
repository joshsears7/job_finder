#!/bin/bash
# CareerIQ backup
# Usage: bash ~/Documents/Projects/job_finder/backup.sh
# Saves timestamped snapshot to backups/YYYYMMDD_HHMMSS/ (keeps 10)

set -euo pipefail

PROJ="/Users/joshuasears/Documents/Projects/job_finder"
DEST="$PROJ/backups/$(date +"%Y%m%d_%H%M%S")"

mkdir -p "$DEST"

rsync -a \
  --exclude='backups/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='chroma_db/' \
  --exclude='cache/' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  "$PROJ/" "$DEST/"

# Counts for verification
PY_COUNT=$(find "$DEST" -name "*.py" | wc -l | tr -d ' ')
ENV_CHECK=$([ -f "$DEST/.env" ] && echo "YES" || echo "MISSING")
DB_CHECK=$([ -f "$DEST/applications.db" ] && echo "YES" || echo "MISSING")
PAGES_COUNT=$(find "$DEST/pages" -name "*.py" 2>/dev/null | wc -l | tr -d ' ')
TESTS_COUNT=$(find "$DEST/tests" -name "*.py" 2>/dev/null | wc -l | tr -d ' ')

echo "=============================="
echo "CareerIQ Backup Complete"
echo "=============================="
echo "  Location : $DEST"
echo "  .py files: $PY_COUNT ($PAGES_COUNT pages + $TESTS_COUNT tests)"
echo "  .env     : $ENV_CHECK"
echo "  DB       : $DB_CHECK"
echo "=============================="

# Keep only 10 most recent snapshots
ls -1d "$PROJ/backups"/[0-9]* 2>/dev/null | sort -r | tail -n +11 | while read old; do
    rm -rf "$old" && echo "  Pruned old backup: $(basename $old)"
done
