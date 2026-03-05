# MIDA OCR API - Deployment Guide

This guide covers deploying the MIDA OCR application using Docker Compose.

## Table of Contents

- [Requirements](#requirements)
- [Environment Configuration](#environment-configuration)
- [Docker Deployment](#docker-deployment)
- [Database Management](#database-management)
- [Security](#security)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Requirements

### Server Requirements

- **OS**: Ubuntu 20.04+ / Debian 11+
- **CPU**: 2+ cores
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 20GB+ for application and data
- **Docker**: 20.10+
- **Docker Compose**: v2.0+

### External Services

- Azure Document Intelligence account (for OCR)
- PostgreSQL 14+ (included in Docker Compose)

---

## Environment Configuration

### Create Environment File

```bash
cp .env.example .env
nano .env  # or your preferred editor
```

### Required Variables

```env
# Azure Document Intelligence (required for OCR)
AZURE_DI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_DI_KEY=your-api-key

# Database
POSTGRES_USER=mida
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=mida

# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
```

### Optional Variables

```env
# Server ports
API_PORT=8000
FRONTEND_PORT=80

# Workers (recommended: 2 * CPU cores + 1)
WORKERS=4

# CORS (use specific origins in production)
CORS_ORIGINS=https://your-domain.com

# IP Whitelisting (comma-separated CIDR ranges)
ALLOWED_NETWORKS=192.168.1.0/24,10.0.0.0/8

# Backups
BACKUP_RETENTION_DAYS=7
```

### Security Notes

- **Never commit `.env` files** to version control
- Use strong, unique passwords for the database
- In production, set `CORS_ORIGINS` to specific domains (not `*`)
- Configure `ALLOWED_NETWORKS` to restrict API access by IP

---

## Docker Deployment

### Build and Start

```bash
# Build Docker images
docker compose build

# Start database first
docker compose up -d postgres

# Wait for database to be ready (15-30 seconds)
sleep 15

# Run database migrations
docker compose run --rm db-migrate

# Start all services
docker compose up -d mida-api mida-frontend db-backup
```

### Verify Deployment

```bash
# Check container status
docker compose ps

# Check API health
curl http://localhost:8000/health

# Check logs
docker compose logs -f
```

### Stop Services

```bash
docker compose down
```

### Full Deployment (Build + Migrate + Start)

```bash
make docker-deploy
```

### Docker Compose Services

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| `mida-api` | `mida-ocr-api` | 8000 | FastAPI backend |
| `mida-frontend` | `mida-frontend` | 80 | Nginx + React SPA |
| `postgres` | `mida-postgres` | 5432 (internal) | PostgreSQL 15 |
| `db-backup` | `mida-db-backup` | — | Daily backup cron |
| `db-migrate` | `mida-db-migrate` | — | One-shot migration |

---

## Database Management

### Run Migrations

```bash
# Docker
docker compose run --rm db-migrate

# Local
cd server && alembic upgrade head

# Makefile
make db-up
```

### Create New Migration

```bash
make db-revision MSG="description of change"
```

### Create Backup

```bash
bash scripts/backup.sh
# or
make docker-backup
```

### Restore Backup

```bash
bash scripts/restore.sh ./backups/mida_backup_YYYYMMDD_HHMMSS.sql.gz
# or
make docker-restore FILE=./backups/mida_backup_YYYYMMDD_HHMMSS.sql.gz
```

### Connect to Database

```bash
docker compose exec postgres psql -U mida -d mida
```

---

## Security

### IP Whitelisting

The application supports IP whitelisting at two levels:

1. **Application level** (`server/app/main.py`): Configure via `ALLOWED_NETWORKS` env var
2. **Nginx level** (`frontend/nginx.conf`): Uncomment and configure `allow`/`deny` directives

```env
# .env
ALLOWED_NETWORKS=192.168.1.0/24,10.0.0.0/8
```

Localhost (`127.0.0.0/8`) and Docker internal networks (`172.28.0.0/16`, `10.0.0.0/8`) are always allowed.

### Firewall (UFW)

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP from specific subnets
sudo ufw allow from <YOUR_SUBNET>/24 to any port 80
sudo ufw allow from <YOUR_SUBNET>/24 to any port 8000

# Enable
sudo ufw enable
```

### SSL/HTTPS

For production, set up SSL with Let's Encrypt:

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Security Checklist

- [ ] Strong, unique database password
- [ ] Azure API credentials configured
- [ ] `CORS_ORIGINS` set to specific domains
- [ ] `ALLOWED_NETWORKS` configured
- [ ] Server firewall enabled
- [ ] SSL/HTTPS enabled
- [ ] Debug mode disabled (`DEBUG=false`)

---

## Monitoring

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f mida-api
```

### Health Check

```bash
curl http://localhost:8000/health

# Or use the monitoring script
bash scripts/monitor.sh
```

### Resource Usage

```bash
docker stats
```

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
docker compose logs mida-api

# Verify environment variables
docker compose exec mida-api env | grep -E "(AZURE|DATABASE)"

# Check database connection
docker compose exec postgres pg_isready -U mida
```

### Azure Document Intelligence Errors

1. Verify endpoint URL format (should end with `/`)
2. Check API key is valid and not expired
3. Ensure resource is active in Azure portal

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker compose ps postgres

# View PostgreSQL logs
docker compose logs postgres

# Test connection
docker compose exec postgres psql -U mida -d mida -c "SELECT 1"
```

### CORS Errors

- Set `CORS_ORIGINS` to specific domains including protocol: `https://yourdomain.com`
- For development: `CORS_ORIGINS=http://localhost,http://localhost:3000`

### Reset Everything

```bash
# Warning: This removes all data!
docker compose down -v
docker compose up -d postgres
sleep 15
docker compose run --rm db-migrate
docker compose up -d mida-api mida-frontend db-backup
```

### Log Analysis (Production)

```bash
# View JSON logs
docker logs mida-ocr-api 2>&1 | python -m json.tool

# Filter errors
docker logs mida-ocr-api 2>&1 | grep '"level":"ERROR"'
```

### Debug Mode

For detailed debugging, update `.env`:
```env
DEBUG=true
LOG_LEVEL=DEBUG
LOG_FORMAT=text
```

Then restart: `docker compose restart mida-api`
