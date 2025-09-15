/**
 * Label Printing Modal Component
 * 
 * Provides a reusable modal for printing barcode labels from JA IDs.
 * Supports dynamic label type selection and localStorage persistence for Add Item form.
 */

class LabelPrintingModal {
    constructor(options = {}) {
        this.persistLabelType = options.persistLabelType || false;
        this.modalId = 'label-printing-modal';
        this.labelTypes = [];
        this.modal = null;
        this.initialized = false;
    }
    
    async init() {
        if (this.initialized) return;
        
        // Fetch available label types from API
        try {
            await this.loadLabelTypes();
            this.initialized = true;
            console.log('Label printing modal initialized with', this.labelTypes.length, 'label types');
        } catch (error) {
            console.error('Failed to load label types:', error);
        }
    }
    
    async loadLabelTypes() {
        const response = await fetch('/api/labels/types');
        if (!response.ok) {
            throw new Error('Failed to fetch label types');
        }
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch label types');
        }
        
        this.labelTypes = data.label_types;
    }
    
    createModalHTML() {
        const modalHTML = `
            <div class="modal fade" id="${this.modalId}" tabindex="-1" aria-labelledby="${this.modalId}-label" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="${this.modalId}-label">
                                <i class="bi bi-printer"></i> Print Label for <span id="label-ja-id-display"></span>
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <div id="label-print-alerts"></div>
                            
                            <form id="label-print-form">
                                <div class="mb-3">
                                    <label for="label-type-select" class="form-label">Label Type *</label>
                                    <select class="form-select" id="label-type-select" required>
                                        <option value="">Select label type...</option>
                                    </select>
                                    <div class="form-text">Choose the type and size of label to print</div>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                <i class="bi bi-x-circle"></i> Cancel
                            </button>
                            <button type="button" class="btn btn-primary" id="modal-print-label-btn">
                                <i class="bi bi-printer"></i> Print Label
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        return modalHTML;
    }
    
    ensureModalExists() {
        let modalElement = document.getElementById(this.modalId);
        if (!modalElement) {
            // Create and add modal to DOM
            document.body.insertAdjacentHTML('beforeend', this.createModalHTML());
            modalElement = document.getElementById(this.modalId);
            
            // Populate label types dropdown
            this.populateLabelTypes();
            
            // Set up event listeners
            this.setupEventListeners();
        }
        
        return modalElement;
    }
    
    populateLabelTypes() {
        const select = document.getElementById('label-type-select');
        if (!select) return;
        
        // Clear existing options (except the first placeholder)
        while (select.children.length > 1) {
            select.removeChild(select.lastChild);
        }
        
        // Add label type options
        this.labelTypes.forEach(labelType => {
            const option = document.createElement('option');
            option.value = labelType;
            option.textContent = labelType;
            select.appendChild(option);
        });
    }
    
    setupEventListeners() {
        const printButton = document.getElementById('modal-print-label-btn');
        if (!printButton) return;
        
        printButton.addEventListener('click', () => {
            this.handlePrintLabel();
        });
        
        // Handle Enter key in form
        const form = document.getElementById('label-print-form');
        if (form) {
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                this.handlePrintLabel();
            });
        }
        
        // Handle modal close to save label type selection
        const modalElement = document.getElementById(this.modalId);
        if (modalElement && this.persistLabelType) {
            modalElement.addEventListener('hidden.bs.modal', () => {
                this.saveLabelTypeSelection();
            });
        }
    }
    
    async handlePrintLabel() {
        console.log('handlePrintLabel called');
        const jaId = this.currentJaId;
        const labelType = document.getElementById('label-type-select').value;
        
        console.log('Printing label for JA ID:', jaId, 'Type:', labelType);
        
        if (!jaId) {
            console.log('Error: No JA ID specified');
            this.showError('No JA ID specified');
            return;
        }
        
        if (!labelType) {
            console.log('Error: No label type selected');
            this.showError('Please select a label type');
            return;
        }
        
        // Disable print button and show loading state
        const printButton = document.getElementById('modal-print-label-btn');
        const originalHTML = printButton.innerHTML;
        printButton.disabled = true;
        printButton.innerHTML = '<i class="bi bi-hourglass-split"></i> Printing...';
        
        try {
            const response = await fetch('/api/labels/print', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    ja_id: jaId,
                    label_type: labelType
                })
            });
            
            const data = await response.json();
            
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Failed to print label');
            }
            
            this.showSuccess(`Label printed successfully for ${jaId}`);
            
            // Save label type selection if persistence is enabled
            if (this.persistLabelType) {
                this.saveLabelTypeSelection();
            }
            
            // Close modal after successful print
            setTimeout(() => {
                this.hide();
            }, 2000);
            
        } catch (error) {
            console.error('Error printing label:', error);
            this.showError(`Failed to print label: ${error.message}`);
        } finally {
            // Restore print button
            printButton.disabled = false;
            printButton.innerHTML = originalHTML;
        }
    }
    
    async show(jaId) {
        if (!jaId) {
            console.error('JA ID is required to show label printing modal');
            return;
        }
        
        this.currentJaId = jaId;
        
        // Ensure initialization is complete
        await this.init();
        
        // Ensure modal exists
        const modalElement = this.ensureModalExists();
        
        // Update modal title with JA ID
        const jaIdDisplay = document.getElementById('label-ja-id-display');
        if (jaIdDisplay) {
            jaIdDisplay.textContent = jaId;
        }
        
        // Clear any previous alerts
        this.clearAlerts();
        
        // Restore saved label type if persistence is enabled
        if (this.persistLabelType) {
            this.restoreLabelTypeSelection();
        }
        
        // Create and show Bootstrap modal
        if (!this.modal) {
            this.modal = new bootstrap.Modal(modalElement);
        }
        this.modal.show();
    }
    
    hide() {
        if (this.modal) {
            this.modal.hide();
        }
    }
    
    showError(message) {
        const alertsContainer = document.getElementById('label-print-alerts');
        if (!alertsContainer) return;
        
        alertsContainer.innerHTML = `
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <i class="bi bi-exclamation-triangle"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
    }
    
    showSuccess(message) {
        const alertsContainer = document.getElementById('label-print-alerts');
        if (!alertsContainer) return;
        
        alertsContainer.innerHTML = `
            <div class="alert alert-success alert-dismissible fade show" role="alert">
                <i class="bi bi-check-circle"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
    }
    
    clearAlerts() {
        const alertsContainer = document.getElementById('label-print-alerts');
        if (alertsContainer) {
            alertsContainer.innerHTML = '';
        }
    }
    
    saveLabelTypeSelection() {
        if (!this.persistLabelType) return;
        
        const labelType = document.getElementById('label-type-select').value;
        if (labelType) {
            localStorage.setItem('labelPrintingModal.selectedLabelType', labelType);
        }
    }
    
    restoreLabelTypeSelection() {
        if (!this.persistLabelType) return;
        
        const savedLabelType = localStorage.getItem('labelPrintingModal.selectedLabelType');
        if (savedLabelType) {
            const select = document.getElementById('label-type-select');
            if (select) {
                select.value = savedLabelType;
            }
        }
    }
}

// Global function to create and show label printing modal
window.showLabelPrintingModal = async function(jaId, persistLabelType = false) {
    if (!window.labelPrintingModalInstance) {
        window.labelPrintingModalInstance = new LabelPrintingModal({
            persistLabelType: persistLabelType
        });
    }
    
    // Update persistence setting if different
    window.labelPrintingModalInstance.persistLabelType = persistLabelType;
    
    await window.labelPrintingModalInstance.show(jaId);
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LabelPrintingModal;
}