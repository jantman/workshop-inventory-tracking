/**
 * Inventory Shorten JavaScript - Item Shortening Interface
 * 
 * Handles item selection, length validation, and shortening workflow
 * for shortening items while preserving the same JA ID and maintaining history.
 */

class InventoryShortenManager {
    constructor() {
        this.currentItem = null;
        this.originalLength = null;
        this.scannerTimeout = null;
        this.scannerDelay = 100; // ms delay to detect scanner input
        
        this.initializeElements();
        this.bindEvents();
        this.setDefaultDate();
        
        console.log('InventoryShortenManager initialized');
    }
    
    initializeElements() {
        // Input elements
        this.sourceJaIdInput = document.getElementById('source-ja-id');
        this.newLengthInput = document.getElementById('new-length');
        this.cutDateInput = document.getElementById('cut-date');
        this.shorteningNotesTextarea = document.getElementById('shortening-notes');
        this.confirmOperationCheckbox = document.getElementById('confirm-operation');
        
        // Button elements
        this.scanJaIdBtn = document.getElementById('scan-ja-id-btn');
        this.loadItemBtn = document.getElementById('load-item-btn');
        this.clearFormBtn = document.getElementById('clear-form-btn');
        this.executeShorteningBtn = document.getElementById('execute-shortening-btn');
        
        // Display elements
        this.scannerStatus = document.getElementById('scanner-status');
        this.itemDetails = document.getElementById('item-details');
        this.itemNotFound = document.getElementById('item-not-found');
        this.shorteningSection = document.getElementById('shortening-section');
        this.notesSection = document.getElementById('notes-section');
        this.summarySection = document.getElementById('summary-section');
        this.historySection = document.getElementById('history-section');
        this.lengthValidation = document.getElementById('length-validation');
        this.lengthValidationAlert = document.getElementById('length-validation-alert');
        
        // Item detail display elements
        this.itemDisplayName = document.getElementById('item-display-name');
        this.itemMaterial = document.getElementById('item-material');
        this.itemType = document.getElementById('item-type');
        this.itemShape = document.getElementById('item-shape');
        this.currentLengthSpan = document.getElementById('current-length');
        this.itemLocation = document.getElementById('item-location');
        this.itemStatus = document.getElementById('item-status');

        // Summary display elements
        this.summaryJaId = document.getElementById('summary-ja-id');
        this.summaryCurrentLength = document.getElementById('summary-current-length');
        this.summaryNewLength = document.getElementById('summary-new-length');
        this.summaryRemovedLength = document.getElementById('summary-removed-length');
        
        // Alert elements
        this.formAlerts = document.getElementById('form-alerts');
    }
    
    bindEvents() {
        // JA ID input handling
        this.sourceJaIdInput.addEventListener('input', (e) => this.handleJaIdInput(e));
        this.sourceJaIdInput.addEventListener('keydown', (e) => this.handleJaIdKeyDown(e));
        
        // Button events
        this.scanJaIdBtn.addEventListener('click', () => this.focusJaIdInput());
        this.loadItemBtn.addEventListener('click', () => this.loadItem());
        this.clearFormBtn.addEventListener('click', () => this.clearForm());
        
        // Length validation
        this.newLengthInput.addEventListener('input', () => this.validateLength());
        
        // Form validation
        this.confirmOperationCheckbox.addEventListener('change', () => this.updateExecuteButton());
        
        // Focus on JA ID input when page loads
        this.sourceJaIdInput.focus();
    }
    
    setDefaultDate() {
        // Set cut date to today by default
        const today = new Date().toISOString().split('T')[0];
        this.cutDateInput.value = today;
    }
    
    focusJaIdInput() {
        this.sourceJaIdInput.focus();
        this.sourceJaIdInput.select();
    }
    
