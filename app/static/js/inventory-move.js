/**
 * Inventory Move JavaScript - Batch Movement Interface
 * 
 * Handles barcode scanning, move queue management, validation, and execution
 * for batch inventory movements.
 */

class InventoryMoveManager {
    constructor() {
        this.moveQueue = [];
        this.currentExpectedInput = 'ja_id'; // 'ja_id' or 'location'
        this.currentJaId = null;
        this.scannerTimeout = null;
        this.scannerDelay = 100; // ms delay to detect scanner input
        this.manualEntryMode = false;
        
        this.initializeElements();
        this.bindEvents();
        this.updateUI();
        
        console.log('InventoryMoveManager initialized');
    }
    
    initializeElements() {
        // Input elements
        this.barcodeInput = document.getElementById('barcode-input');
        this.manualEntryCheckbox = document.getElementById('manual-entry-mode');
        
        // Status elements
        this.scannerStatus = document.getElementById('scanner-status');
        this.inputStatus = document.getElementById('input-status');
        this.statusText = document.getElementById('status-text');
        this.queueCount = document.getElementById('queue-count');
        
        // Queue display elements
        this.queueEmpty = document.getElementById('move-queue-empty');
        this.queueList = document.getElementById('move-queue-list');
        this.queueItems = document.getElementById('queue-items');
        
        // Button elements
        this.clearAllBtn = document.getElementById('clear-all-btn');
        this.clearQueueBtn = document.getElementById('clear-queue-btn');
        this.validateBtn = document.getElementById('validate-btn');
        this.executeMoveBtn = document.getElementById('execute-moves-btn');
        
        // Alert elements
        this.formAlerts = document.getElementById('form-alerts');
        this.validationSection = document.getElementById('validation-section');
        this.validationResults = document.getElementById('validation-results');
    }
    
    bindEvents() {
        // Barcode input handling
        this.barcodeInput.addEventListener('input', (e) => this.handleBarcodeInput(e));
        this.barcodeInput.addEventListener('keydown', (e) => this.handleKeyDown(e));
        
        // Manual entry mode toggle
        this.manualEntryCheckbox.addEventListener('change', (e) => {
            this.manualEntryMode = e.target.checked;
            this.updateScannerStatus();
        });
        
        // Button events
        this.clearAllBtn.addEventListener('click', () => this.clearAll());
        this.clearQueueBtn.addEventListener('click', () => this.clearQueue());
        this.validateBtn.addEventListener('click', () => this.validateMoves());
        this.executeMoveBtn.addEventListener('click', () => this.executeMoves());
        
        // Focus on barcode input when page loads
        this.barcodeInput.focus();
    }
    
    handleKeyDown(e) {
        // Handle Enter key for both manual and automated modes
        if (e.key === 'Enter') {
            e.preventDefault();
            
            // Clear any pending scanner timeout since Enter takes precedence
            if (this.scannerTimeout) {
                clearTimeout(this.scannerTimeout);
                this.scannerTimeout = null;
            }
            
            this.processInput();
        }
    }
    
    handleBarcodeInput(e) {
        const value = e.target.value.trim();
        
        if (!value) return;
        
        // Clear any existing timeout
        if (this.scannerTimeout) {
            clearTimeout(this.scannerTimeout);
        }
        
        // Check for >>DONE<< immediately (special case for ending scanning session)
        if (this.isDoneCode(value)) {
            this.handleDoneCode();
            return;
        }
        
        // For barcode scanners that automatically add newline, set a short timeout
        // This allows the scanner's newline to be processed by handleKeyDown
        if (!this.manualEntryMode) {
            this.scannerTimeout = setTimeout(() => {
                // If we reach here, the scanner didn't send Enter, so process directly
                this.processInput();
            }, this.scannerDelay);
        }
        
        // In manual entry mode, only process on Enter key (handled in handleKeyDown)
    }
    
