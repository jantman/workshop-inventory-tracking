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
10. [Error Code Reference](#error-code-reference)
11. [Diagnostic Tools](#diagnostic-tools)

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
from app.google_sheets_storage import GoogleSheetsStorage
from config import Config

try:
    storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
    result = storage.connect()
    if result.success:
        print("✅ Connection successful")
        print(f"Sheet: {result.data.get('title')}")
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