/**
 * Inventory Move JavaScript - Batch Movement Interface
 * 
 * Handles barcode scanning, move queue management, validation, and execution
 * for batch inventory movements.
 */

class InventoryMoveManager {
    constructor() {
        this.moveQueue = [];
        // State machine: 'ja_id', 'location', or 'ja_id_or_sub_location'
        // 'ja_id_or_sub_location' means we've received a location and are waiting for
        // either the next JA ID (no sub-location) or a sub-location string
        this.currentExpectedInput = 'ja_id';
        this.currentJaId = null;
        this.currentLocation = null;
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
    
    /**
     * Location Pattern Validation Functions
     *
     * These functions implement the centralized location pattern validation logic
     * matching the backend implementation in app/utils/location_validator.py
     *
     * Pattern Rules (applied in order):
     * 1. JA ID: ^JA[0-9]+$
     * 2. Location Patterns:
     *    - Metal stock storage: ^M[0-9]+.*
     *    - Threaded stock storage: ^T[0-9]+.*
     *    - General storage: exact match "Other"
     * 3. Sub-location: Any string NOT matching the above
     */

    isJaId(value) {
        // JA ID pattern: JA followed by one or more digits
        return /^JA[0-9]+$/.test(value);
    }

    isLocation(value) {
        if (!value || value.length === 0) {
            return false;
        }

        // Metal stock storage pattern
        if (/^M[0-9]+.*/.test(value)) {
            return true;
        }

        // Threaded stock storage pattern
        if (/^T[0-9]+.*/.test(value)) {
            return true;
        }

        // Exact match for "Other" (case-sensitive)
        if (value === 'Other') {
            return true;
        }

        return false;
    }

    classifyInput(value) {
        // Classify input as 'ja_id', 'location', or 'sub_location'
        if (this.isJaId(value)) {
            return 'ja_id';
        } else if (this.isLocation(value)) {
            return 'location';
        } else {
            return 'sub_location';
        }
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
        const value = this.barcodeInput.value.trim();

        if (!value) {
            this.showAlert('Please enter a value', 'warning');
            return;
        }

        // Check for done code
        if (this.isDoneCode(value)) {
            this.handleDoneCode();
            return;
        }

        // Classify the input
        const inputType = this.classifyInput(value);

        // State machine for input processing
        if (this.currentExpectedInput === 'ja_id') {
            // Expecting a JA ID
            if (inputType === 'ja_id') {
                this.handleJaIdInput(value);
            } else {
                this.showAlert(`Expected JA ID but received ${inputType}. Please scan a JA ID (format: JA000123)`, 'warning');
                this.clearInput();
            }
        } else if (this.currentExpectedInput === 'location') {
            // Expecting a location
            if (inputType === 'location') {
                this.handleLocationInput(value);
            } else if (inputType === 'ja_id') {
                this.showAlert('Expected location but received JA ID. Please scan the location for this item.', 'warning');
                this.clearInput();
            } else {
                this.showAlert('Expected location but received sub-location. Please scan a valid location (M*, T*, or Other).', 'warning');
                this.clearInput();
            }
        } else if (this.currentExpectedInput === 'ja_id_or_sub_location') {
            // After scanning location, we can receive either:
            // - A JA ID (meaning no sub-location, start next move)
            // - A sub-location (meaning we have a sub-location for current move)
            // - A location would be an error
            if (inputType === 'ja_id') {
                // No sub-location for current move, finalize it and start new move
                this.finalizeCurrentMove(null);
                this.handleJaIdInput(value);
            } else if (inputType === 'sub_location') {
                // Sub-location for current move
                this.handleSubLocationInput(value);
            } else if (inputType === 'location') {
                this.showAlert('Received two locations in a row. Did you forget to scan a JA ID?', 'warning');
                this.clearInput();
            }
        }
    }
    
    isDoneCode(value) {
        const cleanValue = value.replace(/[<>]/g, '').toUpperCase();
        return cleanValue === 'DONE' || value === '>>DONE<<';
    }
    
    handleJaIdInput(jaId) {
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
        this.updateStatus(`JA ID ${jaId} scanned. Now scan or enter the location (M*, T*, or Other).`);
        this.updateScannerStatus('Waiting for Location');
    }

    handleLocationInput(location) {
        if (!location || location.length < 1) {
            this.showAlert('Location cannot be empty', 'warning');
            return;
        }

        // Store the location and wait for either JA ID or sub-location
        this.currentLocation = location;
        this.currentExpectedInput = 'ja_id_or_sub_location';
        this.clearInput();
        this.updateStatus(`Location ${location} scanned. Now scan the next JA ID or enter a sub-location (optional).`);
        this.updateScannerStatus('Waiting for JA ID or Sub-Location');
    }

    handleSubLocationInput(subLocation) {
        // Finalize current move with sub-location
        this.finalizeCurrentMove(subLocation);
        this.clearInput();
    }

    async finalizeCurrentMove(subLocation) {
        // Fetch current location and sub-location for the item
        let currentLocation = 'Unknown';
        let currentSubLocation = null;
        try {
            const response = await fetch(`/api/items/${this.currentJaId}`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.item) {
                    currentLocation = data.item.location || 'Unknown';
                    currentSubLocation = data.item.sub_location || null;
                }
            }
        } catch (error) {
            console.warn('Could not fetch current location for item:', error);
            // currentLocation remains 'Unknown'
        }

        // Add to move queue
        const moveItem = {
            jaId: this.currentJaId,
            newLocation: this.currentLocation,
            newSubLocation: subLocation || null,
            currentLocation: currentLocation,
            currentSubLocation: currentSubLocation,
            status: 'pending',
            timestamp: new Date().toISOString()
        };

        this.moveQueue.push(moveItem);

        // Build status message
        let statusMsg = `Added ${moveItem.jaId} → ${this.currentLocation}`;
        if (subLocation) {
            statusMsg += ` (${subLocation})`;
        }
        statusMsg += ' to queue. Ready to scan next JA ID.';

        // Reset for next item
        this.currentJaId = null;
        this.currentLocation = null;
        this.currentExpectedInput = 'ja_id';
        this.updateStatus(statusMsg);
        this.updateScannerStatus('Ready for JA ID');
        this.updateUI();

        console.log('Added to move queue:', moveItem);
    }
    
