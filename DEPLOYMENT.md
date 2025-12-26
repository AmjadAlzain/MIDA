# MIDA OCR API Deployment Guide

This guide covers deploying the MIDA OCR API following 12-factor app principles.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Ports](#ports)
- [Run Commands](#run-commands)
- [Docker Deployment](#docker-deployment)
- [Docker Compose](#docker-compose)
- [Health Check](#health-check)
- [Troubleshooting](#troubleshooting)

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_DI_ENDPOINT` | Azure Document Intelligence endpoint URL | `https://your-resource.cognitiveservices.azure.com/` |
| `AZURE_DI_KEY` | Azure Document Intelligence API key | `your-api-key` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `MIDA OCR API` | Application name |
| `APP_VERSION` | `1.0.0` | Application version |
| `ENVIRONMENT` | `development` | Environment: development, staging, production |
| `DEBUG` | `false` | Enable debug mode |
| `HOST` | `0.0.0.0` | Server bind host |
| `PORT` | `8000` | Server bind port |
| `DATABASE_URL` | `None` | Database connection URL (if needed) |
| `CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `LOG_FORMAT` | `json` | Log format: json (production) or text (development) |

### Security Notes

- **Never commit secrets** to version control
- Use `.env` files only for local development
- In production, use proper secret management (Azure Key Vault, AWS Secrets Manager, etc.)
- The `AZURE_DI_KEY` should always be kept secret

---

## Ports

| Port | Protocol | Description |
|------|----------|-------------|
| 8000 | HTTP | Main API server (configurable via `PORT` env var) |

---

## Run Commands

### Local Development

```bash
# Navigate to server directory
cd server

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp ../.env.example .env
# Edit .env with your values

# Run development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production (without Docker)

```bash
cd server
pip install -r requirements.txt

# Set environment variables (use your preferred method)
export AZURE_DI_ENDPOINT="https://..."
export AZURE_DI_KEY="..."
export LOG_FORMAT=json
export ENVIRONMENT=production

# Run with production settings
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Database Migrations

**Important:** Migrations are NOT run automatically at startup. You must run them explicitly.

### Before First Deployment

Run migrations to create the database schema:

```bash
# Using Makefile (from project root)
make db-up

# Or directly with Alembic (from server/ directory)
cd server && alembic upgrade head
```

### Docker / Container Deployment

Run migrations as a one-off command before starting the app:

```bash
# Run migrations in a temporary container
docker run --rm \
    -e DATABASE_URL="postgresql://user:pass@host:5432/mida" \
    mida-ocr-api:latest \
    alembic upgrade head

# Then start the application container
docker run -d ... mida-ocr-api:latest
```

Or use an init container in Kubernetes/Docker Compose.

### Creating New Migrations

After modifying models:

```bash
make db-revision MSG="add users table"
```

---

## Docker Deployment

### Dockerfile

Create `server/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Run

```bash
# Build image
docker build -t mida-ocr-api:latest ./server

# Run container
docker run -d \
    --name mida-ocr-api \
    -p 8000:8000 \
    -e AZURE_DI_ENDPOINT="https://your-resource.cognitiveservices.azure.com/" \
    -e AZURE_DI_KEY="your-api-key" \
    -e ENVIRONMENT=production \
    -e LOG_FORMAT=json \
    -e LOG_LEVEL=INFO \
    mida-ocr-api:latest

# View logs
docker logs -f mida-ocr-api
```

---

## Docker Compose

Create `docker-compose.yml` in project root:

```yaml
version: '3.8'

services:
  mida-api:
    build:
      context: ./server
      dockerfile: Dockerfile
    container_name: mida-ocr-api
    ports:
      - "${PORT:-8000}:8000"
    environment:
      - AZURE_DI_ENDPOINT=${AZURE_DI_ENDPOINT}
      - AZURE_DI_KEY=${AZURE_DI_KEY}
      - DATABASE_URL=${DATABASE_URL:-}
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - LOG_FORMAT=${LOG_FORMAT:-json}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - CORS_ORIGINS=${CORS_ORIGINS:-*}
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
    restart: unless-stopped
    # Optional: uncomment for volume persistence
    # volumes:
    #   - ./data:/app/data

  # Optional: Add database if needed
  # postgres:
  #   image: postgres:15-alpine
  #   container_name: mida-postgres
  #   environment:
  #     POSTGRES_USER: mida
  #     POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  #     POSTGRES_DB: mida
  #   volumes:
  #     - postgres_data:/var/lib/postgresql/data
  #   healthcheck:
  #     test: ["CMD-SHELL", "pg_isready -U mida"]
  #     interval: 10s
  #     timeout: 5s
  #     retries: 5

# volumes:
#   postgres_data:
```

### Docker Compose Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild and restart
docker-compose up -d --build

# Scale (if using multiple workers)
docker-compose up -d --scale mida-api=3
```

---

## Health Check

### Endpoint

```
GET /health
```

### Response

```json
{
    "status": "healthy",
    "app_name": "MIDA OCR API",
    "version": "1.0.0",
    "environment": "production",
    "timestamp": "2025-12-23T10:30:00.000000+00:00"
}
```

### Usage in Load Balancers

- **AWS ALB/ELB**: Configure health check path as `/health`
- **Kubernetes**: Use as liveness and readiness probe
- **Nginx**: Use for upstream health checks

### Kubernetes Probe Example

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## Troubleshooting

### Common Issues

#### 1. Application won't start

**Symptoms**: Container exits immediately or fails to start

**Solutions**:
```bash
# Check logs
docker logs mida-ocr-api

# Verify environment variables
docker exec mida-ocr-api env | grep -E "(AZURE|DATABASE|LOG)"

# Test locally first
cd server && uvicorn app.main:app --reload
```

#### 2. Azure Document Intelligence errors

**Symptoms**: `Missing AZURE_DI_ENDPOINT or AZURE_DI_KEY` error

**Solutions**:
- Verify environment variables are set correctly
- Check Azure resource is active and endpoint URL is correct
- Ensure API key has not expired or been regenerated

```bash
# Test Azure connection
curl -X POST "https://your-resource.cognitiveservices.azure.com/formrecognizer/documentModels/prebuilt-layout:analyze?api-version=2023-07-31" \
    -H "Ocp-Apim-Subscription-Key: your-api-key"
```

#### 3. Health check failing

**Symptoms**: Container marked as unhealthy, `/health` returns error

**Solutions**:
```bash
# Check if app is running
curl http://localhost:8000/health

# Check container health
docker inspect --format='{{.State.Health.Status}}' mida-ocr-api

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' mida-ocr-api
```

#### 4. CORS errors

**Symptoms**: Browser shows CORS policy errors

**Solutions**:
- Set `CORS_ORIGINS` to specific domains: `https://yourdomain.com,https://app.yourdomain.com`
- For development, use `CORS_ORIGINS=*`
- Ensure the origin includes protocol (`https://` not just `yourdomain.com`)

#### 5. Database connection issues

**Symptoms**: `DATABASE_URL` connection errors

**Solutions**:
- Verify database is running and accessible
- Check connection string format
- Ensure network connectivity (especially in Docker networks)

```bash
# Test database connectivity
# PostgreSQL:
pg_isready -h localhost -p 5432 -U user

# From inside container to compose db:
docker exec mida-ocr-api python -c "from app.config import get_settings; print(get_settings().database_url)"
```

#### 6. High memory usage

**Symptoms**: Container OOM killed, slow responses

**Solutions**:
- Increase container memory limits
- Reduce worker count
- Check for memory leaks in PDF processing

```yaml
# docker-compose.yml
services:
  mida-api:
    deploy:
      resources:
        limits:
          memory: 1G
```

### Log Analysis

```bash
# View JSON logs (production)
docker logs mida-ocr-api 2>&1 | jq '.'

# Filter by log level
docker logs mida-ocr-api 2>&1 | jq 'select(.level == "ERROR")'

# Search for specific messages
docker logs mida-ocr-api 2>&1 | grep -i "azure"
```

### Debug Mode

For detailed debugging, set:
```bash
DEBUG=true
LOG_LEVEL=DEBUG
LOG_FORMAT=text  # More readable for debugging
```

---

## Support

For issues not covered here, check:
1. Application logs (`docker logs` or stdout)
2. Azure Document Intelligence metrics in Azure Portal
3. Container resource usage (`docker stats`)
