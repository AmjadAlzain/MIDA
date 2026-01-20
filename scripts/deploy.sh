#!/bin/bash
# MIDA Deployment Script for Remote Server
# Usage: ./deploy.sh

set -e

echo "=========================================="
echo "MIDA Application Deployment"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Note: Some commands may require sudo privileges${NC}"
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is not available. Please install Docker Compose.${NC}"
    exit 1
fi

echo -e "${GREEN}Docker and Docker Compose are available${NC}"

# Check for .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}No .env file found. Creating from template...${NC}"
    cp .env.docker .env
    echo -e "${RED}Please edit .env file with your Azure credentials before continuing!${NC}"
    echo "Run: nano .env"
    exit 1
fi

echo -e "${GREEN}.env file found${NC}"

# Pull latest images and build
echo ""
echo "Building Docker images..."
docker compose build

# Start services
echo ""
echo "Starting services..."
docker compose up -d

# Wait for services to be healthy
echo ""
echo "Waiting for services to start..."
sleep 10

# Check service status
echo ""
echo "Service Status:"
docker compose ps

# Show logs summary
echo ""
echo "Recent logs (last 20 lines):"
docker compose logs --tail=20

echo ""
echo "=========================================="
echo -e "${GREEN}Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Access the application at:"
echo "  Frontend: http://$(hostname -I | awk '{print $1}')"
echo "  API:      http://$(hostname -I | awk '{print $1}'):8000"
echo "  API Docs: http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "Useful commands:"
echo "  View logs:      docker compose logs -f"
echo "  Stop services:  docker compose down"
echo "  Restart:        docker compose restart"
echo ""
