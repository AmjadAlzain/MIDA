#!/bin/bash
# =============================================================================
# MIDA OCR Application - Health Monitor Script
# =============================================================================
# Checks health of all services and sends alerts if issues detected
# Can be run via cron for continuous monitoring
# Usage: ./monitor.sh [--alert-email your@email.com]
# =============================================================================

set -e

# Configuration
ALERT_EMAIL="${ALERT_EMAIL:-}"
API_URL="http://localhost:${API_PORT:-8000}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT:-80}"
LOG_FILE="./logs/monitor.log"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --alert-email)
            ALERT_EMAIL="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Create logs directory
mkdir -p logs

# Log function
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    case $level in
        INFO)
            echo -e "${GREEN}[$timestamp] $message${NC}"
            ;;
        WARN)
            echo -e "${YELLOW}[$timestamp] $message${NC}"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] $message${NC}"
            ;;
    esac
}

# Send alert (if email configured)
send_alert() {
    local subject=$1
    local body=$2
    
    if [ -n "$ALERT_EMAIL" ] && command -v mail &> /dev/null; then
        echo "$body" | mail -s "MIDA Monitor Alert: $subject" "$ALERT_EMAIL"
        log "INFO" "Alert sent to $ALERT_EMAIL"
    fi
}

# Check Docker service
check_docker() {
    if docker info &> /dev/null; then
        log "INFO" "Docker daemon: OK"
        return 0
    else
        log "ERROR" "Docker daemon: NOT RUNNING"
        send_alert "Docker Down" "Docker daemon is not running on $(hostname)"
        return 1
    fi
}

# Check container health
check_containers() {
    local failed=0
    
    # Check each container
    for container in mida-ocr-api mida-frontend mida-postgres; do
        status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "not found")
        health=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "no healthcheck")
        
        if [ "$status" == "running" ]; then
            if [ "$health" == "healthy" ] || [ "$health" == "no healthcheck" ]; then
                log "INFO" "Container $container: running ($health)"
            else
                log "WARN" "Container $container: running but unhealthy ($health)"
                failed=1
            fi
        else
            log "ERROR" "Container $container: $status"
            failed=1
        fi
    done
    
    return $failed
}

# Check API health endpoint
check_api_health() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null || echo "000")
    
    if [ "$response" == "200" ]; then
        log "INFO" "API health endpoint: OK (HTTP $response)"
        return 0
    else
        log "ERROR" "API health endpoint: FAILED (HTTP $response)"
        send_alert "API Health Check Failed" "API health endpoint returned HTTP $response"
        return 1
    fi
}

# Check frontend
check_frontend() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null || echo "000")
    
    if [ "$response" == "200" ]; then
        log "INFO" "Frontend: OK (HTTP $response)"
        return 0
    else
        log "ERROR" "Frontend: FAILED (HTTP $response)"
        send_alert "Frontend Down" "Frontend returned HTTP $response"
        return 1
    fi
}

# Check disk space
check_disk_space() {
    usage=$(df -h . | awk 'NR==2 {print $5}' | tr -d '%')
    
    if [ "$usage" -lt 80 ]; then
        log "INFO" "Disk usage: ${usage}%"
        return 0
    elif [ "$usage" -lt 90 ]; then
        log "WARN" "Disk usage: ${usage}% (warning threshold)"
        return 0
    else
        log "ERROR" "Disk usage: ${usage}% (critical!)"
        send_alert "Disk Space Critical" "Disk usage is at ${usage}%"
        return 1
    fi
}

# Check memory usage
check_memory() {
    # Get memory usage from Docker stats
    api_mem=$(docker stats --no-stream --format "{{.MemPerc}}" mida-ocr-api 2>/dev/null | tr -d '%' || echo "0")
    
    if [ -n "$api_mem" ]; then
        log "INFO" "API memory usage: ${api_mem}%"
    fi
}

# Check database connection
check_database() {
    result=$(docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-mida}" 2>/dev/null)
    
    if echo "$result" | grep -q "accepting connections"; then
        log "INFO" "Database: accepting connections"
        return 0
    else
        log "ERROR" "Database: not accepting connections"
        send_alert "Database Down" "PostgreSQL is not accepting connections"
        return 1
    fi
}

# Check backup status
check_backups() {
    latest_backup=$(ls -t ./backups/mida_backup_*.sql.gz 2>/dev/null | head -1)
    
    if [ -z "$latest_backup" ]; then
        log "WARN" "No backups found"
        return 0
    fi
    
    backup_age=$(( ($(date +%s) - $(stat -c %Y "$latest_backup" 2>/dev/null || stat -f %m "$latest_backup" 2>/dev/null)) / 3600 ))
    
    if [ "$backup_age" -lt 25 ]; then
        log "INFO" "Latest backup: ${backup_age}h old ($latest_backup)"
        return 0
    else
        log "WARN" "Latest backup: ${backup_age}h old (stale!)"
        send_alert "Backup Stale" "Latest backup is ${backup_age} hours old"
        return 1
    fi
}

# Main monitoring routine
main() {
    log "INFO" "=== Starting health check ==="
    
    local errors=0
    
    check_docker || ((errors++))
    check_containers || ((errors++))
    check_api_health || ((errors++))
    check_frontend || ((errors++))
    check_database || ((errors++))
    check_disk_space || ((errors++))
    check_memory
    check_backups || ((errors++))
    
    if [ $errors -eq 0 ]; then
        log "INFO" "=== All checks passed ==="
    else
        log "ERROR" "=== $errors check(s) failed ==="
        send_alert "Health Check Summary" "$errors health check(s) failed. Check logs for details."
    fi
    
    return $errors
}

# Run main
main
