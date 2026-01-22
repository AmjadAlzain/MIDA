#!/bin/bash
# =============================================================================
# MIDA OCR Application - Database Restore Script
# =============================================================================
# Restore database from backup
# Usage: ./restore.sh <backup_file>
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check arguments
if [ -z "$1" ]; then
    echo -e "${RED}Usage: $0 <backup_file>${NC}"
    echo ""
    echo "Available backups:"
    ls -lh ./backups/mida_backup_*.sql.gz 2>/dev/null || echo "  No backups found in ./backups/"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Error: Backup file not found: ${BACKUP_FILE}${NC}"
    exit 1
fi

echo -e "${YELLOW}WARNING: This will overwrite the current database!${NC}"
echo -e "Backup file: ${BACKUP_FILE}"
read -p "Are you sure you want to continue? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi

echo -e "${GREEN}Starting database restore...${NC}"

# Load environment variables
source .env 2>/dev/null || true
POSTGRES_USER=${POSTGRES_USER:-mida}
POSTGRES_DB=${POSTGRES_DB:-mida}

# Stop the API to prevent connections during restore
echo "Stopping API service..."
docker compose stop mida-api

# Restore database
echo "Restoring database from backup..."
gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Database restored successfully!${NC}"
else
    echo -e "${RED}Database restore failed!${NC}"
    exit 1
fi

# Restart API
echo "Restarting API service..."
docker compose start mida-api

echo -e "${GREEN}Restore completed. Services are running.${NC}"
