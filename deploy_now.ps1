# PowerShell Deployment Script for TRSM Analytics
$ErrorActionPreference = "Stop"

$SERVER_IP = "10.4.21.7"
$USER = "kush"
$TAR_FILE = "deploy_package.tar.gz"

Write-Host "=== TRSM Analytics Deployment ===" -ForegroundColor Cyan
Write-Host "1. Packaging files..."

# Create tarball (Windows tar is bsdtar)
# Exclude heavy/unnecessary folders
tar --exclude "venv" --exclude ".git" --exclude "__pycache__" --exclude ".pytest_cache" --exclude "tests" --exclude "*.md" --exclude ".env" -czf $TAR_FILE *

if (-not (Test-Path $TAR_FILE)) {
    Write-Error "Failed to create tarball."
    exit 1
}

Write-Host "2. Uploading package to server..." -ForegroundColor Yellow
Write-Host "   (Enter password for $USER@$SERVER_IP if prompted)"
scp $TAR_FILE ${USER}@${SERVER_IP}:/tmp/$TAR_FILE

if ($LASTEXITCODE -ne 0) {
    Write-Error "SCP failed. Aborting."
    exit 1
}

Write-Host "3. Executing Remote Setup..." -ForegroundColor Yellow
Write-Host "   (Enter password again if prompted)"

# 1. Create dir
# 2. Extract
# 3. Run Fix Script
$REMOTE_CMD = "sudo mkdir -p /opt/trsmanalytics && sudo chown $USER /opt/trsmanalytics && tar -xzf /tmp/$TAR_FILE -C /opt/trsmanalytics && chmod +x /opt/trsmanalytics/DEPLOY_FIX.sh && /opt/trsmanalytics/DEPLOY_FIX.sh"

ssh -t ${USER}@${SERVER_IP} $REMOTE_CMD

Write-Host "=== Deployment Finished ===" -ForegroundColor Green
Remove-Item $TAR_FILE