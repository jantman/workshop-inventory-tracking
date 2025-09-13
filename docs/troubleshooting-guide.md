# Workshop Inventory Tracking - Troubleshooting Guide

## Table of Contents
1. [Quick Diagnosis](#quick-diagnosis)
2. [Connection Issues](#connection-issues)
3. [Authentication Problems](#authentication-problems)
4. [Data and Search Issues](#data-and-search-issues)
5. [Performance Problems](#performance-problems)
6. [Form and Input Issues](#form-and-input-issues)
7. [Barcode Scanner Issues](#barcode-scanner-issues)
8. [Browser-Specific Issues](#browser-specific-issues)
9. [Server and Deployment Issues](#server-and-deployment-issues)
10. [Audit Logging and Data Reconstruction](#audit-logging-and-data-reconstruction)
11. [Error Code Reference](#error-code-reference)
12. [Diagnostic Tools](#diagnostic-tools)

## Quick Diagnosis

### First Steps for Any Issue
1. **Refresh the page** - Ctrl+F5 (hard refresh)
2. **Check internet connection**
3. **Try in an incognito/private browser window**
4. **Check browser console** for error messages (F12)
5. **Check application status** at `/health` endpoint

### Common Quick Fixes
- Clear browser cache and cookies
- Disable browser extensions
- Try a different browser
- Check if Google Sheets is accessible directly

## Connection Issues

### "Cannot connect to Google Sheets"

#### Symptoms
- Error message on page load
- Blank inventory lists
- Failed form submissions

#### Causes & Solutions

**Internet Connection**
```bash
# Test connectivity
ping google.com
curl -I https://sheets.googleapis.com
```

**Google Sheets API Issues**
- Check [Google Cloud Status](https://status.cloud.google.com)
- Verify API quotas in Google Cloud Console
- Check service account permissions

**Credentials Problems**
```bash
# Verify credentials file exists
ls -la credentials/
# Check file permissions
chmod 600 credentials/service_account.json
```

**Network/Firewall Issues**
- Ensure ports 80/443 are open
- Check corporate firewall settings
- Verify proxy configuration if applicable

### "Service Temporarily Unavailable"

#### Immediate Actions
1. Check application service status:
   ```bash
   sudo systemctl status workshop-inventory
   ```
2. Review recent logs:
   ```bash
   # Application logs via systemd (production)
   sudo journalctl -u workshop-inventory -f
   
   # Or via Docker (if using containers)
   docker logs -f workshop-inventory
   ```
3. Check server resources:
   ```bash
   htop
   df -h
   ```

#### Common Causes
- Service crashed or stopped
- Out of disk space
- Memory exhaustion
- Google API rate limiting

## Authentication Problems

### "Authentication Failed"

#### Check Service Account
1. **Verify service account email** in Google Cloud Console
2. **Check sheet sharing** - ensure service account has Editor access
3. **Regenerate credentials** if necessary

#### Credential File Issues
```bash
# Verify JSON format
python3 -m json.tool credentials/service_account.json

# Check file accessibility
sudo -u workshop-app cat credentials/service_account.json
```

### "Access Denied" on Google Sheets

#### Solutions
1. **Re-share the sheet** with service account email
2. **Check Google Drive permissions** if sheet is in shared drive
3. **Verify sheet ID** in configuration
4. **Test with a new sheet** to isolate permission issues

## Data and Search Issues

### "No items found" when inventory exists

#### Diagnostic Steps
1. **Check Google Sheet directly** - verify data exists
2. **Test raw API connection**:
   ```bash
   python3 test_connection.py
   ```
3. **Clear application cache**
4. **Check sheet name** - must be "Metal" (case-sensitive)

#### Data Format Issues
- **Headers mismatch** - ensure first row matches expected headers
- **Empty rows** - remove blank rows between header and data
- **Character encoding** - ensure UTF-8 encoding
- **Date formats** - use consistent date formatting

### Search Returns Wrong Results

#### Common Causes
1. **Case sensitivity** in text searches
2. **Numeric format mismatch** (fractions vs decimals)
3. **Thread format variations**
4. **Cached results** showing old data

#### Solutions
```bash
# Clear search cache
# In browser console:
localStorage.clear()
```

### Duplicate Items Appearing

#### Investigation
1. **Check for duplicate JA IDs** in sheet
2. **Review item creation logs**:
   ```bash
   # Production deployment
   sudo journalctl -u workshop-inventory | grep "Added item"
   
   # Docker deployment
   docker logs workshop-inventory | grep "Added item"
   ```
3. **Data migration issues** - check original vs migrated data

## Performance Problems

### Slow Page Loading

#### Browser-Side Solutions
```javascript
// Clear browser data (run in console)
localStorage.clear();
sessionStorage.clear();
```

#### Server-Side Investigation
```bash
# Check memory usage
free -h

# Check CPU usage
top -p $(pgrep -f workshop-inventory)

# Check disk I/O
iostat -x 1 5

# Analyze slow queries
# Production: sudo journalctl -u workshop-inventory | grep -i "slow\|timeout"
# Docker: docker logs workshop-inventory | grep -i "slow\|timeout"
```

### Search Taking Too Long

#### Optimization Steps
1. **Add more specific filters** to narrow results
2. **Clear browser cache**
3. **Check network speed** - large datasets take time
4. **Use export function** for large result sets

#### Performance Monitoring
```bash
# Check search performance logs
# Production:
sudo journalctl -u workshop-inventory | grep "search" | tail -20

# Monitor API response times
sudo journalctl -u workshop-inventory | grep "api_access" | grep -E "search|list"
```

### High Memory Usage

#### Investigation
```bash
# Memory usage by process
ps aux | grep workshop
# Detailed memory breakdown
sudo pmap -d $(pgrep -f workshop-inventory)
```

#### Solutions
- Restart application service
- Reduce cache TTL in configuration
- Increase system swap if needed
- Consider adding more RAM

## Form and Input Issues

### Validation Errors

#### Field Format Issues
- **JA ID**: Must be unique, non-empty
- **Dimensions**: Use fractions (1 1/4) or decimals (1.25)
- **Thread Size**: Follow standard format (1/4-20, M10x1.5)
- **Dates**: Use MM/DD/YYYY format

#### Thread Format Examples
```
Valid:   1/4-20, 3/8-16 UNC, M10x1.5, 1/2-13 Acme
Invalid: 1/4x20, M10-1.5, 1/2 Acme thread
```

### Form Data Lost

#### Auto-save Features
- Form data automatically saved to browser storage
- Refresh page to restore unsaved data
- Check browser console for save/restore messages

#### Manual Recovery
```javascript
// Check saved form data (browser console)
console.log(localStorage.getItem('formData'));
```

### Cannot Submit Form

#### Common Issues
1. **Missing required fields** - check for * markers
2. **Validation errors** - review field messages
3. **CSRF token expired** - refresh page
4. **JavaScript disabled** - enable JavaScript
5. **Network connectivity** - check connection

## Barcode Scanner Issues

### Scanner Not Responding

#### Basic Troubleshooting
1. **Test in text editor** - verify scanner works as keyboard
2. **Check USB connection** - try different port
3. **Restart scanner** - power cycle if possible
4. **Test with different device** to isolate issue

#### Configuration Issues
- **Scanner mode**: Must be set to "keyboard wedge" mode
- **Termination character**: Should send Enter/Return
- **Character encoding**: Must match expected format

### Wrong Data from Scanner

#### Common Problems
1. **Damaged barcodes** - verify barcode quality
2. **Scanner configuration** - check programming barcodes
3. **Multiple scans** - ensure single trigger per scan
4. **Format mismatch** - verify expected vs actual format

#### Scanner Programming
Consult scanner manual for:
- Keyboard wedge mode setup
- Add line feed after data
- Character set configuration

### Barcode Format Issues

#### Expected Formats
- **Item IDs**: Standard format (e.g., JA12345)
- **Location codes**: Consistent format
- **Submit code**: Exactly ">>DONE<<"

## Browser-Specific Issues

### Chrome Issues
```javascript
// Clear Chrome data
chrome://settings/clearBrowserData
```
- **Disable extensions** in incognito mode
- **Check for mixed content** warnings
- **Verify JavaScript enabled**

### Firefox Issues
- **Disable Enhanced Tracking Protection** for site
- **Check add-on interference**
- **Clear site data**: Settings → Privacy → Manage Data

### Safari Issues
- **Enable JavaScript**: Preferences → Security
- **Clear website data**: Develop → Empty Caches
- **Check Intelligent Tracking Prevention** settings

### Edge Issues
- **Reset site permissions**
- **Clear browsing data**
- **Check SmartScreen settings**

## Server and Deployment Issues

### Application Won't Start

#### Check Service Status
```bash
sudo systemctl status workshop-inventory
sudo journalctl -u workshop-inventory -n 50
```

#### Common Startup Issues
1. **Port already in use**:
   ```bash
   sudo netstat -tlnp | grep :5000
   sudo lsof -i :5000
   ```

2. **Permission errors**:
   ```bash
   sudo chown -R workshop-app:www-data /path/to/app
   ```

3. **Missing dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configuration errors**:
   ```bash
   python3 -c "from config import Config; print('Config OK')"
   ```

### Database/Sheet Connection Issues

#### Test Connection Script
```python
#!/usr/bin/env python3
import sys
sys.path.append('.')
from app.storage_factory import get_storage_backend

try:
    storage = get_storage_backend()
    result = storage.connect()
    if result.success:
        print("✅ MariaDB connection successful")
        print(f"Database connected")
    else:
        print("❌ Connection failed")
        print(f"Error: {result.error}")
except Exception as e:
    print(f"❌ Exception: {e}")
```

### Web Server Issues (Nginx)

#### Check Configuration
```bash
sudo nginx -t
sudo systemctl status nginx
```

#### Common Nginx Issues
1. **Configuration syntax errors**
2. **SSL certificate problems**
3. **Upstream connection failures**
4. **File permission issues**

#### Nginx Logs
```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

## Audit Logging and Data Reconstruction

The Workshop Inventory Tracking application maintains comprehensive audit logs for all data modification operations (add, edit, move, shorten). These logs are designed to provide sufficient information for manual data reconstruction in case of database corruption or data loss requiring rollback to an earlier state.

### Understanding Audit Log Structure

#### Log Format
All audit logs use structured JSON format with the following key fields:

```json
{
  "timestamp": "2025-09-13T12:45:31.598",
  "level": "INFO",
  "message": "AUDIT: operation_name item=JA000123 phase=success operation completed successfully",
  "logger": "inventory",
  "module": "routes",
  "function": "inventory_add",
  "line": 245,
  "request": {
    "url": "http://localhost/inventory/add",
    "method": "POST",
    "remote_addr": "192.168.1.100",
    "user_agent": "Mozilla/5.0...",
    "user_id": "user@example.com"
  },
  "item_id": "JA000123",
  "audit_data": {
    "form_data": { /* Complete user input */ },
    "item_before": { /* Item state before changes */ },
    "item_after": { /* Item state after changes */ },
    "changes": { /* Specific changes made */ }
  }
}
```

#### Three-Phase Logging
Each operation is logged in up to three phases:
1. **Input Phase**: Captures complete user input when operation starts
2. **Success Phase**: Logs complete before/after states when operation succeeds
3. **Error Phase**: Captures error details and context when operation fails

### Finding Audit Logs

#### Production Deployment (systemd)
```bash
# View all audit logs (last 24 hours)
sudo journalctl -u workshop-inventory --since "24 hours ago" | grep "AUDIT:"

# Search for specific operation types
sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "add_item"
sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "edit_item" 
sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "shorten_item"
sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "batch_move"

# Find logs for specific item
sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "item=JA000123"

# View structured JSON logs
sudo journalctl -u workshop-inventory -o json | jq 'select(.MESSAGE | contains("AUDIT:"))'
```

#### Docker Deployment
```bash
# View all audit logs
docker logs workshop-inventory | grep "AUDIT:"

# Search for specific operations
docker logs workshop-inventory | grep "AUDIT:" | grep "add_item"
docker logs workshop-inventory | grep "AUDIT:" | grep "edit_item"
docker logs workshop-inventory | grep "AUDIT:" | grep "shorten_item"
docker logs workshop-inventory | grep "AUDIT:" | grep "batch_move"

# Find logs for specific item
docker logs workshop-inventory | grep "AUDIT:" | grep "item=JA000123"
```

### Operation-Specific Log Patterns

#### Add Item Operations
```bash
# Find all add operations
grep "AUDIT:.*add_item" /var/log/workshop-inventory.log

# Pattern: AUDIT: add_item item=JA000123 phase=input capturing user input for reconstruction
# Pattern: AUDIT: add_item item=JA000123 phase=success operation completed successfully
# Pattern: AUDIT: add_item item=JA000123 phase=error operation failed
```

**Data Available for Reconstruction:**
- Complete form data (JA ID, type, material, dimensions, location, etc.)
- Item creation timestamp
- User who created the item
- Success confirmation or error details

#### Edit Item Operations  
```bash
# Find all edit operations
grep "AUDIT:.*edit_item" /var/log/workshop-inventory.log

# Pattern: AUDIT: edit_item item=JA000123 phase=input capturing user input for reconstruction
# Pattern: AUDIT: edit_item item=JA000123 phase=success operation completed successfully
# Pattern: AUDIT: edit_item item=JA000123 phase=error operation failed
```

**Data Available for Reconstruction:**
- Complete form data showing new values
- Complete item state before changes
- Complete item state after changes
- Specific fields that were modified
- User who made the changes

#### Shorten Item Operations
```bash
# Find all shorten operations  
grep "AUDIT:.*shorten_item" /var/log/workshop-inventory.log

# Pattern: AUDIT: shorten_item item=JA000123 phase=input capturing user input for reconstruction
# Pattern: AUDIT: shorten_item_service item=JA000123 phase=success operation completed successfully
# Pattern: AUDIT: shorten_item item=JA000123 phase=error operation failed
```

**Data Available for Reconstruction:**
- Original item length and complete state
- New length and cut parameters
- Complete before/after item states  
- Database record IDs (original item deactivated, new item created)
- Cut date and user notes
- User who performed the shortening

#### Batch Move Operations
```bash
# Find all batch move operations
grep "AUDIT:.*batch_move" /var/log/workshop-inventory.log  

# Pattern: AUDIT: batch_move_items batch_phase=input
# Pattern: AUDIT: batch_move_items batch_phase=success processed=5
# Pattern: AUDIT: batch_move_items batch_phase=error
```

**Data Available for Reconstruction:**
- Complete list of items being moved
- Target locations for each item
- Success/failure counts
- List of any failed items with reasons
- User who initiated the move

### Data Reconstruction Procedures

#### Recovering a Deleted/Lost Item (Add Operation)
1. **Find the add operation**:
   ```bash
   sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "add_item" | grep "item=JA000123"
   ```

2. **Extract the JSON log entry** containing form_data:
   ```bash
   sudo journalctl -u workshop-inventory -o json | jq 'select(.MESSAGE | contains("AUDIT: add_item") and contains("item=JA000123") and contains("phase=success"))'
   ```

3. **Reconstruct item from audit_data.form_data**:
   - JA ID, type, shape, material
   - All dimensions (length, width, thickness, etc.)
   - Location and sub-location
   - Purchase information
   - Notes and other metadata

#### Recovering from Incorrect Edit (Edit Operation)
1. **Find the edit operation**:
   ```bash
   sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "edit_item" | grep "item=JA000123" | tail -1
   ```

2. **Extract the before state**:
   ```bash
   sudo journalctl -u workshop-inventory -o json | jq 'select(.MESSAGE | contains("AUDIT: edit_item") and contains("item=JA000123") and contains("phase=success")) | .audit_data.item_before'
   ```

3. **Restore original values** from item_before data

#### Recovering from Incorrect Shortening (Shorten Operation)
1. **Find the shortening operation**:
   ```bash  
   sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "shorten_item" | grep "item=JA000123"
   ```

2. **Extract operation details**:
   ```bash
   # Get the service-level log with complete details
   sudo journalctl -u workshop-inventory -o json | jq 'select(.MESSAGE | contains("AUDIT: shorten_item_service") and contains("item=JA000123") and contains("phase=success"))'
   ```

3. **Reconstruction steps**:
   - Deactivate the current (shortened) item using `new_item_id`
   - Reactivate the original item using `deactivated_item_id`  
   - Restore original length from `item_before.length`
   - Remove shortening notes from `item_before.notes`

#### Recovering from Incorrect Batch Move
1. **Find the batch move operation**:
   ```bash
   sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "batch_move" | grep -A5 -B5 "processed=[0-9]"
   ```

2. **Extract movement details**:
   ```bash
   sudo journalctl -u workshop-inventory -o json | jq 'select(.MESSAGE | contains("batch_move_items") and contains("batch_phase=success")) | .audit_data.batch_input.moves'
   ```

3. **Reverse the moves** by updating each item's location back to its previous value (if known from earlier logs)

### Advanced Log Analysis

#### Finding Related Operations
```bash
# Track an item's complete history
sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "item=JA000123" | sort

# Find all operations by a specific user
sudo journalctl -u workshop-inventory -o json | jq 'select(.MESSAGE | contains("AUDIT:") and .request.user_id=="user@example.com")'

# Find operations within a time range
sudo journalctl -u workshop-inventory --since "2025-09-13 10:00:00" --until "2025-09-13 14:00:00" | grep "AUDIT:"
```

#### Extracting Structured Data
```bash
# Extract all audit data to JSON file for analysis
sudo journalctl -u workshop-inventory -o json | jq 'select(.MESSAGE | contains("AUDIT:")) | {timestamp, message, audit_data}' > audit_extract.json

# Count operations by type
sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep -o "AUDIT: [a-z_]*" | sort | uniq -c

# Find the most active users
sudo journalctl -u workshop-inventory -o json | jq -r 'select(.MESSAGE | contains("AUDIT:")) | .request.user_id' | sort | uniq -c | sort -nr
```

### Automated Reconstruction Scripts

#### Backup Current State Before Reconstruction
```bash
#!/bin/bash
# backup-before-reconstruction.sh
echo "Creating backup before data reconstruction..."
mysqldump -u $DB_USER -p$DB_PASS workshop_inventory > "reconstruction_backup_$(date +%Y%m%d_%H%M%S).sql"
```

#### Item State Extractor
```python
#!/usr/bin/env python3
# extract_item_state.py
import json
import sys
import subprocess

def extract_item_audit_data(ja_id, operation_type="add_item"):
    """Extract audit data for a specific item and operation"""
    cmd = [
        'sudo', 'journalctl', '-u', 'workshop-inventory', '-o', 'json'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                log_entry = json.loads(line)
                message = log_entry.get('MESSAGE', '')
                if (f'AUDIT: {operation_type}' in message and 
                    f'item={ja_id}' in message and 
                    'phase=success' in message):
                    return log_entry.get('audit_data', {})
            except json.JSONDecodeError:
                continue
    except subprocess.CalledProcessError as e:
        print(f"Error running journalctl: {e}")
    
    return None

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python3 extract_item_state.py JA000123")
        sys.exit(1)
    
    ja_id = sys.argv[1]
    audit_data = extract_item_audit_data(ja_id)
    
    if audit_data:
        print(json.dumps(audit_data, indent=2))
    else:
        print(f"No audit data found for item {ja_id}")
```

### Monitoring Audit Log Health

#### Check Audit Logging is Working
```bash
# Verify recent audit logs exist
sudo journalctl -u workshop-inventory --since "1 hour ago" | grep "AUDIT:" | wc -l

# Test pattern - should show recent activity
sudo journalctl -u workshop-inventory | grep "AUDIT:" | tail -5

# Check for any audit logging errors
sudo journalctl -u workshop-inventory | grep -i "audit.*error"
```

#### Audit Log Volume Analysis
```bash
# Operations per hour (last 24 hours)
sudo journalctl -u workshop-inventory --since "24 hours ago" | grep "AUDIT:" | \
  awk '{print $1" "$2" "$3}' | cut -d: -f1-2 | sort | uniq -c

# Most common operations
sudo journalctl -u workshop-inventory | grep "AUDIT:" | \
  grep -o "AUDIT: [a-z_]*" | sort | uniq -c | sort -nr

# Error rate in audit operations  
total=$(sudo journalctl -u workshop-inventory | grep "AUDIT:" | wc -l)
errors=$(sudo journalctl -u workshop-inventory | grep "AUDIT:" | grep "phase=error" | wc -l)
echo "Audit operations: $total, Errors: $errors, Error rate: $(echo "scale=2; $errors*100/$total" | bc)%"
```

This audit logging system provides comprehensive data recovery capabilities. All user operations that modify data are logged with sufficient detail to manually reconstruct the exact changes made, enabling recovery from data corruption or accidental changes.

## Error Code Reference

### HTTP Status Codes
- **400 Bad Request**: Invalid input data or malformed request
- **401 Unauthorized**: Authentication required or failed
- **403 Forbidden**: Access denied to resource
- **404 Not Found**: Item or page not found
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Application error
- **502 Bad Gateway**: Upstream connection failed
- **503 Service Unavailable**: Application not responding

### Application Error Codes
- **VALIDATION_ERROR**: Input validation failed
- **STORAGE_ERROR**: Google Sheets operation failed
- **GOOGLE_SHEETS_ERROR**: Specific Google API error
- **AUTHENTICATION_ERROR**: Credential or permission issue
- **ITEM_NOT_FOUND**: Requested item doesn't exist
- **DUPLICATE_ITEM**: Item with same ID already exists
- **BUSINESS_LOGIC_ERROR**: Operation violates business rules
- **RATE_LIMIT_ERROR**: API quota exceeded
- **TEMPORARY_ERROR**: Transient error, retry recommended

### Google Sheets API Errors
- **quotaExceeded**: API quota exceeded, wait or request increase
- **rateLimitExceeded**: Too many requests, implement backoff
- **userRateLimitExceeded**: Per-user rate limit exceeded
- **dailyLimitExceeded**: Daily quota exceeded
- **forbidden**: Access denied to sheet or API

## Diagnostic Tools

### Health Check Endpoint
```bash
curl -i http://localhost:5000/health
```
Expected response:
```json
{
  "status": "healthy",
  "service": "workshop-inventory-tracking"
}
```

### Performance Metrics
```bash
# Check recent performance logs
# Production:
sudo journalctl -u workshop-inventory -n 100 | grep performance

# Average response times
sudo journalctl -u workshop-inventory | grep "completed in" | \
  grep -oE "[0-9]+ms" | \
  sed 's/ms//' | \
  awk '{sum+=$1; count++} END {printf "Average: %.1f ms\n", sum/count}'
```

### Cache Statistics
Access via Python console:
```python
from app.performance import cache
print(cache.stats())
```

### API Usage Analysis
```bash
# Most accessed endpoints (analyze structured JSON logs)
sudo journalctl -u workshop-inventory | grep "api_access" | \
  grep -o '"endpoint":"[^"]*"' | sort | uniq -c | sort -nr

# Error rate analysis
sudo journalctl -u workshop-inventory | grep -E "Status [45][0-9][0-9]" | wc -l
```

### Memory and Resource Monitoring
```bash
# Real-time monitoring
watch -n 1 'ps aux | grep workshop-inventory | grep -v grep'

# Log monitoring via systemd/Docker
# Production: sudo journalctl -u workshop-inventory --since "1 hour ago" | wc -l
# Docker: docker logs --since="1h" workshop-inventory | wc -l

# Network connection monitoring
watch -n 2 'ss -tuln | grep :5000'
```

### Log Analysis Scripts

#### Error Summary
```bash
#!/bin/bash
# error-summary.sh
echo "=== Error Summary (Last 24 Hours) ==="
# Production deployment
sudo journalctl -u workshop-inventory --since "24 hours ago" | \
  grep -i error | \
  cut -d' ' -f6- | \
  sort | uniq -c | sort -nr | head -10
```

#### Performance Summary  
```bash
#!/bin/bash
# perf-summary.sh
echo "=== Performance Summary ==="
echo "Slowest Operations:"
sudo journalctl -u workshop-inventory | grep "completed in" | \
  sort -k6 -nr | head -5

echo "Most Frequent Operations:"
sudo journalctl -u workshop-inventory | grep "completed in" | \
  awk '{print $4}' | sort | uniq -c | sort -nr | head -5
```

### Browser Developer Tools

#### Console Commands
```javascript
// Check local storage
Object.keys(localStorage).forEach(key => 
  console.log(key + ': ' + localStorage.getItem(key))
);

// Monitor network requests
console.log('Monitoring enabled - check Network tab');

// Check for JavaScript errors
window.addEventListener('error', e => 
  console.error('JS Error:', e.error)
);
```

#### Network Analysis
1. Open Developer Tools (F12)
2. Go to Network tab
3. Reload page and monitor requests
4. Look for failed requests (red status)
5. Check request/response headers

This troubleshooting guide provides systematic approaches to diagnosing and resolving common issues with the Workshop Inventory Tracking application.