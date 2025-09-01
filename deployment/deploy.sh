#!/bin/bash
set -e

# Workshop Inventory Tracking - Production Deployment Script
# This script automates the deployment process for production environments

# Configuration
APP_NAME="workshop-inventory"
APP_USER="workshop-app" 
APP_DIR="/opt/workshop-inventory-tracking"
SERVICE_NAME="workshop-inventory"
NGINX_SITE="workshop-inventory"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
    exit 1
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   error "This script must be run as root"
fi

# Check system requirements
check_requirements() {
    log "Checking system requirements..."
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed"
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)'; then
        error "Python 3.8+ is required, found $PYTHON_VERSION"
    fi
    
    # Check required packages
    for pkg in git curl nginx; do
        if ! command -v $pkg &> /dev/null; then
            error "$pkg is not installed"
        fi
    done
    
    log "✓ System requirements met"
}

# Create application user
create_user() {
    log "Creating application user..."
    
    if id "$APP_USER" &>/dev/null; then
        log "✓ User $APP_USER already exists"
    else
        useradd -m -s /bin/bash $APP_USER
        usermod -aG www-data $APP_USER
        log "✓ Created user $APP_USER"
    fi
}

# Install application
install_app() {
    log "Installing application..."
    
    # Create app directory
    mkdir -p $APP_DIR
    chown $APP_USER:www-data $APP_DIR
    
    # Copy application files
    if [ -d "./app" ]; then
        log "Copying application files..."
        cp -r . $APP_DIR/
        chown -R $APP_USER:www-data $APP_DIR
    else
        error "Application files not found. Run this script from the project root directory."
    fi
    
    # Create required directories
    sudo -u $APP_USER mkdir -p $APP_DIR/{logs,instance,backups,credentials}
    
    # Set permissions
    chmod 755 $APP_DIR
    chmod -R 755 $APP_DIR/app
    chmod -R 644 $APP_DIR/logs
    chmod 700 $APP_DIR/credentials
    
    log "✓ Application files installed"
}

# Setup Python environment
setup_python() {
    log "Setting up Python environment..."
    
    cd $APP_DIR
    
    # Create virtual environment
    sudo -u $APP_USER python3 -m venv venv
    
    # Install dependencies
    sudo -u $APP_USER $APP_DIR/venv/bin/pip install --upgrade pip
    sudo -u $APP_USER $APP_DIR/venv/bin/pip install -r deployment/requirements-prod.txt
    
    log "✓ Python environment ready"
}

# Configure environment
configure_env() {
    log "Configuring environment..."
    
    if [ ! -f "$APP_DIR/.env" ]; then
        # Generate secret key
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
        
        # Create .env file
        cat > $APP_DIR/.env << EOF
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=$SECRET_KEY

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
EOF
        
        chown $APP_USER:www-data $APP_DIR/.env
        chmod 600 $APP_DIR/.env
        
        warn "Created .env file with default values. Please update GOOGLE_SHEET_ID and add credentials."
    else
        log "✓ .env file already exists"
    fi
}

# Setup systemd service
setup_systemd() {
    log "Setting up systemd service..."
    
    cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=Workshop Inventory Tracking
After=network.target

[Service]
Type=notify
User=$APP_USER
Group=www-data
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn \\
    --bind 127.0.0.1:5000 \\
    --workers 2 \\
    --worker-class sync \\
    --timeout 300 \\
    --keep-alive 2 \\
    --max-requests 1000 \\
    --max-requests-jitter 50 \\
    --preload \\
    --log-file $APP_DIR/logs/gunicorn.log \\
    --log-level info \\
    --access-logfile $APP_DIR/logs/gunicorn_access.log \\
    wsgi:app
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable $SERVICE_NAME
    
    log "✓ Systemd service configured"
}

# Setup Nginx
setup_nginx() {
    log "Setting up Nginx configuration..."
    
    # Get server name from user or use localhost
    read -p "Enter your domain name (or press Enter for localhost): " DOMAIN
    DOMAIN=${DOMAIN:-localhost}
    
    cat > /etc/nginx/sites-available/$NGINX_SITE << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    client_max_body_size 10M;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    location /static {
        alias $APP_DIR/app/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Gzip compression
        gzip on;
        gzip_types text/css application/javascript text/javascript;
    }
    
    location /favicon.ico {
        alias $APP_DIR/app/static/favicon.ico;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    
    # Hide server version
    server_tokens off;
}
EOF

    # Enable site
    ln -sf /etc/nginx/sites-available/$NGINX_SITE /etc/nginx/sites-enabled/
    
    # Test configuration
    nginx -t || error "Nginx configuration test failed"
    
    log "✓ Nginx configured for domain: $DOMAIN"
}

# Setup log rotation
setup_logrotate() {
    log "Setting up log rotation..."
    
    cat > /etc/logrotate.d/$APP_NAME << EOF
$APP_DIR/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 $APP_USER www-data
    sharedscripts
    postrotate
        systemctl reload $SERVICE_NAME
    endscript
}
EOF

    log "✓ Log rotation configured"
}

