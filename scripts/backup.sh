#!/bin/bash
# =============================================================================
# MIDA OCR Application - Database Backup Script
# =============================================================================
# Manual backup script - can be run standalone or via cron
# Usage: ./backup.sh [backup_dir]
# =============================================================================

set -e

# Configuration
BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/mida_backup_${TIMESTAMP}.sql.gz"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}[${TIMESTAMP}] Starting database backup...${NC}"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Check if running inside Docker or on host
if [ -f /.dockerenv ]; then
    # Inside Docker container
    pg_dump -h postgres -U "${PGUSER:-mida}" -d "${PGDATABASE:-mida}" | gzip > "$BACKUP_FILE"
else
    # On host machine - use docker compose exec
    docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-mida}" -d "${POSTGRES_DB:-mida}" | gzip > "$BACKUP_FILE"
fi

# Check if backup was successful
if [ $? -eq 0 ] && [ -s "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}[$(date +%Y%m%d_%H%M%S)] Backup completed successfully${NC}"
    echo -e "  File: ${BACKUP_FILE}"
    echo -e "  Size: ${BACKUP_SIZE}"
    
    # Clean up old backups
    echo -e "${YELLOW}Cleaning up backups older than ${RETENTION_DAYS} days...${NC}"
    DELETED=$(find "$BACKUP_DIR" -name "mida_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -delete -print | wc -l)
    echo -e "  Deleted ${DELETED} old backup(s)"
    
    # List current backups
    echo -e "\nCurrent backups:"
    ls -lh "$BACKUP_DIR"/mida_backup_*.sql.gz 2>/dev/null | tail -5 || echo "  No backups found"
else
    echo -e "${RED}[$(date +%Y%m%d_%H%M%S)] Backup FAILED!${NC}"
    rm -f "$BACKUP_FILE"
    exit 1
fi