    handleDoneCode() {
        this.clearInput();

        // If we were in the middle of entering a move, finalize or clear it
        if (this.currentExpectedInput === 'location') {
            // We have a JA ID but no location - clear partial entry
            this.currentJaId = null;
            this.currentExpectedInput = 'ja_id';
            this.showAlert('Partial entry cleared (JA ID without location).', 'info');
        } else if (this.currentExpectedInput === 'ja_id_or_sub_location') {
            // We have JA ID and location but no sub-location - finalize without sub-location
            this.finalizeCurrentMove(null);
            this.showAlert('Finalized last entry without sub-location.', 'info');
        }

        if (this.moveQueue.length === 0) {
            this.showAlert('No items in move queue. Add some items before finishing.', 'warning');
            return;
        }

        this.updateStatus(`Scan completed. ${this.moveQueue.length} items queued for moving.`);
        this.updateScannerStatus('Done - Ready to Validate');
        this.validateBtn.disabled = false;
    }
    
    clearInput() {
        this.barcodeInput.value = '';
    }
    
    clearAll() {
        this.clearQueue();
        this.currentJaId = null;
        this.currentLocation = null;
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

            // Format sub-location display
            const currentSubLoc = item.currentSubLocation || '<span class="text-muted fst-italic">None</span>';
            let newSubLoc;
            if (item.newSubLocation) {
                newSubLoc = `<span class="fw-bold text-primary">${item.newSubLocation}</span>`;
            } else if (item.currentSubLocation) {
                // Clearing sub-location
                newSubLoc = '<span class="text-danger fst-italic">Cleared</span>';
            } else {
                // No sub-location before or after
                newSubLoc = '<span class="text-muted fst-italic">None</span>';
            }

            row.innerHTML = `
                <td>
                    <strong>${item.jaId}</strong>
                    ${item.itemInfo ? `<br><small class="text-muted">${item.itemInfo}</small>` : ''}
                </td>
                <td>
                    <span class="text-muted">${item.currentLocation || 'Unknown'}</span>
                </td>
                <td>
                    ${currentSubLoc}
                </td>
                <td>
                    <span class="fw-bold text-primary">${item.newLocation}</span>
                </td>
                <td>
                    ${newSubLoc}
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

        // Validate button enabled only when we have items and are ready for next JA ID
        // (not in the middle of entering a move)
        this.validateBtn.disabled = !hasItems || this.currentExpectedInput !== 'ja_id';

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
                        new_location: item.newLocation,
                        new_sub_location: item.newSubLocation || null
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