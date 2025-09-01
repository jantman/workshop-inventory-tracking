# Workshop Inventory Tracking - Deployment Guide

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Pre-deployment Setup](#pre-deployment-setup)
3. [Installation Process](#installation-process)
4. [Configuration](#configuration)
5. [Google Sheets Setup](#google-sheets-setup)
6. [Production Deployment](#production-deployment)
7. [Monitoring and Maintenance](#monitoring-and-maintenance)
8. [Backup and Recovery](#backup-and-recovery)
9. [Security Considerations](#security-considerations)
10. [Troubleshooting](#troubleshooting)

## System Requirements

### Minimum Requirements
- **OS**: Linux (Ubuntu 20.04+ recommended), macOS, Windows 10+
- **Python**: 3.8 or higher
- **Memory**: 512MB RAM minimum, 1GB recommended
- **Storage**: 1GB available space
- **Network**: Internet connection for Google Sheets API access

### Recommended for Production
- **OS**: Ubuntu 22.04 LTS or similar Linux distribution
- **Python**: 3.11+
- **Memory**: 2GB RAM
- **Storage**: 5GB available space (including logs)
- **Web Server**: Nginx or Apache (for production)
- **Process Manager**: systemd or supervisord

## Pre-deployment Setup

### 1. System Updates
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

### 2. Install Python and Dependencies
```bash
# Ubuntu/Debian
sudo apt install python3 python3-pip python3-venv git -y

# CentOS/RHEL
sudo yum install python3 python3-pip git -y
```

### 3. Create Application User (Production)
```bash
sudo useradd -m -s /bin/bash workshop-app
sudo usermod -aG www-data workshop-app  # For web server access
```

## Installation Process

### 1. Download Application
```bash
# Clone repository
git clone https://github.com/your-org/workshop-inventory-tracking.git
cd workshop-inventory-tracking

# Or download and extract release archive
wget https://github.com/your-org/workshop-inventory-tracking/archive/v1.0.tar.gz
tar -xzf v1.0.tar.gz
cd workshop-inventory-tracking-1.0
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

### 3. Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Create Required Directories
```bash
mkdir -p logs
mkdir -p instance
mkdir -p backups
chmod 755 logs instance backups
```

## Configuration

### 1. Environment Variables
Create `.env` file in project root:
```bash
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=your-secret-key-here-change-this

# Google Sheets Configuration
GOOGLE_SHEET_ID=your-sheet-id-here
GOOGLE_CREDENTIALS_PATH=credentials/service_account.json
GOOGLE_TOKEN_PATH=credentials/token.json

# Logging Configuration
LOG_LEVEL=INFO

# Application Settings
APP_NAME=Workshop Inventory Tracking
APP_VERSION=1.0.0

# Performance Settings
CACHE_TTL=300
BATCH_SIZE=100
```

### 2. Secret Key Generation
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Configuration File (config.py)
Verify configuration settings:
- Database/storage paths
- API credentials paths
- Logging levels
- Security settings

## Google Sheets Setup

### 1. Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create new project or select existing
3. Enable Google Sheets API
4. Enable Google Drive API (for file access)

### 2. Create Service Account
1. Navigate to IAM & Admin → Service Accounts
2. Create new service account
3. Add role: Editor (or custom role with Sheets access)
4. Generate and download JSON key file
5. Save as `credentials/service_account.json`

### 3. Share Google Sheet
1. Open your inventory Google Sheet
2. Share with service account email
3. Grant Editor permissions
4. Copy Sheet ID from URL

### 4. Test Connection
```bash
python3 test_connection.py
```

## Production Deployment

### 1. Web Server Configuration (Nginx)

#### Install Nginx
```bash
sudo apt install nginx -y
```

#### Create Site Configuration
Create `/etc/nginx/sites-available/workshop-inventory`:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /static {
        alias /path/to/workshop-inventory-tracking/app/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
}
```

#### Enable Site
```bash
sudo ln -s /etc/nginx/sites-available/workshop-inventory /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 2. Process Manager (systemd)

Create `/etc/systemd/system/workshop-inventory.service`:
```ini
[Unit]
Description=Workshop Inventory Tracking
After=network.target

[Service]
Type=notify
User=workshop-app
Group=www-data
WorkingDirectory=/path/to/workshop-inventory-tracking
Environment=PATH=/path/to/workshop-inventory-tracking/venv/bin
EnvironmentFile=/path/to/workshop-inventory-tracking/.env
ExecStart=/path/to/workshop-inventory-tracking/venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 2 \
    --timeout 300 \
    --keep-alive 2 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --log-file /path/to/workshop-inventory-tracking/logs/gunicorn.log \
    --log-level info \
    wsgi:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable workshop-inventory
sudo systemctl start workshop-inventory
sudo systemctl status workshop-inventory
```

### 3. SSL/HTTPS Setup (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

## Monitoring and Maintenance

### 1. Log Monitoring

#### Application Logs
- `logs/workshop_inventory.log` - General application logs
- `logs/errors.log` - Error logs only
- `logs/audit.log` - Structured audit trail (JSON)
- `logs/performance.log` - Performance metrics
- `logs/api_access.log` - API access logs

#### System Logs
```bash
# Application service logs
sudo journalctl -u workshop-inventory -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 2. Health Checks
```bash
# Application health endpoint
curl http://localhost:5000/health

# Check service status
sudo systemctl status workshop-inventory
sudo systemctl status nginx
```

### 3. Performance Monitoring
- Monitor log file sizes
- Check memory usage
- Monitor API response times
- Track Google Sheets API quota usage

### 4. Regular Maintenance Tasks

#### Daily
- Check service status
- Review error logs
- Monitor disk space

#### Weekly
- Rotate log files
- Review performance metrics
- Check backup integrity

#### Monthly
- Update system packages
- Review security logs
- Performance optimization review

### 5. Log Rotation
Create `/etc/logrotate.d/workshop-inventory`:
```
/path/to/workshop-inventory-tracking/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        systemctl reload workshop-inventory
    endscript
}
```

## Backup and Recovery

### 1. Backup Strategy

#### Application Files
```bash
#!/bin/bash
# backup-app.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/workshop-inventory"
APP_DIR="/path/to/workshop-inventory-tracking"

mkdir -p "$BACKUP_DIR"

# Create application backup
tar -czf "$BACKUP_DIR/app_backup_$DATE.tar.gz" \
    --exclude="venv" \
    --exclude="*.pyc" \
    --exclude="__pycache__" \
    -C "$(dirname $APP_DIR)" \
    "$(basename $APP_DIR)"

# Keep only last 30 days
find "$BACKUP_DIR" -name "app_backup_*.tar.gz" -mtime +30 -delete
```

#### Google Sheets Backup
```bash
#!/bin/bash
# backup-sheets.sh
DATE=$(date +%Y%m%d_%H%M%S)
python3 -c "
from app.google_sheets_storage import GoogleSheetsStorage
from config import Config
import json

storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
result = storage.read_all('Metal')
if result.success:
    with open(f'backups/sheet_backup_{DATE}.json', 'w') as f:
        json.dump(result.data, f, indent=2)
"
```

### 2. Automated Backups
Add to crontab:
```bash
# Daily application backup at 2 AM
0 2 * * * /path/to/backup-app.sh

# Daily sheets backup at 2:30 AM
30 2 * * * /path/to/backup-sheets.sh
```

### 3. Recovery Procedures

#### Application Recovery
```bash
# Stop service
sudo systemctl stop workshop-inventory

# Restore from backup
cd /path/to
tar -xzf /backups/workshop-inventory/app_backup_YYYYMMDD_HHMMSS.tar.gz

# Restore permissions
chown -R workshop-app:www-data workshop-inventory-tracking

# Restart service
sudo systemctl start workshop-inventory
```

#### Configuration Recovery
- Restore `.env` file
- Restore credentials directory
- Verify Google Sheets access

## Security Considerations

### 1. File Permissions
```bash
# Application files
chmod -R 755 /path/to/workshop-inventory-tracking
chmod -R 640 /path/to/workshop-inventory-tracking/credentials
chmod 600 /path/to/workshop-inventory-tracking/.env

# Log files
chmod -R 644 /path/to/workshop-inventory-tracking/logs
```

### 2. Network Security
- Use HTTPS in production
- Configure firewall rules
- Limit access to management ports
- Regular security updates

### 3. Credential Management
- Store credentials outside web root
- Use environment variables for sensitive data
- Regular credential rotation
- Secure backup of credentials

### 4. Application Security
- CSRF protection enabled
- Input validation and sanitization
- Secure session configuration
- Regular dependency updates

## Troubleshooting

### Common Deployment Issues

#### Service Won't Start
```bash
# Check service status
sudo systemctl status workshop-inventory

# Check logs
sudo journalctl -u workshop-inventory -n 50

# Check application logs
tail -f logs/workshop_inventory.log
```

#### Google Sheets Connection Issues
- Verify credentials file exists and is readable
- Check service account permissions on sheet
- Test API connectivity
- Check quota limits

#### Performance Issues
- Monitor resource usage: `htop` or `top`
- Check log file sizes
- Review database query performance
- Monitor network connectivity

#### SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Renew certificates
sudo certbot renew --dry-run
```

### Log Analysis Commands
```bash
# Error analysis
grep -i error logs/workshop_inventory.log

# Performance metrics
grep "Performance metric" logs/performance.log

# API usage
grep "Status" logs/api_access.log | tail -100
```

### Health Check Script
```bash
#!/bin/bash
# health-check.sh

echo "=== Workshop Inventory Health Check ==="

# Service status
echo "Service Status:"
systemctl is-active workshop-inventory

# HTTP response
echo "HTTP Response:"
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health

# Disk space
echo "Disk Usage:"
df -h | grep -E "/$|/var|/home"

# Memory usage
echo "Memory Usage:"
free -h

echo "=== Health Check Complete ==="
```

This deployment guide provides comprehensive instructions for setting up, configuring, and maintaining the Workshop Inventory Tracking application in production environments.