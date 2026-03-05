# MIDA OCR Application - Quick Deployment Guide

## Server Requirements

- **OS**: Debian/Ubuntu with Docker pre-installed
- **Ports Required**: 22 (SSH), 80 (HTTP), 8000 (API)
- **Minimum Resources**: 2 CPU cores, 4GB RAM, 20GB storage

---

## Step-by-Step Deployment

### 1. Connect to Server

```bash
ssh <username>@<server-ip>
```

### 2. Clone the Repository

```bash
# Create app directory
sudo mkdir -p /opt/mida-ocr
sudo chown $USER:$USER /opt/mida-ocr
cd /opt/mida-ocr

# Clone from your repository
git clone <YOUR_REPOSITORY_URL> .
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
- **Azure Document Intelligence Endpoint** (from Azure portal)
- **Azure Document Intelligence API Key** (from Azure portal)
- **Database password** (auto-generated or custom)
- **Server ports** (default: 80 for frontend, 8000 for API)
- **Number of API workers** (default: 4)

### 4. Alternative: Manual Deployment

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

# Wait for database to be ready
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

### 6. Configure Firewall (Recommended for Production)

```bash
# Reset firewall if needed
sudo ufw reset

# Allow SSH (to avoid lockout)
sudo ufw allow 22/tcp

# Allow HTTP only from your office/VPN subnets
sudo ufw allow from <YOUR_SUBNET>/24 to any port 80

# Allow API only from your office/VPN subnets
sudo ufw allow from <YOUR_SUBNET>/24 to any port 8000

# Allow HTTPS for future SSL
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Verify rules
sudo ufw status verbose
```

> **Note**: IP whitelisting is also enforced at the application level.
> Configure `ALLOWED_NETWORKS` in your `.env` file — see the
> [Environment Variables](#environment-variables) section.

---

## Access Your Application

After deployment:
- **Frontend**: `http://<your-server-ip>`
- **API Docs**: `http://<your-server-ip>:8000/docs`

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AZURE_DI_ENDPOINT` | Azure Document Intelligence endpoint URL | Yes |
| `AZURE_DI_KEY` | Azure Document Intelligence API key | Yes |
| `POSTGRES_PASSWORD` | Database password (auto-generated if not set) | Yes |
| `ALLOWED_NETWORKS` | Comma-separated CIDR ranges for IP whitelisting | No |
| `API_PORT` | Backend API port (default: 8000) | No |
| `FRONTEND_PORT` | Frontend port (default: 80) | No |
| `CORS_ORIGINS` | Allowed CORS origins | No |
| `WORKERS` | Number of API workers (default: 4) | No |

---

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

---

## Backup Information

- **Automatic backups**: Daily at 2 AM
- **Location**: `/opt/mida-ocr/backups/`
- **Retention**: 7 days (configurable via `BACKUP_RETENTION_DAYS`)

---

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
docker compose run --rm db-migrate
```

---

## Security Checklist

- [ ] Changed default database password
- [ ] Configured Azure credentials
- [ ] Set specific CORS origins (not `*`)
- [ ] Configured `ALLOWED_NETWORKS` in `.env`
- [ ] Configured server firewall (UFW)
- [ ] Enabled SSL/HTTPS for production

---

## Adding SSL/HTTPS (Recommended for Production)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com

# Auto-renewal is configured automatically
```
