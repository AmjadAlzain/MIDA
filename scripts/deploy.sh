#!/bin/bash
# =============================================================================
# MIDA OCR Application - Server Deployment Script
# =============================================================================
# Run this script on the Debian server after cloning the repository
# Usage: ./deploy.sh
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================${NC}\n"
}

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Check if running as root or with sudo
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

print_header "MIDA OCR Application - Server Deployment"

# Step 1: Update system and install prerequisites
print_header "Step 1: System Preparation"

print_info "Updating system packages..."
$SUDO apt-get update -y

print_info "Installing prerequisites..."
$SUDO apt-get install -y \
    git \
    curl \
    openssl \
    ca-certificates \
    gnupg \
    lsb-release

# Step 2: Ensure Docker is properly configured
print_header "Step 2: Docker Configuration"

if command -v docker &> /dev/null; then
    print_success "Docker is installed: $(docker --version)"
else
    print_error "Docker not found! Please install Docker first."
    exit 1
fi

# Add current user to docker group if not already
if ! groups | grep -q docker; then
    print_info "Adding user to docker group..."
    $SUDO usermod -aG docker $USER
    print_warning "You may need to log out and back in for docker group changes to take effect"
fi

# Check if docker compose is available
if docker compose version &> /dev/null; then
    print_success "Docker Compose V2 is available"
elif command -v docker-compose &> /dev/null; then
    print_success "Docker Compose V1 is available"
    # Create alias for consistency
    alias docker-compose="docker compose"
else
    print_error "Docker Compose not found!"
    exit 1
fi

# Ensure Docker daemon is running
if ! docker info &> /dev/null; then
    print_info "Starting Docker daemon..."
    $SUDO systemctl start docker
    $SUDO systemctl enable docker
fi

print_success "Docker is ready"

# Step 3: Create application directory
print_header "Step 3: Application Setup"

APP_DIR="/opt/mida-ocr"

if [ -d "$APP_DIR" ]; then
    print_warning "Application directory exists. Creating backup..."
    $SUDO mv "$APP_DIR" "${APP_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
fi

print_info "Creating application directory..."
$SUDO mkdir -p "$APP_DIR"
$SUDO chown -R $USER:$USER "$APP_DIR"

# Step 4: Clone or copy repository
print_header "Step 4: Deploy Application Files"

# Check if we're already in the repo
if [ -f "docker-compose.yml" ]; then
    print_info "Copying application files..."
    cp -r . "$APP_DIR/"
else
    print_info "Cloning repository..."
    echo "Please enter the Git repository URL:"
    read -p "Repository URL: " REPO_URL
    
    if [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" "$APP_DIR"
    else
        print_error "No repository URL provided!"
        exit 1
    fi
fi

cd "$APP_DIR"

# Step 5: Create required directories
print_header "Step 5: Create Directories"

mkdir -p backups
mkdir -p logs
print_success "Created backups/ and logs/ directories"

# Step 6: Configure environment
print_header "Step 6: Environment Configuration"

if [ ! -f ".env" ]; then
    print_info "No .env file found. Running setup wizard..."
    bash scripts/setup.sh
else
    print_success ".env file exists"
    read -p "Do you want to reconfigure? (y/N): " reconfig
    if [[ "$reconfig" =~ ^[Yy]$ ]]; then
        bash scripts/setup.sh
    fi
fi

# Step 7: Build Docker images
print_header "Step 7: Build Docker Images"

print_info "Building Docker images (this may take a few minutes)..."
docker compose build --no-cache

print_success "Docker images built"

# Step 8: Start database and run migrations
print_header "Step 8: Database Setup"

print_info "Starting database container..."
docker compose up -d postgres

print_info "Waiting for database to be ready..."
sleep 15

print_info "Running database migrations..."
docker compose run --rm db-migrate

print_success "Database migrations completed"

# Step 9: Start all services
print_header "Step 9: Start Services"

print_info "Starting all services..."
docker compose up -d mida-api mida-frontend db-backup

print_info "Waiting for services to start..."
sleep 10

# Step 10: Verify deployment
print_header "Step 10: Verification"

# Check container status
echo ""
echo "Container Status:"
docker compose ps

# Check health
echo ""
echo "Health Checks:"

API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
if [ "$API_HEALTH" == "200" ]; then
    print_success "API is healthy (HTTP $API_HEALTH)"
else
    print_warning "API health check returned HTTP $API_HEALTH"
fi

FRONTEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:80 2>/dev/null || echo "000")
if [ "$FRONTEND_HEALTH" == "200" ]; then
    print_success "Frontend is healthy (HTTP $FRONTEND_HEALTH)"
else
    print_warning "Frontend health check returned HTTP $FRONTEND_HEALTH"
fi

# Step 11: Configure firewall (optional)
print_header "Step 11: Firewall Configuration"

if command -v ufw &> /dev/null; then
    read -p "Configure UFW firewall? (y/N): " config_ufw
    if [[ "$config_ufw" =~ ^[Yy]$ ]]; then
        $SUDO ufw allow 22/tcp     # SSH
        $SUDO ufw allow 80/tcp     # HTTP
        $SUDO ufw allow 443/tcp    # HTTPS (for future SSL)
        $SUDO ufw --force enable
        print_success "Firewall configured"
    fi
else
    print_info "UFW not installed. Skipping firewall configuration."
fi

# Step 12: Setup monitoring cron job
print_header "Step 12: Monitoring Setup"

read -p "Setup monitoring cron job (runs every 5 minutes)? (y/N): " setup_cron
if [[ "$setup_cron" =~ ^[Yy]$ ]]; then
    # Add cron job for monitoring
    CRON_JOB="*/5 * * * * cd $APP_DIR && bash scripts/monitor.sh >> logs/monitor.log 2>&1"
    (crontab -l 2>/dev/null | grep -v "monitor.sh"; echo "$CRON_JOB") | crontab -
    print_success "Monitoring cron job installed"
fi

# Final summary
print_header "Deployment Complete!"

SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "Your MIDA OCR application is now running!"
echo ""
echo "Access URLs:"
echo "  Frontend:  http://${SERVER_IP}"
echo "  API:       http://${SERVER_IP}:8000"
echo "  API Docs:  http://${SERVER_IP}:8000/docs"
echo ""
echo "Application directory: $APP_DIR"
echo ""
echo "Useful commands:"
echo "  cd $APP_DIR"
echo "  docker compose logs -f          # View logs"
echo "  docker compose ps               # Check status"
echo "  docker compose restart          # Restart services"
echo "  make docker-backup              # Create backup"
echo "  make docker-monitor             # Check health"
echo ""
print_info "Backups run daily at 2 AM and are stored in $APP_DIR/backups/"
print_warning "Remember to configure SSL/HTTPS for production!"
echo ""
