#!/bin/bash
set -e

# Configuration
APP_DIR="/opt/trsmanalytics"
USER="kush"
VENV_PYTHON="$APP_DIR/venv/bin/python"
VENV_PIP="$APP_DIR/venv/bin/pip"

echo "=== Starting Remote Deployment Fix ==="

# 1. Stop conflicting services
echo "[1/7] Stopping potential conflicting services..."
sudo systemctl stop trsmanalytics || true
sudo systemctl stop trsmanalytics-worker || true
sudo systemctl stop returnapp || true
sudo pkill -f gunicorn || true

# 2. Prepare Directory
echo "[2/7] Preparing directory $APP_DIR..."
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR
# Ensure we have write access
if [ ! -w "$APP_DIR" ]; then
    echo "Error: Cannot write to $APP_DIR"
    exit 1
fi

# 3. Extract Code (Assume tarball was uploaded to /tmp/deploy_package.tar.gz)
if [ -f "/tmp/deploy_package.tar.gz" ]; then
    echo "[3/7] Extracting new code..."
    # Extract strip-components=0 because we tarred from root
    tar -xzf /tmp/deploy_package.tar.gz -C $APP_DIR
    rm /tmp/deploy_package.tar.gz
else
    echo "Warning: /tmp/deploy_package.tar.gz not found. Assuming code was rsync'd."
fi

# 4. Setup Virtualenv
echo "[4/7] Setting up virtual environment..."
cd $APP_DIR
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Creating venv..."
    python3 -m venv venv
fi

# Upgrade pip and install deps
$VENV_PIP install --upgrade pip
if [ -f "requirements.txt" ]; then
    echo "Installing requirements..."
    $VENV_PIP install -r requirements.txt
    $VENV_PIP install gunicorn psycopg2-binary
else
    echo "Error: requirements.txt not found!"
    exit 1
fi

# 5. Configure Systemd
echo "[5/7] Configuring Systemd..."
# We assume service files are in $APP_DIR/deploy/
if [ -d "deploy" ]; then
    sudo cp deploy/trsmanalytics.service /etc/systemd/system/
    sudo cp deploy/trsmanalytics-worker.service /etc/systemd/system/
    sudo systemctl daemon-reload
else
    echo "Error: deploy/ directory not found in package!"
    exit 1
fi

# 6. Start Services
echo "[6/7] Starting application..."
sudo systemctl enable --now trsmanalytics
sudo systemctl enable --now trsmanalytics-worker
sudo systemctl restart trsmanalytics
sudo systemctl restart trsmanalytics-worker

# 7. Nginx Fix
echo "[7/7] Reloading Nginx..."
sudo nginx -t
sudo systemctl reload nginx

echo "=== Deployment Complete ==="
echo "Checking health..."
sleep 2
curl -I http://127.0.0.1/analytics/ || echo "Local curl failed"