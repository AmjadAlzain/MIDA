# MIDA OCR Application - Quick Deployment Guide

## Server Details
- **IP Address**: 37.187.49.236
- **SSH Port**: 22
- **RDP Port**: 6638
- **Username**: debian
- **OS**: Debian with Docker pre-installed

## Step-by-Step Deployment

### 1. Connect to Server

**Option A: SSH (Recommended)**
```bash
ssh debian@37.187.49.236
# Password: Leader6639@
```

**Option B: Windows RDP**
- Connect to: `37.187.49.236:6638`
- Username: `debian`
- Password: `Leader6639@`

### 2. Clone the Repository

```bash
# Create app directory
sudo mkdir -p /opt/mida-ocr
sudo chown debian:debian /opt/mida-ocr
cd /opt/mida-ocr

# Clone from your repository (replace with actual URL)
git clone <YOUR_REPOSITORY_URL> .

# Or copy files via SCP from your local machine:
# scp -r /path/to/AgentT/* debian@37.187.49.236:/opt/mida-ocr/
```

### 3. Run the Setup Wizard

```bash
cd /opt/mida-ocr

# Make scripts executable
chmod +x scripts/*.sh

# Run interactive setup
bash scripts/setup.sh
```

The setup wizard will prompt you for:
- **Azure Document Intelligence Endpoint** (from your Azure portal)
- **Azure Document Intelligence API Key** (from your Azure portal)
- **Database password** (auto-generated or custom)
- **Server ports** (default: 80 for frontend, 8000 for API)
- **Number of API workers** (default: 4)

### 4. Alternative: Manual Deployment

If you prefer manual setup:

```bash
cd /opt/mida-ocr

# Create required directories
mkdir -p backups logs

# Copy and configure environment file
cp .env.example .env
nano .env  # Edit with your values

# Build Docker images
docker compose build

# Start database first
docker compose up -d postgres

# Wait for database to be ready (about 15 seconds)
sleep 15

# Run migrations
docker compose run --rm db-migrate

# Start all services
docker compose up -d mida-api mida-frontend db-backup

# Check status
docker compose ps
```

### 5. Verify Deployment

```bash
# Check container status
docker compose ps

# Check API health
curl http://localhost:8000/health

# Check frontend
curl -I http://localhost

# View logs
docker compose logs -f
```

### 6. Configure Firewall (Optional but Recommended)

```bash
# Allow necessary ports
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (frontend)
sudo ufw allow 443/tcp   # HTTPS (future SSL)
sudo ufw enable
```

## Access Your Application

After deployment, access the application at:
- **Frontend**: http://37.187.49.236
- **API**: http://37.187.49.236:8000
- **API Docs**: http://37.187.49.236:8000/docs

## Environment Variables to Configure

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_DI_ENDPOINT` | Azure Document Intelligence endpoint | `https://your-resource.cognitiveservices.azure.com/` |
| `AZURE_DI_KEY` | Azure API key | `your-api-key` |
| `POSTGRES_PASSWORD` | Database password | `secure-password-123` |
| `WORKERS` | Number of API workers | `4` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://your-domain.com` |

## Useful Commands

```bash
# Start services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f mida-api

# Restart services
docker compose restart

# Manual backup
bash scripts/backup.sh

# Restore from backup
bash scripts/restore.sh ./backups/mida_backup_YYYYMMDD_HHMMSS.sql.gz

# Check health
bash scripts/monitor.sh

# View resource usage
docker stats
```

## Backup Information

- **Automatic backups**: Daily at 2 AM
- **Location**: `/opt/mida-ocr/backups/`
- **Retention**: 7 days (configurable via `BACKUP_RETENTION_DAYS`)

## Troubleshooting

### Services not starting
```bash
docker compose logs mida-api
docker compose logs mida-frontend
```

### Database connection issues
```bash
docker compose logs postgres
docker compose exec postgres pg_isready -U mida
```

### API returns 500 errors
```bash
# Check environment variables
docker compose exec mida-api env | grep -E "(AZURE|DATABASE)"

# Check logs
docker compose logs mida-api --tail=100
```

### Reset everything
```bash
docker compose down -v  # Warning: removes all data
docker compose up -d
```

## Security Checklist

- [ ] Changed default database password
- [ ] Configured Azure credentials
- [ ] Set specific CORS origins (not *)
- [ ] Configured firewall
- [ ] Enabled SSL/HTTPS (see below)

## Adding SSL/HTTPS (Recommended for Production)

For production, add SSL using Let's Encrypt:

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```