    handleJaIdKeyDown(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            this.loadItem();
        }
    }
    
    handleJaIdInput(e) {
        const value = e.target.value.trim();
        
        if (!value) return;
        
        // Clear any existing timeout
        if (this.scannerTimeout) {
            clearTimeout(this.scannerTimeout);
        }
        
        // Auto-load after scanner delay (for barcode scanners)
        this.scannerTimeout = setTimeout(() => {
            if (this.isValidJaId(value)) {
                this.loadItem();
            }
        }, this.scannerDelay);
    }
    
    isValidJaId(jaId) {
        const jaIdPattern = /^JA\d{6}$/;
        return jaIdPattern.test(jaId);
    }
    
    async loadItem() {
        const jaId = this.sourceJaIdInput.value.trim().toUpperCase();
        
        if (!jaId) {
            this.showAlert('Please enter a JA ID', 'warning');
            return;
        }
        
        if (!this.isValidJaId(jaId)) {
            this.showAlert(`Invalid JA ID format: ${jaId}. Expected format: JA000001`, 'danger');
            return;
        }
        
        this.loadItemBtn.disabled = true;
        this.loadItemBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Loading...';
        this.updateScannerStatus('Loading Item');
        
        try {
            const response = await fetch(`/api/items/${jaId}`);
            
            if (response.status === 404) {
                this.showItemNotFound();
                return;
            }
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.error || 'Failed to load item');
            }
            
            const item = data.item;
            
            // Validate item is suitable for shortening
            if (!this.validateItemForShortening(item)) {
                this.showItemNotFound();
                return;
            }
            
            this.currentItem = item;
            this.displayItemDetails(item);
            this.showShorteningSections();
            this.updateScannerStatus('Item Loaded');
            
        } catch (error) {
            console.error('Error loading item:', error);
            this.showAlert(`Failed to load item: ${error.message}`, 'danger');
            this.showItemNotFound();
        } finally {
            this.loadItemBtn.disabled = false;
            this.loadItemBtn.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Load';
        }
    }
    
    validateItemForShortening(item) {
        // Item must be active
        if (!item.active) {
            return false;
        }
        
        // Item must have dimensions with length
        if (!item.dimensions || !item.dimensions.length) {
            return false;
        }
        
        // Parse and store original length
        try {
            this.originalLength = parseFloat(item.dimensions.length);
            if (isNaN(this.originalLength) || this.originalLength <= 0) {
                return false;
            }
        } catch (e) {
            return false;
        }
        
        return true;
    }
    
    displayItemDetails(item) {
        this.itemDisplayName.textContent = item.display_name || item.ja_id;
        this.itemMaterial.textContent = item.material || 'Unknown';
        this.itemType.textContent = item.item_type || 'Unknown';
        this.itemShape.textContent = item.shape || 'Unknown';
        this.currentLengthSpan.textContent = item.dimensions.length || 'Unknown';
        this.itemLocation.textContent = item.location || 'Not specified';
        this.itemStatus.textContent = item.active ? 'Active' : 'Inactive';

        // Show item details
        this.itemDetails.classList.remove('d-none');
        this.itemNotFound.classList.add('d-none');
    }
    
    showItemNotFound() {
        this.itemDetails.classList.add('d-none');
        this.itemNotFound.classList.remove('d-none');
        this.hideShorteningSection();
        this.updateScannerStatus('Item Not Found', 'danger');
    }
    
    showShorteningSections() {
        this.shorteningSection.style.display = 'block';
        this.notesSection.style.display = 'block';
        this.summarySection.style.display = 'block';
        this.historySection.style.display = 'block';
        
        // Update summary with initial values
        this.updateSummary();
        
        // Focus on new length input
        setTimeout(() => this.newLengthInput.focus(), 100);
    }
    
    hideShorteningSection() {
        this.shorteningSection.style.display = 'none';
        this.notesSection.style.display = 'none';
        this.summarySection.style.display = 'none';
        this.historySection.style.display = 'none';
        this.lengthValidation.classList.add('d-none');
    }
    
    validateLength() {
        if (!this.currentItem || !this.originalLength) {
            return;
        }
        
        const newLengthStr = this.newLengthInput.value.trim();
        
        if (!newLengthStr) {
            this.lengthValidation.classList.add('d-none');
            this.updateSummary();
            return;
        }
        
        try {
            const newLength = this.parseDimensionValue(newLengthStr);
            
            if (newLength <= 0) {
                this.showLengthValidation('New length must be greater than 0', 'danger');
                return;
            }
            
            if (newLength >= this.originalLength) {
                this.showLengthValidation('New length must be shorter than the original length', 'danger');
                return;
            }
            
            const materialRemoved = this.originalLength - newLength;
            
            let validationMessage = `Length validation successful. `;
            validationMessage += `Material removed: ${materialRemoved.toFixed(3)}"`;
            
            this.showLengthValidation(validationMessage, 'success');
            this.updateSummary();
            
        } catch (error) {
            this.showLengthValidation(`Invalid length format: ${error.message}`, 'danger');
        }
    }
    
    parseDimensionValue(value) {
        value = value.trim();
        if (!value) return 0;
        
        // Handle mixed numbers like "1 1/2"
        if (value.includes(' ') && value.includes('/')) {
            const parts = value.split(' ', 2);
            const whole = parseFloat(parts[0]);
            const fracParts = parts[1].split('/');
            if (fracParts.length === 2) {
                const numerator = parseFloat(fracParts[0]);
                const denominator = parseFloat(fracParts[1]);
                if (denominator === 0) throw new Error('Division by zero in fraction');
                return whole + (numerator / denominator);
            }
        }
        
        // Handle simple fractions like "1/2"
        if (value.includes('/')) {
            const fracParts = value.split('/');
            if (fracParts.length === 2) {
                const numerator = parseFloat(fracParts[0]);
                const denominator = parseFloat(fracParts[1]);
                if (denominator === 0) throw new Error('Division by zero in fraction');
                return numerator / denominator;
            }
        }
        
        // Handle decimal numbers
        const decimal = parseFloat(value);
        if (isNaN(decimal)) throw new Error('Invalid number format');
        return decimal;
    }
    
    showLengthValidation(message, type) {
        this.lengthValidationAlert.textContent = message;
        this.lengthValidationAlert.className = `alert alert-${type}`;
        this.lengthValidation.classList.remove('d-none');
    }
    
    updateSummary() {
        if (!this.currentItem) return;
        
        this.summaryJaId.textContent = this.currentItem.ja_id;
        this.summaryCurrentLength.textContent = `${this.originalLength.toFixed(3)}"`;
        
        const newLengthStr = this.newLengthInput.value.trim();
        
        if (newLengthStr) {
            try {
                const newLength = this.parseDimensionValue(newLengthStr);
                const removedLength = this.originalLength - newLength;
                
                this.summaryNewLength.textContent = `${newLength.toFixed(3)}"`;
                this.summaryRemovedLength.textContent = `${removedLength.toFixed(3)}"`;
            } catch (e) {
                this.summaryNewLength.textContent = 'Invalid';
                this.summaryRemovedLength.textContent = 'Invalid';
            }
        } else {
            this.summaryNewLength.textContent = '-';
            this.summaryRemovedLength.textContent = '-';
        }
        
        this.updateExecuteButton();
    }
    
    
    updateExecuteButton() {
        const hasItem = !!this.currentItem;
        const hasValidLength = this.newLengthInput.value.trim() !== '';
        const isConfirmed = this.confirmOperationCheckbox.checked;
        
        const canExecute = hasItem && hasValidLength && isConfirmed;
        this.executeShorteningBtn.disabled = !canExecute;
    }
    
    clearForm() {
        // Clear all form inputs
        this.sourceJaIdInput.value = '';
        this.newLengthInput.value = '';
        this.shorteningNotesTextarea.value = '';
        this.confirmOperationCheckbox.checked = false;
        this.setDefaultDate();
        
        // Reset state
        this.currentItem = null;
        this.originalLength = null;
        
        // Hide sections
        this.hideShorteningSection();
        this.itemDetails.classList.add('d-none');
        this.itemNotFound.classList.add('d-none');
        
        // Reset UI
        this.updateScannerStatus('Ready');
        this.clearAlerts();
        this.sourceJaIdInput.focus();
    }
    
    updateScannerStatus(status = 'Ready', type = 'secondary') {
        this.scannerStatus.textContent = status;
        this.scannerStatus.className = `badge ms-2 bg-${type}`;
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
    window.shortenManager = new InventoryShortenManager();
    
    // Handle form submission
    document.getElementById('shorten-form').addEventListener('submit', function(e) {
        e.preventDefault();
        
        if (!window.shortenManager.currentItem) {
            window.shortenManager.showAlert('Please load an item first', 'warning');
            return;
        }
        
        if (!document.getElementById('confirm-operation').checked) {
            window.shortenManager.showAlert('Please confirm the shortening operation', 'warning');
            return;
        }
        
        // Form is valid, submit normally
        this.submit();
    });
});