# Setup backup scripts
setup_backups() {
    log "Setting up backup scripts..."
    
    mkdir -p /opt/backups/$APP_NAME
    chown $APP_USER:www-data /opt/backups/$APP_NAME
    
    # Application backup script
    cat > /opt/backups/$APP_NAME/backup-app.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups/workshop-inventory"
APP_DIR="/opt/workshop-inventory-tracking"

mkdir -p "$BACKUP_DIR"

# Create application backup
tar -czf "$BACKUP_DIR/app_backup_$DATE.tar.gz" \
    --exclude="venv" \
    --exclude="*.pyc" \
    --exclude="__pycache__" \
    --exclude="logs/*.log*" \
    -C "$(dirname $APP_DIR)" \
    "$(basename $APP_DIR)"

# Keep only last 30 days
find "$BACKUP_DIR" -name "app_backup_*.tar.gz" -mtime +30 -delete

echo "Application backup completed: app_backup_$DATE.tar.gz"
EOF

    # Sheets backup script
    cat > /opt/backups/$APP_NAME/backup-sheets.sh << EOF
#!/bin/bash
DATE=\$(date +%Y%m%d_%H%M%S)
APP_DIR="$APP_DIR"
BACKUP_DIR="/opt/backups/$APP_NAME"

cd \$APP_DIR
source venv/bin/activate

python3 -c "
import sys
import json
from datetime import datetime
sys.path.append('.')
try:
    from app.google_sheets_storage import GoogleSheetsStorage
    from config import Config
    
    storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
    result = storage.read_all('Metal')
    
    if result.success:
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'sheet_data': result.data
        }
        with open('\$BACKUP_DIR/sheet_backup_\$DATE.json', 'w') as f:
            json.dump(backup_data, f, indent=2)
        print('Sheets backup completed: sheet_backup_\$DATE.json')
    else:
        print('Failed to backup sheets:', result.error)
        sys.exit(1)
except Exception as e:
    print('Error during sheets backup:', str(e))
    sys.exit(1)
"

# Keep only last 30 days
find "\$BACKUP_DIR" -name "sheet_backup_*.json" -mtime +30 -delete
EOF

    chmod +x /opt/backups/$APP_NAME/*.sh
    chown $APP_USER:www-data /opt/backups/$APP_NAME/*.sh
    
    log "✓ Backup scripts created"
}

# Setup monitoring
setup_monitoring() {
    log "Setting up monitoring scripts..."
    
    # Health check script
    cat > $APP_DIR/health-check.sh << EOF
#!/bin/bash

echo "=== Workshop Inventory Health Check ==="
echo "Timestamp: \$(date)"
echo

# Service status
echo "Service Status:"
systemctl is-active $SERVICE_NAME
echo

# HTTP response
echo "HTTP Health Check:"
HTTP_STATUS=\$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health)
if [ "\$HTTP_STATUS" = "200" ]; then
    echo "✓ HTTP OK (200)"
else
    echo "✗ HTTP Error (\$HTTP_STATUS)"
fi
echo

# Disk space
echo "Disk Usage:"
df -h | grep -E "/$|/var|/opt" | head -5
echo

# Memory usage
echo "Memory Usage:"
free -h
echo

# Log errors (last hour)
echo "Recent Errors (last hour):"
find $APP_DIR/logs -name "*.log" -mtime -0.05 | xargs grep -i error 2>/dev/null | wc -l | sed 's/^/  /'
echo

echo "=== Health Check Complete ==="
EOF

    chmod +x $APP_DIR/health-check.sh
    chown $APP_USER:www-data $APP_DIR/health-check.sh
    
    log "✓ Health check script created"
}

# Start services
start_services() {
    log "Starting services..."
    
    # Start application
    systemctl start $SERVICE_NAME
    sleep 3
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        log "✓ $SERVICE_NAME started successfully"
    else
        error "$SERVICE_NAME failed to start. Check logs: journalctl -u $SERVICE_NAME"
    fi
    
    # Reload Nginx
    systemctl reload nginx
    
    if systemctl is-active --quiet nginx; then
        log "✓ Nginx reloaded successfully"
    else
        error "Nginx failed to reload"
    fi
}

# Post-deployment verification
verify_deployment() {
    log "Verifying deployment..."
    
    # Check HTTP response
    sleep 5  # Allow time for startup
    
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health || echo "000")
    
    if [ "$HTTP_STATUS" = "200" ]; then
        log "✓ Application responding correctly"
    else
        warn "Application health check failed (HTTP $HTTP_STATUS)"
        warn "Check application logs: journalctl -u $SERVICE_NAME"
    fi
    
    # Check log files
    if [ -f "$APP_DIR/logs/workshop_inventory.log" ]; then
        log "✓ Application logging working"
    else
        warn "No log file found"
    fi
    
    # Display next steps
    echo
    log "=== DEPLOYMENT COMPLETE ==="
    echo
    echo "Next steps:"
    echo "1. Update $APP_DIR/.env with your Google Sheet ID"
    echo "2. Add Google service account credentials to $APP_DIR/credentials/"
    echo "3. Test the application at http://localhost/ (or your domain)"
    echo "4. Set up SSL certificate: sudo certbot --nginx -d yourdomain.com"
    echo "5. Configure backup crontab:"
    echo "   # Daily backups at 2 AM"
    echo "   0 2 * * * /opt/backups/$APP_NAME/backup-app.sh"
    echo "   30 2 * * * /opt/backups/$APP_NAME/backup-sheets.sh"
    echo
    echo "Management commands:"
    echo "  Service status: sudo systemctl status $SERVICE_NAME"
    echo "  View logs: sudo journalctl -u $SERVICE_NAME -f"
    echo "  Health check: sudo -u $APP_USER $APP_DIR/health-check.sh"
    echo
}

# Main deployment process
main() {
    log "Starting Workshop Inventory Tracking deployment..."
    
    check_requirements
    create_user
    install_app
    setup_python
    configure_env
    setup_systemd
    setup_nginx
    setup_logrotate
    setup_backups
    setup_monitoring
    start_services
    verify_deployment
}

# Run main deployment
main "$@"