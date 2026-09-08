#!/bin/bash
# ==============================================================================
# SIH Dead Reckoning Backend - VPS Automated Deployment Script
# Supports: Ubuntu 20.04/22.04/24.04, Debian, Amazon Linux 2023
# ==============================================================================

set -e

echo "========================================================="
echo " Starting SIH Dead Reckoning Backend Deployment..."
echo "========================================================="

# 1. Update system packages
echo "[1/5] Updating package repositories..."
sudo apt-get update -y || sudo yum update -y

# 2. Check and install Docker & Docker Compose if missing
if ! command -v docker &> /dev/null; then
    echo "[2/5] Docker not found. Installing Docker Engine..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    sudo usermod -aG docker $USER
    echo "Docker installed successfully."
else
    echo "[2/5] Docker is already installed: $(docker --version)"
fi

# 3. Verify Docker Compose plugin
if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    sudo apt-get install -y docker-compose-plugin || sudo yum install -y docker-compose-plugin
fi

# 4. Prepare Environment Variables
if [ ! -f .env ]; then
    echo "[3/5] Creating .env from .env.example..."
    cp .env.example .env
else
    echo "[3/5] Using existing .env configuration."
fi

# 5. Build and Launch Containers
echo "[4/5] Building and launching multi-container stack (FastAPI + Redis + TimescaleDB)..."
sudo docker compose down --remove-orphans || true
sudo docker compose up -d --build

# 6. Verification and Healthcheck
echo "[5/5] Waiting for services to stabilize..."
sleep 5

echo ""
echo "========================================================="
echo " Deployment Complete! Checking container statuses:"
echo "========================================================="
sudo docker compose ps

echo ""
echo "Testing Backend Health Endpoint:"
curl -s http://localhost:8000/health || echo "Endpoint starting up..."
echo ""
echo "Your backend is now LIVE on port 8000!"
echo "WebSocket URL: ws://<YOUR_VPS_PUBLIC_IP>:8000/ws/track/{device_id}?token=<jwt>"
echo "API Docs:      http://<YOUR_VPS_PUBLIC_IP>:8000/docs"
echo "========================================================="