    processInput() {
        const value = this.barcodeInput.value.trim().toUpperCase();
        
        if (!value) {
            this.showAlert('Please enter a value', 'warning');
            return;
        }
        
        // Check for done code
        if (this.isDoneCode(value)) {
            this.handleDoneCode();
            return;
        }
        
        if (this.currentExpectedInput === 'ja_id') {
            this.handleJaIdInput(value);
        } else {
            this.handleLocationInput(value);
        }
    }
    
    isDoneCode(value) {
        const cleanValue = value.replace(/[<>]/g, '').toUpperCase();
        return cleanValue === 'DONE' || value === '>>DONE<<';
    }
    
    handleJaIdInput(jaId) {
        // Validate JA ID format
        if (!this.isValidJaId(jaId)) {
            this.showAlert(`Invalid JA ID format: ${jaId}. Expected format: JA000001`, 'danger');
            this.clearInput();
            return;
        }
        
        // Check if this JA ID is already in queue
        if (this.moveQueue.some(item => item.jaId === jaId)) {
            this.showAlert(`Item ${jaId} is already in the move queue`, 'warning');
            this.clearInput();
            return;
        }
        
        // Store the JA ID and wait for location
        this.currentJaId = jaId;
        this.currentExpectedInput = 'location';
        this.clearInput();
        this.updateStatus(`JA ID ${jaId} scanned. Now scan or enter the new location.`);
        this.updateScannerStatus('Waiting for Location');
    }
    
    handleLocationInput(location) {
        if (!location || location.length < 1) {
            this.showAlert('Location cannot be empty', 'warning');
            return;
        }
        
        // Add to move queue
        const moveItem = {
            jaId: this.currentJaId,
            newLocation: location,
            status: 'pending',
            timestamp: new Date().toISOString()
        };
        
        this.moveQueue.push(moveItem);
        
        // Reset for next item
        this.currentJaId = null;
        this.currentExpectedInput = 'ja_id';
        this.clearInput();
        this.updateStatus(`Added ${moveItem.jaId} → ${location} to queue. Ready to scan next JA ID.`);
        this.updateScannerStatus('Ready for JA ID');
        this.updateUI();
        
        console.log('Added to move queue:', moveItem);
    }
    
    handleDoneCode() {
        this.clearInput();
        
        if (this.moveQueue.length === 0) {
            this.showAlert('No items in move queue. Add some items before finishing.', 'warning');
            return;
        }
        
        // If we were waiting for a location, clear the partial entry
        if (this.currentExpectedInput === 'location') {
            this.currentJaId = null;
            this.currentExpectedInput = 'ja_id';
            this.showAlert('Partial entry cleared. You can add more items or proceed with validation.', 'info');
        }
        
        this.updateStatus(`Scan completed. ${this.moveQueue.length} items queued for moving.`);
        this.updateScannerStatus('Done - Ready to Validate');
        this.validateBtn.disabled = false;
    }
    
    isValidJaId(jaId) {
        // JA ID format: JA followed by 6 digits
        const jaIdPattern = /^JA\d{6}$/;
        return jaIdPattern.test(jaId);
    }
    
    clearInput() {
        this.barcodeInput.value = '';
    }
    
    clearAll() {
        this.clearQueue();
        this.currentJaId = null;
        this.currentExpectedInput = 'ja_id';
        this.updateStatus('All data cleared. Ready to scan first JA ID.');
        this.updateScannerStatus('Ready');
        this.hideValidationResults();
        this.clearAlerts();
    }
    
    clearQueue() {
        this.moveQueue = [];
        this.updateUI();
        this.validateBtn.disabled = true;
        this.executeMoveBtn.disabled = true;
    }
    
    updateUI() {
        this.updateQueueDisplay();
        this.updateButtonStates();
    }
    
    updateQueueDisplay() {
        const count = this.moveQueue.length;
        this.queueCount.textContent = `${count} item${count !== 1 ? 's' : ''}`;
        
        if (count === 0) {
            this.queueEmpty.style.display = 'block';
            this.queueList.classList.add('d-none');
            this.clearQueueBtn.disabled = true;
        } else {
            this.queueEmpty.style.display = 'none';
            this.queueList.classList.remove('d-none');
            this.clearQueueBtn.disabled = false;
            this.renderQueueItems();
        }
    }
    
