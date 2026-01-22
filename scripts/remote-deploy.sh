#!/bin/bash
# =============================================================================
# MIDA OCR - One-Line Server Deployment
# =============================================================================
# Run this single command on the server to deploy everything:
#
#   curl -sSL https://raw.githubusercontent.com/YOUR_REPO/main/scripts/remote-deploy.sh | bash
#
# Or copy this file to the server and run:
#   bash remote-deploy.sh
# =============================================================================

set -e

# Configuration - UPDATE THESE VALUES
REPO_URL="${REPO_URL:-}"  # Set this or it will prompt
AZURE_DI_ENDPOINT="${AZURE_DI_ENDPOINT:-}"
AZURE_DI_KEY="${AZURE_DI_KEY:-}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)}"

APP_DIR="/opt/mida-ocr"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  MIDA OCR Application - Remote Deployment ${NC}"
echo -e "${BLUE}============================================${NC}"

# Check for root/sudo
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# Update and install git if needed
echo -e "\n${YELLOW}Installing prerequisites...${NC}"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq git curl openssl

# Verify Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker is installed${NC}"

# Setup app directory
echo -e "\n${YELLOW}Setting up application directory...${NC}"
$SUDO mkdir -p "$APP_DIR"
$SUDO chown -R $USER:$USER "$APP_DIR"
cd "$APP_DIR"

# Clone repository
if [ -z "$REPO_URL" ]; then
    echo -e "${YELLOW}Enter your Git repository URL:${NC}"
    read -p "Repository URL: " REPO_URL
fi

if [ -n "$REPO_URL" ]; then
    echo -e "${YELLOW}Cloning repository...${NC}"
    git clone "$REPO_URL" . 2>/dev/null || git pull origin main
fi

# Create directories
mkdir -p backups logs

# Make scripts executable
chmod +x scripts/*.sh 2>/dev/null || true

# Configure environment
echo -e "\n${YELLOW}Configuring environment...${NC}"

if [ -z "$AZURE_DI_ENDPOINT" ]; then
    echo "Enter Azure Document Intelligence Endpoint:"
    read -p "Endpoint URL: " AZURE_DI_ENDPOINT
fi

if [ -z "$AZURE_DI_KEY" ]; then
    echo "Enter Azure Document Intelligence API Key:"
    read -p "API Key: " AZURE_DI_KEY
fi

# Create .env file
cat > .env << EOF
# MIDA OCR - Production Environment
# Generated: $(date)

# Azure Document Intelligence
AZURE_DI_ENDPOINT=${AZURE_DI_ENDPOINT}
AZURE_DI_KEY=${AZURE_DI_KEY}

# Database
POSTGRES_USER=mida
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=mida

# Application
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
LOG_FORMAT=json

# Server
API_PORT=8000
FRONTEND_PORT=80
WORKERS=4

# CORS
CORS_ORIGINS=*

# Backups
BACKUP_RETENTION_DAYS=7
EOF

chmod 600 .env
echo -e "${GREEN}✓ Environment configured${NC}"
echo -e "${YELLOW}Database password: ${POSTGRES_PASSWORD}${NC}"
echo -e "${YELLOW}(Save this password!)${NC}"

# Build and deploy
echo -e "\n${YELLOW}Building Docker images...${NC}"
docker compose build

echo -e "\n${YELLOW}Starting database...${NC}"
docker compose up -d postgres
sleep 15

echo -e "\n${YELLOW}Running migrations...${NC}"
docker compose run --rm db-migrate

echo -e "\n${YELLOW}Starting all services...${NC}"
docker compose up -d mida-api mida-frontend db-backup
sleep 10

# Verify
echo -e "\n${YELLOW}Verifying deployment...${NC}"
docker compose ps

API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost 2>/dev/null || echo "000")

echo ""
if [ "$API_STATUS" == "200" ]; then
    echo -e "${GREEN}✓ API is healthy${NC}"
else
    echo -e "${YELLOW}⚠ API returned HTTP $API_STATUS${NC}"
fi

if [ "$FRONTEND_STATUS" == "200" ]; then
    echo -e "${GREEN}✓ Frontend is healthy${NC}"
else
    echo -e "${YELLOW}⚠ Frontend returned HTTP $FRONTEND_STATUS${NC}"
fi

SERVER_IP=$(hostname -I | awk '{print $1}')

echo -e "\n${BLUE}============================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "Access your application:"
echo "  Frontend: http://${SERVER_IP}"
echo "  API Docs: http://${SERVER_IP}:8000/docs"
echo ""
echo "Useful commands:"
echo "  cd $APP_DIR"
echo "  docker compose logs -f"
echo "  docker compose ps"
echo ""
