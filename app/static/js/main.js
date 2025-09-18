/**
 * Workshop Inventory Tracking - Main JavaScript
 */

// Application namespace
const WorkshopInventory = {
    
    // Configuration
    config: {
        // Application configuration
    },
    
    // Initialize application
    init: function() {
        console.log('Initializing Workshop Inventory application...');
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Set up keyboard shortcuts
        this.setupKeyboardShortcuts();
    },
    
    // Set up event listeners
    setupEventListeners: function() {
        // Connection status click handler
        const connectionStatus = document.getElementById('connection-status');
        if (connectionStatus) {
            connectionStatus.addEventListener('click', (e) => {
                e.preventDefault();
                this.checkConnectionStatus(true); // Force check
            });
        }
        
        // Keyboard help button handler
        const keyboardHelpBtn = document.getElementById('keyboard-help-btn');
        if (keyboardHelpBtn) {
            keyboardHelpBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.showKeyboardHelp();
            });
        }
        
        // JA ID quick lookup handler
        this.setupJaIdLookup();
        
        // Form validation helpers
        this.setupFormValidation();
        
        // Auto-dismiss alerts
        this.setupAlertDismissal();
    },
    
    // Show keyboard shortcuts help modal
    showKeyboardHelp: function() {
        // Remove existing modal if present
        const existingModal = document.getElementById('keyboard-help-modal');
        if (existingModal) {
            existingModal.remove();
        }
        
        // Create modal HTML
        const modalHTML = `
            <div class="modal fade" id="keyboard-help-modal" tabindex="-1" aria-labelledby="keyboard-help-title" aria-hidden="true">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="keyboard-help-title">
                                <i class="bi bi-keyboard"></i> Keyboard Shortcuts
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            ${Object.entries(this.keyboardShortcuts || {}).map(([category, shortcuts]) => `
                                <div class="mb-4">
                                    <h6 class="text-primary fw-bold mb-3">${category}</h6>
                                    <div class="row">
                                        ${Object.entries(shortcuts).map(([keys, description]) => `
                                            <div class="col-md-6 mb-2">
                                                <div class="d-flex justify-content-between align-items-center">
                                                    <span class="text-muted">${description}</span>
                                                    <kbd class="ms-2">${keys}</kbd>
                                                </div>
                                            </div>
                                        `).join('')}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                        <div class="modal-footer">
                            <div class="text-muted small">
                                <i class="bi bi-info-circle"></i> 
                                Press <kbd>Shift</kbd> + <kbd>/</kbd> or <kbd>F1</kbd> to show this help anytime
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Add modal to page
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('keyboard-help-modal'));
        modal.show();
        
        // Remove modal from DOM when hidden
        document.getElementById('keyboard-help-modal').addEventListener('hidden.bs.modal', function() {
            this.remove();
        });
    },
    
    // Set up keyboard shortcuts
    setupKeyboardShortcuts: function() {
        // Track if user is in an input field
        let inInputField = false;
        
        // Track input field focus
        document.addEventListener('focusin', (e) => {
            if (e.target.matches('input, textarea, select, [contenteditable]')) {
                inInputField = true;
            }
        });
        
        document.addEventListener('focusout', (e) => {
            if (e.target.matches('input, textarea, select, [contenteditable]')) {
                inInputField = false;
            }
        });
        
        // Global keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Skip shortcuts if user is typing in an input field
            if (inInputField && !e.ctrlKey && !e.metaKey && !e.altKey) {
                return;
            }
            
            const shortcuts = {
                // Utility shortcuts
                'Focus Search': {
                    keys: ['Slash'],
                    action: (e) => {
                        if (!inInputField) {
                            e.preventDefault();
                            const searchInput = document.querySelector('input[type="search"], input[name*="search"], #search');
                            if (searchInput) {
                                searchInput.focus();
                            }
                        }
                    },
                    description: 'Focus search input'
                },
                
                'Help': {
                    keys: ['F1', 'Slash'],
                    shift: true,
                    action: (e) => {
                        if (e.code === 'F1' || (e.code === 'Slash' && e.shiftKey)) {
                            e.preventDefault();
                            this.showKeyboardHelp();
                        }
                    },
                    description: 'Show keyboard shortcuts help'
                }
            };
            
            // Check for matching shortcut
            Object.entries(shortcuts).forEach(([name, shortcut]) => {
                const matchesKey = shortcut.keys.includes(e.code);
                const matchesCtrl = !shortcut.ctrl || e.ctrlKey || e.metaKey;
                const matchesAlt = !shortcut.alt || e.altKey;
                const matchesShift = !shortcut.shift || e.shiftKey;
                
                if (matchesKey && matchesCtrl && matchesAlt && matchesShift) {
                    // Ensure we don't conflict with browser shortcuts unless we explicitly prevent default
                    if (shortcut.ctrl || shortcut.alt || e.code === 'F1') {
                        e.preventDefault();
                    }
                    
                    try {
                        shortcut.action(e);
                        // Show brief feedback for the shortcut
                        this.utils.showToast(`${name}`, 'info');
                    } catch (error) {
                        console.warn('Keyboard shortcut error:', error);
                    }
                }
            });
        });
        
        // Store shortcuts for help display
        this.keyboardShortcuts = {
            'Utilities': {
                '/': 'Focus search input',
                'Shift + /': 'Show this help',
                'F1': 'Show this help',
            }
        };
    },
    
    
    // Set up form validation
    // Set up JA ID quick lookup functionality
    setupJaIdLookup: function() {
        const jaIdInput = document.getElementById('ja-id-lookup');
        if (!jaIdInput) return;
        
        jaIdInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const jaId = jaIdInput.value.trim().toUpperCase();
                
                // Validate JA ID format (JA######)
                if (!jaId.match(/^JA[0-9]{6}$/)) {
                    // Show visual feedback for invalid format
                    jaIdInput.classList.add('is-invalid');
                    jaIdInput.title = 'Invalid format. Use JA######';
                    
                    // Clear invalid state after 2 seconds
                    setTimeout(() => {
                        jaIdInput.classList.remove('is-invalid');
                        jaIdInput.title = 'Enter JA ID and press Enter to edit item';
                    }, 2000);
                    return;
                }
                
                // Clear the input and navigate
                jaIdInput.value = '';
                jaIdInput.classList.remove('is-invalid');
                
                // Navigate to edit page
                const editUrl = `/inventory/edit/${jaId}`;
                console.log(`Navigating to edit page for ${jaId}: ${editUrl}`);
                window.location.href = editUrl;
            }
        });
        
        // Handle input formatting - auto uppercase
        jaIdInput.addEventListener('input', (e) => {
            let value = e.target.value.toUpperCase();
            
            // Remove invalid state when user types
            if (e.target.classList.contains('is-invalid')) {
                e.target.classList.remove('is-invalid');
                e.target.title = 'Enter JA ID and press Enter to edit item';
            }
            
            e.target.value = value;
        });
    },
    
    setupFormValidation: function() {
        // Add Bootstrap validation classes
        const forms = document.querySelectorAll('.needs-validation');
        
        forms.forEach(form => {
            form.addEventListener('submit', (event) => {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                form.classList.add('was-validated');
            });
        });
        
        // Real-time validation for specific inputs
        const requiredInputs = document.querySelectorAll('input[required], select[required]');
        requiredInputs.forEach(input => {
            input.addEventListener('blur', () => {
                if (input.value.trim() === '') {
                    input.classList.add('is-invalid');
                    input.classList.remove('is-valid');
                } else if (!input.checkValidity()) {
                    input.classList.add('is-invalid');
                    input.classList.remove('is-valid');
                } else {
                    input.classList.remove('is-invalid');
                    input.classList.add('is-valid');
                }
            });
        });
    },
    
    // Set up alert auto-dismissal
    setupAlertDismissal: function() {
        // Auto-dismiss success alerts after 5 seconds
        const successAlerts = document.querySelectorAll('.alert-success');
        successAlerts.forEach(alert => {
            setTimeout(() => {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }, 5000);
        });
    },
    
    // Utility functions
    utils: {
        // Show loading state on element
        showLoading: function(element, text = 'Loading...') {
            element.classList.add('loading');
            const originalHTML = element.innerHTML;
            element.innerHTML = `
                <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                <span class="sr-only">Loading...</span>
                ${text}
            `;
            return originalHTML;
        },
        
        // Hide loading state
        hideLoading: function(element, originalHTML) {
            element.classList.remove('loading');
            element.innerHTML = originalHTML;
        },
        
        // Show full screen loading overlay
        showLoadingOverlay: function(message = 'Processing...') {
            const overlay = document.createElement('div');
            overlay.id = 'loading-overlay';
            overlay.className = 'loading-overlay';
            overlay.innerHTML = `
                <div class="loading-spinner">
                    <div class="spinner-border text-primary" role="status" aria-hidden="true"></div>
                    <div class="mt-3 fw-medium">${message}</div>
                </div>
            `;
            document.body.appendChild(overlay);
            return overlay;
        },
        
        // Hide full screen loading overlay
        hideLoadingOverlay: function() {
            const overlay = document.getElementById('loading-overlay');
            if (overlay) {
                overlay.remove();
            }
        },
        
        // Progress indicator for multi-step forms
        createProgressSteps: function(steps, currentStep = 0) {
            const container = document.createElement('div');
            container.className = 'progress-steps';
            
            steps.forEach((step, index) => {
                const stepElement = document.createElement('div');
                stepElement.className = 'progress-step';
                stepElement.title = step;
                
                if (index < currentStep) {
                    stepElement.classList.add('completed');
                    stepElement.innerHTML = '<i class="bi bi-check"></i>';
                } else if (index === currentStep) {
                    stepElement.classList.add('active');
                    stepElement.textContent = index + 1;
                } else {
                    stepElement.textContent = index + 1;
                }
                
                container.appendChild(stepElement);
            });
            
            return container;
        },
        
        // Update progress steps
        updateProgressSteps: function(container, currentStep) {
            const steps = container.querySelectorAll('.progress-step');
            steps.forEach((step, index) => {
                step.classList.remove('active', 'completed');
                
                if (index < currentStep) {
                    step.classList.add('completed');
                    step.innerHTML = '<i class="bi bi-check"></i>';
                } else if (index === currentStep) {
                    step.classList.add('active');
                    step.textContent = index + 1;
                } else {
                    step.textContent = index + 1;
                }
            });
        },
        
        // Show toast notification
        showToast: function(message, type = 'info') {
            // Create toast if doesn't exist
            let toastContainer = document.getElementById('toast-container');
            if (!toastContainer) {
                toastContainer = document.createElement('div');
                toastContainer.id = 'toast-container';
                toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
                document.body.appendChild(toastContainer);
            }
            
            const toastHTML = `
                <div class="toast align-items-center text-bg-${type}" role="alert">
                    <div class="d-flex">
                        <div class="toast-body">${message}</div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                    </div>
                </div>
            `;
            
            toastContainer.insertAdjacentHTML('beforeend', toastHTML);
            const toastElement = toastContainer.lastElementChild;
            const toast = new bootstrap.Toast(toastElement);
            toast.show();
            
            // Remove toast element after it's hidden
            toastElement.addEventListener('hidden.bs.toast', () => {
                toastElement.remove();
            });
        },
        
        // Format numbers with commas
        formatNumber: function(num) {
            return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        },
        
        // Debounce function for search inputs
        debounce: function(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },
        
        // Enhanced form validation
        validateForm: function(form, customValidators = {}) {
            let isValid = true;
            let firstInvalidField = null;
            
            // Clear previous validation states
            form.querySelectorAll('.is-valid, .is-invalid').forEach(field => {
                field.classList.remove('is-valid', 'is-invalid');
            });
            
            // Validate required fields
            const requiredFields = form.querySelectorAll('[required]');
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    field.classList.add('is-invalid');
                    this.showFieldError(field, 'This field is required.');
                    isValid = false;
                    if (!firstInvalidField) firstInvalidField = field;
                } else if (!field.checkValidity()) {
                    // Field has value but doesn't pass HTML5 validation (pattern, type, etc.)
                    field.classList.add('is-invalid');
                    this.showFieldError(field, field.validationMessage || 'Invalid value.');
                    isValid = false;
                    if (!firstInvalidField) firstInvalidField = field;
                } else {
                    field.classList.add('is-valid');
                    this.clearFieldError(field);
                }
            });
            
            // Run custom validators
            Object.keys(customValidators).forEach(fieldId => {
                const field = form.querySelector(`#${fieldId}`);
                const validator = customValidators[fieldId];
                
                if (field && field.value.trim()) {
                    const result = validator(field.value);
                    if (result !== true) {
                        field.classList.remove('is-valid');
                        field.classList.add('is-invalid');
                        this.showFieldError(field, result);
                        isValid = false;
                        if (!firstInvalidField) firstInvalidField = field;
                    }
                }
            });
            
            // Focus first invalid field
            if (firstInvalidField) {
                firstInvalidField.focus();
            }
            
            return isValid;
        },
        
        // Show field error message
        showFieldError: function(field, message) {
            this.clearFieldError(field);
            
            const feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            feedback.textContent = message;
            feedback.setAttribute('data-error-for', field.id || field.name);
            
            field.parentNode.appendChild(feedback);
        },
        
        // Clear field error message
        clearFieldError: function(field) {
            const existingFeedback = field.parentNode.querySelector(`[data-error-for="${field.id || field.name}"]`);
            if (existingFeedback) {
                existingFeedback.remove();
            }
        },
        
        // Show contextual help
        showHelp: function(fieldId, helpText, placement = 'top') {
            const field = document.getElementById(fieldId);
            if (!field) return;
            
            // Create or update tooltip
            if (field.hasAttribute('data-bs-original-title')) {
                field.setAttribute('data-bs-original-title', helpText);
            } else {
                field.setAttribute('data-bs-toggle', 'tooltip');
                field.setAttribute('data-bs-placement', placement);
                field.setAttribute('title', helpText);
                
                // Initialize tooltip
                const tooltip = new bootstrap.Tooltip(field);
            }
        },
        
        // Auto-save form data to localStorage
        autoSave: function(form, key) {
            const saveData = () => {
                const formData = new FormData(form);
                const data = {};
                formData.forEach((value, key) => {
                    data[key] = value;
                });
                localStorage.setItem(`autosave_${key}`, JSON.stringify(data));
            };
            
            // Save on form change
            form.addEventListener('input', this.debounce(saveData, 1000));
            form.addEventListener('change', saveData);
            
            // Load saved data on page load
            const savedData = localStorage.getItem(`autosave_${key}`);
            if (savedData) {
                try {
                    const data = JSON.parse(savedData);
                    Object.keys(data).forEach(fieldName => {
                        const field = form.querySelector(`[name="${fieldName}"]`);
                        if (field && data[fieldName]) {
                            field.value = data[fieldName];
                            // Trigger change event to update any dependent fields
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });
                } catch (e) {
                    console.warn('Failed to restore auto-saved form data:', e);
                }
            }
        },
        
        // Clear auto-saved data
        clearAutoSave: function(key) {
            localStorage.removeItem(`autosave_${key}`);
        },
        
        // Recent items management
        addToRecentItems: function(item) {
            const maxRecentItems = 10;
            let recentItems = JSON.parse(localStorage.getItem('recentItems') || '[]');
            
            // Remove if already exists
            recentItems = recentItems.filter(recent => recent.ja_id !== item.ja_id);
            
            // Add to beginning
            recentItems.unshift({
                ja_id: item.ja_id,
                type: item.type,
                shape: item.shape,
                material: item.material,
                length: item.length,
                width: item.width,
                timestamp: Date.now()
            });
            
            // Keep only maxRecentItems
            recentItems = recentItems.slice(0, maxRecentItems);
            
            localStorage.setItem('recentItems', JSON.stringify(recentItems));
        },
        
        // Get recent items
        getRecentItems: function() {
            const recentItems = JSON.parse(localStorage.getItem('recentItems') || '[]');
            
            // Filter out items older than 7 days
            const sevenDaysAgo = Date.now() - (7 * 24 * 60 * 60 * 1000);
            return recentItems.filter(item => item.timestamp > sevenDaysAgo);
        },
        
        // Create recent items dropdown
        createRecentItemsDropdown: function(targetElement) {
            const recentItems = this.getRecentItems();
            
            if (recentItems.length === 0) {
                return;
            }
            
            const dropdown = document.createElement('div');
            dropdown.className = 'dropdown';
            
            const button = document.createElement('button');
            button.className = 'btn btn-outline-secondary btn-sm dropdown-toggle';
            button.type = 'button';
            button.setAttribute('data-bs-toggle', 'dropdown');
            button.innerHTML = '<i class="bi bi-clock-history"></i> Recent Items';
            
            const menu = document.createElement('ul');
            menu.className = 'dropdown-menu';
            
            recentItems.forEach(item => {
                const listItem = document.createElement('li');
                const link = document.createElement('a');
                link.className = 'dropdown-item';
                link.href = '#';
                link.innerHTML = `
                    <div class="fw-semibold">${item.ja_id}</div>
                    <small class="text-muted">${item.type} ${item.shape} - ${item.material}</small>
                `;
                
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.fillFormFromRecentItem(item);
                });
                
                listItem.appendChild(link);
                menu.appendChild(listItem);
            });
            
            dropdown.appendChild(button);
            dropdown.appendChild(menu);
            targetElement.appendChild(dropdown);
        },
        
        // Fill form from recent item
        fillFormFromRecentItem: function(item) {
            Object.keys(item).forEach(key => {
                if (key !== 'ja_id' && key !== 'timestamp') {
                    const field = document.querySelector(`[name="${key}"], #${key}`);
                    if (field && item[key]) {
                        field.value = item[key];
                        // Trigger change event for dependent fields
                        field.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            });
        },
        
        // Auto-complete from similar items
        setupAutoComplete: function(inputField, dataSource) {
            let timeoutId;
            
            inputField.addEventListener('input', (e) => {
                clearTimeout(timeoutId);
                const value = e.target.value.trim();
                
                if (value.length < 2) {
                    this.hideAutoComplete();
                    return;
                }
                
                timeoutId = setTimeout(() => {
                    this.showAutoComplete(inputField, value, dataSource);
                }, 300);
            });
            
            // Hide on blur (with delay to allow click)
            inputField.addEventListener('blur', () => {
                setTimeout(() => this.hideAutoComplete(), 150);
            });
        },
        
        // Show auto-complete suggestions
        showAutoComplete: function(inputField, value, dataSource) {
            this.hideAutoComplete();
            
            // Get suggestions
            const suggestions = this.getAutoCompleteSuggestions(value, dataSource);
            
            if (suggestions.length === 0) {
                return;
            }
            
            // Create dropdown
            const dropdown = document.createElement('div');
            dropdown.id = 'autocomplete-dropdown';
            dropdown.className = 'autocomplete-dropdown position-absolute bg-white border rounded shadow-sm';
            dropdown.style.cssText = `
                z-index: 1050;
                max-height: 200px;
                overflow-y: auto;
                min-width: ${inputField.offsetWidth}px;
            `;
            
            suggestions.forEach(suggestion => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item px-3 py-2 cursor-pointer';
                item.textContent = suggestion;
                item.style.cursor = 'pointer';
                
                item.addEventListener('mouseenter', () => {
                    item.style.backgroundColor = '#f8f9fa';
                });
                
                item.addEventListener('mouseleave', () => {
                    item.style.backgroundColor = '';
                });
                
                item.addEventListener('click', () => {
                    inputField.value = suggestion;
                    inputField.dispatchEvent(new Event('input', { bubbles: true }));
                    inputField.dispatchEvent(new Event('change', { bubbles: true }));
                    this.hideAutoComplete();
                });
                
                dropdown.appendChild(item);
            });
            
            // Position dropdown
            const rect = inputField.getBoundingClientRect();
            dropdown.style.left = rect.left + 'px';
            dropdown.style.top = (rect.bottom + window.scrollY) + 'px';
            
            document.body.appendChild(dropdown);
        },
        
        // Hide auto-complete dropdown
        hideAutoComplete: function() {
            const dropdown = document.getElementById('autocomplete-dropdown');
            if (dropdown) {
                dropdown.remove();
            }
        },
        
        // Get auto-complete suggestions
        getAutoCompleteSuggestions: function(value, dataSource) {
            if (typeof dataSource === 'function') {
                return dataSource(value);
            }
            
            if (Array.isArray(dataSource)) {
                const lowerValue = value.toLowerCase();
                return dataSource
                    .filter(item => item.toLowerCase().includes(lowerValue))
                    .slice(0, 10)
                    .sort((a, b) => {
                        const aIndex = a.toLowerCase().indexOf(lowerValue);
                        const bIndex = b.toLowerCase().indexOf(lowerValue);
                        return aIndex - bIndex;
                    });
            }
            
            return [];
        }
    }
};

// CSS animation for spinning icon
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    WorkshopInventory.init();
});

// Make utils available globally
window.WorkshopInventory = WorkshopInventory;