    renderQueueItems() {
        this.queueItems.innerHTML = '';
        
        this.moveQueue.forEach((item, index) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    <strong>${item.jaId}</strong>
                    ${item.itemInfo ? `<br><small class="text-muted">${item.itemInfo}</small>` : ''}
                </td>
                <td>
                    <span class="text-muted">${item.currentLocation || 'Unknown'}</span>
                </td>
                <td>
                    <span class="fw-bold text-primary">${item.newLocation}</span>
                </td>
                <td>
                    <span class="badge ${this.getStatusBadgeClass(item.status)}">${item.status}</span>
                </td>
                <td>
                    <button type="button" class="btn btn-sm btn-outline-danger" 
                            onclick="window.moveManager.removeFromQueue(${index})"
                            title="Remove from queue">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            this.queueItems.appendChild(row);
        });
    }
    
    getStatusBadgeClass(status) {
        switch (status) {
            case 'pending': return 'bg-secondary';
            case 'validated': return 'bg-success';
            case 'error': return 'bg-danger';
            case 'not_found': return 'bg-warning';
            default: return 'bg-secondary';
        }
    }
    
    removeFromQueue(index) {
        if (index >= 0 && index < this.moveQueue.length) {
            const removed = this.moveQueue.splice(index, 1)[0];
            this.updateUI();
            this.showAlert(`Removed ${removed.jaId} from move queue`, 'info');
            
            // If queue becomes empty, reset validation
            if (this.moveQueue.length === 0) {
                this.hideValidationResults();
            }
        }
    }
    
    updateButtonStates() {
        const hasItems = this.moveQueue.length > 0;
        this.clearQueueBtn.disabled = !hasItems;
        
        // Validate button enabled when we have items and not currently expecting location
        this.validateBtn.disabled = !hasItems || this.currentExpectedInput === 'location';
        
        // Execute moves button only enabled after successful validation
        const allValidated = hasItems && this.moveQueue.every(item => item.status === 'validated');
        this.executeMoveBtn.disabled = !allValidated;
    }
    
    updateStatus(message) {
        this.statusText.textContent = message;
    }
    
    updateScannerStatus(status = 'Ready') {
        this.scannerStatus.textContent = status;
        this.scannerStatus.className = 'badge ms-2 ' + this.getScannerStatusClass(status);
    }
    
    getScannerStatusClass(status) {
        if (status.includes('Ready')) return 'bg-success';
        if (status.includes('Waiting')) return 'bg-warning';
        if (status.includes('Done')) return 'bg-info';
        if (status.includes('Error')) return 'bg-danger';
        return 'bg-secondary';
    }
    
    async validateMoves() {
        if (this.moveQueue.length === 0) {
            this.showAlert('No items to validate', 'warning');
            return;
        }
        
        this.validateBtn.disabled = true;
        this.validateBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Validating...';
        
        try {
            // Validate each item
            const validationPromises = this.moveQueue.map(item => this.validateMoveItem(item));
            const results = await Promise.all(validationPromises);
            
            // Update move queue with validation results
            results.forEach((result, index) => {
                this.moveQueue[index] = { ...this.moveQueue[index], ...result };
            });
            
            this.displayValidationResults();
            this.updateUI();
            
        } catch (error) {
            console.error('Validation error:', error);
            this.showAlert('Validation failed. Please try again.', 'danger');
        } finally {
            this.validateBtn.disabled = false;
            this.validateBtn.innerHTML = '<i class="bi bi-check-square"></i> Validate & Preview';
        }
    }
    
    async validateMoveItem(item) {
        try {
            // Check if item exists
            const response = await fetch(`/api/items/${item.jaId}/exists`);
            const data = await response.json();
            
            if (!data.success) {
                return {
                    status: 'error',
                    error: 'Failed to validate item existence'
                };
            }
            
            if (!data.exists) {
                return {
                    status: 'not_found',
                    error: `Item ${item.jaId} not found in inventory`
                };
            }
            
            // Get item details (this would need a separate API endpoint)
            try {
                const detailResponse = await fetch(`/api/items/${item.jaId}`);
                if (detailResponse.ok) {
                    const detailData = await detailResponse.json();
                    return {
                        status: 'validated',
                        currentLocation: detailData.location || 'Unknown',
                        itemInfo: detailData.display_name || item.jaId
                    };
                }
            } catch (e) {
                console.log('Could not fetch item details:', e);
            }
            
            // Basic validation passed
            return {
                status: 'validated',
                currentLocation: 'Unknown'
            };
            
        } catch (error) {
            console.error('Error validating item:', error);
            return {
                status: 'error',
                error: 'Validation failed'
            };
        }
    }
    
    displayValidationResults() {
        const validCount = this.moveQueue.filter(item => item.status === 'validated').length;
        const errorCount = this.moveQueue.filter(item => item.status === 'error').length;
        const notFoundCount = this.moveQueue.filter(item => item.status === 'not_found').length;
        
        let resultsHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-success">${validCount}</div>
                        <small class="text-muted">Valid Items</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-danger">${errorCount}</div>
                        <small class="text-muted">Errors</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-warning">${notFoundCount}</div>
                        <small class="text-muted">Not Found</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-info">${this.moveQueue.length}</div>
                        <small class="text-muted">Total Items</small>
                    </div>
                </div>
            </div>
        `;
        
        if (errorCount > 0 || notFoundCount > 0) {
            resultsHTML += '<div class="alert alert-warning mt-3">';
            resultsHTML += '<i class="bi bi-exclamation-triangle"></i> ';
            resultsHTML += 'Some items have validation issues. Please review the move queue and remove or correct problematic items before executing moves.';
            resultsHTML += '</div>';
        } else {
            resultsHTML += '<div class="alert alert-success mt-3">';
            resultsHTML += '<i class="bi bi-check-circle"></i> ';
            resultsHTML += 'All items validated successfully! You can now execute the moves.';
            resultsHTML += '</div>';
        }
        
        this.validationResults.innerHTML = resultsHTML;
        this.validationSection.style.display = 'block';
    }
    
    hideValidationResults() {
        this.validationSection.style.display = 'none';
    }
    
    async executeMoves() {
        const validItems = this.moveQueue.filter(item => item.status === 'validated');
        
        if (validItems.length === 0) {
            this.showAlert('No valid items to move', 'warning');
            return;
        }
        
        if (!confirm(`Are you sure you want to move ${validItems.length} items? This action cannot be undone.`)) {
            return;
        }
        
        this.executeMoveBtn.disabled = true;
        this.executeMoveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Moving Items...';
        
        try {
            const response = await fetch('/api/inventory/batch-move', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                },
                body: JSON.stringify({
                    moves: validItems.map(item => ({
                        ja_id: item.jaId,
                        new_location: item.newLocation
                    }))
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showAlert(`Successfully moved ${result.moved_count} items!`, 'success');
                this.clearAll();
            } else {
                this.showAlert(`Move failed: ${result.error}`, 'danger');
            }
            
        } catch (error) {
            console.error('Execute moves error:', error);
            this.showAlert('Failed to execute moves. Please try again.', 'danger');
        } finally {
            this.executeMoveBtn.disabled = false;
            this.executeMoveBtn.innerHTML = '<i class="bi bi-play-fill"></i> Execute Moves';
        }
    }
    
    showAlert(message, type = 'info') {
        const alertClass = `alert-${type}`;
        const iconClass = type === 'danger' ? 'bi-exclamation-triangle' : 
                         type === 'success' ? 'bi-check-circle' : 
                         type === 'warning' ? 'bi-exclamation-triangle' :
                         'bi-info-circle';
        
        const alertHTML = `
            <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
                <i class="bi ${iconClass}"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        this.formAlerts.innerHTML = alertHTML;
        
        // Auto-dismiss info and success alerts after 5 seconds
        if (type === 'info' || type === 'success') {
            setTimeout(() => {
                const alert = this.formAlerts.querySelector('.alert');
                if (alert) {
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                }
            }, 5000);
        }
    }
    
    clearAlerts() {
        this.formAlerts.innerHTML = '';
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.moveManager = new InventoryMoveManager();
});