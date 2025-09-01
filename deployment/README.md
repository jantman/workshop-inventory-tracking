# Workshop Inventory Tracking - Deployment Package

This directory contains all the files needed for production deployment of the Workshop Inventory Tracking application.

## Deployment Options

### Option 1: Automated Script Deployment (Recommended)
The automated deployment script handles the complete setup process:

```bash
sudo ./deploy.sh
```

**Features:**
- Complete system setup and configuration
- Service installation and management
- Nginx web server configuration
- Automatic backup setup
- Health monitoring scripts
- Log rotation configuration

### Option 2: Docker Deployment
Use Docker containers for easy deployment and management:

```bash
cd docker/
cp .env.example .env
# Edit .env with your configuration
docker-compose up -d
```

**Features:**
- Containerized application
- Nginx reverse proxy
- Volume persistence
- Health checks
- Easy scaling

## Prerequisites

### System Requirements
- **Operating System**: Ubuntu 20.04+ / CentOS 8+ / Similar Linux distribution
- **Python**: 3.8 or higher
- **Memory**: 1GB RAM minimum, 2GB recommended
- **Storage**: 5GB available space
- **Network**: Internet connection for Google Sheets API

### Google Cloud Setup
1. Create Google Cloud project
2. Enable Google Sheets API
3. Create service account with Editor permissions
4. Download service account JSON key
5. Share Google Sheet with service account email

## Quick Start

### 1. Download and Prepare
```bash
# Download the application
git clone https://github.com/your-org/workshop-inventory-tracking.git
cd workshop-inventory-tracking/deployment

# Make deployment script executable
chmod +x deploy.sh
```

### 2. Run Deployment
```bash
# Run automated deployment (requires sudo)
sudo ./deploy.sh
```

### 3. Configure Application
```bash
# Edit configuration file
sudo nano /opt/workshop-inventory-tracking/.env

# Add Google Sheets credentials
sudo cp your-service-account.json /opt/workshop-inventory-tracking/credentials/service_account.json
sudo chown workshop-app:www-data /opt/workshop-inventory-tracking/credentials/service_account.json
sudo chmod 600 /opt/workshop-inventory-tracking/credentials/service_account.json
```

### 4. Start Services
```bash
# Start the application
sudo systemctl start workshop-inventory
sudo systemctl enable workshop-inventory

# Check status
sudo systemctl status workshop-inventory
```

### 5. Verify Installation
```bash
# Test application
curl http://localhost/health

# Run health check
sudo -u workshop-app /opt/workshop-inventory-tracking/health-check.sh
```

## Files Description

### Core Deployment Files
- **`deploy.sh`** - Automated deployment script
- **`requirements-prod.txt`** - Production Python dependencies
- **`README.md`** - This deployment guide

### Docker Deployment
- **`docker/Dockerfile`** - Application container definition
- **`docker/docker-compose.yml`** - Multi-container orchestration
- **`docker/.env.example`** - Environment variables template

### Configuration Templates
Configuration files are automatically created by the deployment script.

## Configuration

### Environment Variables
Key configuration options in `.env` file:

```bash
# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=your-secret-key-here

# Google Sheets Configuration
GOOGLE_SHEET_ID=your-sheet-id-here
GOOGLE_CREDENTIALS_PATH=credentials/service_account.json

# Application Settings
LOG_LEVEL=INFO
CACHE_TTL=300
BATCH_SIZE=100
```

### Google Sheets Setup
1. **Sheet ID**: Extract from Google Sheets URL
   - URL: `https://docs.google.com/spreadsheets/d/SHEET_ID/edit`
   - Use the `SHEET_ID` part in configuration

2. **Service Account**: 
   - Download JSON key file
   - Place in `credentials/service_account.json`
   - Share sheet with service account email address

3. **Permissions**: Service account needs Editor access to the sheet

## Post-Deployment Setup

### 1. SSL Certificate (Production)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Verify auto-renewal
sudo certbot renew --dry-run
```

### 2. Firewall Configuration
```bash
# Allow HTTP and HTTPS
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh
sudo ufw enable
```

### 3. Backup Configuration
Add backup jobs to crontab:
```bash
sudo crontab -e

# Add these lines:
0 2 * * * /opt/backups/workshop-inventory/backup-app.sh
30 2 * * * /opt/backups/workshop-inventory/backup-sheets.sh
```

### 4. Monitoring Setup
```bash
# Add health check to crontab
sudo crontab -e

# Add this line for hourly health checks:
0 * * * * /opt/workshop-inventory-tracking/health-check.sh >> /var/log/workshop-health.log 2>&1
```

## Management Commands

### Service Management
```bash
# Start/stop/restart application
sudo systemctl start workshop-inventory
sudo systemctl stop workshop-inventory
sudo systemctl restart workshop-inventory

# View service status
sudo systemctl status workshop-inventory

# View logs
sudo journalctl -u workshop-inventory -f
```

### Application Management
```bash
# Health check
sudo -u workshop-app /opt/workshop-inventory-tracking/health-check.sh

# View application logs
sudo tail -f /opt/workshop-inventory-tracking/logs/workshop_inventory.log

# Clear cache (if needed)
sudo systemctl restart workshop-inventory
```

### Backup and Restore
```bash
# Manual backup
sudo /opt/backups/workshop-inventory/backup-app.sh
sudo /opt/backups/workshop-inventory/backup-sheets.sh

# List backups
sudo ls -la /opt/backups/workshop-inventory/

# Restore from backup (example)
sudo systemctl stop workshop-inventory
sudo tar -xzf /opt/backups/workshop-inventory/app_backup_YYYYMMDD_HHMMSS.tar.gz -C /opt/
sudo systemctl start workshop-inventory
```

## Troubleshooting

### Common Issues

#### Application Won't Start
```bash
# Check service logs
sudo journalctl -u workshop-inventory -n 50

# Check configuration
sudo -u workshop-app python3 -c "from config import Config; print('Config OK')"

# Check permissions
sudo ls -la /opt/workshop-inventory-tracking/
```

#### Connection Issues
```bash
# Test Google Sheets connection
cd /opt/workshop-inventory-tracking
sudo -u workshop-app python3 test_connection.py
```

#### Performance Issues
```bash
# Check resource usage
htop
df -h

# Analyze logs
sudo grep -i "slow\|error" /opt/workshop-inventory-tracking/logs/*.log
```

### Log Files
- **Application**: `/opt/workshop-inventory-tracking/logs/`
- **Service**: `sudo journalctl -u workshop-inventory`
- **Nginx**: `/var/log/nginx/`
- **System**: `/var/log/syslog`

## Security Considerations

### File Permissions
- Application files: 755 (readable/executable)
- Configuration files: 600 (owner only)
- Credential files: 600 (owner only)
- Log files: 644 (readable)

### Network Security
- Use HTTPS in production
- Configure firewall appropriately
- Regular security updates
- Monitor access logs

### Data Security
- Secure credential storage
- Regular backups
- Access logging
- Google Sheets sharing permissions

## Support and Maintenance

### Regular Maintenance
- **Daily**: Check service status and error logs
- **Weekly**: Review performance metrics and backup integrity
- **Monthly**: System updates and security review

### Getting Help
1. Check troubleshooting guide: `../docs/troubleshooting-guide.md`
2. Review application logs for error details
3. Test with health check script
4. Check system resource usage

### Updates
To update the application:
1. Stop the service
2. Backup current installation
3. Deploy new version
4. Test thoroughly
5. Start the service

This deployment package provides everything needed for a production-ready Workshop Inventory Tracking installation.