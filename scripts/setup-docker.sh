#!/bin/bash
# Quick setup script for fresh Debian server
# Run this first if Docker needs configuration

set -e

echo "Setting up Docker permissions..."

# Add current user to docker group (if not root)
if [ "$EUID" -ne 0 ]; then
    sudo usermod -aG docker $USER
    echo "Added $USER to docker group. You may need to log out and back in."
fi

# Start Docker service if not running
sudo systemctl start docker
sudo systemctl enable docker

echo "Docker setup complete!"
echo ""
echo "If you just added yourself to the docker group, please run:"
echo "  newgrp docker"
echo "Or log out and log back in."
