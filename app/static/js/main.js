/**
 * Workshop Inventory Tracking - Main JavaScript
 */

// Application namespace
const WorkshopInventory = {
    
    // Configuration
    config: {
        connectionCheckInterval: 30000, // 30 seconds
        apiEndpoints: {
            connectionTest: '/api/connection-test'
        }
    },
    
    // Initialize application
    init: function() {
        console.log('Initializing Workshop Inventory application...');
        
        // Check initial connection status
        this.checkConnectionStatus();
        
        // Set up periodic connection checks
        setInterval(() => {
            this.checkConnectionStatus();
        }, this.config.connectionCheckInterval);
        
        // Set up event listeners
        this.setupEventListeners();
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
        
        // Form validation helpers
        this.setupFormValidation();
        
        // Auto-dismiss alerts
        this.setupAlertDismissal();
    },
    
    // Check Google Sheets connection status
    checkConnectionStatus: function(showLoading = false) {
        const statusElement = document.getElementById('connection-status');
        if (!statusElement) return;
        
        const icon = statusElement.querySelector('i');
        const text = statusElement.querySelector('.connection-text') || 
                    document.createElement('span');
        
        if (showLoading) {
            icon.className = 'bi bi-arrow-clockwise text-checking';
            icon.style.animation = 'spin 1s linear infinite';
        }
        
        fetch(this.config.apiEndpoints.connectionTest)
            .then(response => response.json())
            .then(data => {
                icon.style.animation = '';
                
                if (data.success) {
                    icon.className = 'bi bi-check-circle text-connected';
                    statusElement.title = `Connected to: ${data.data?.title || 'Google Sheets'}`;
                } else {
                    icon.className = 'bi bi-x-circle text-disconnected';
                    statusElement.title = `Connection failed: ${data.error}`;
                }
            })
            .catch(error => {
                console.error('Connection check failed:', error);
                icon.style.animation = '';
                icon.className = 'bi bi-exclamation-triangle text-disconnected';
                statusElement.title = 'Connection check failed';
            });
    },
    
    // Set up form validation
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
                <span class="spinner-border spinner-border-sm me-2" role="status"></span>
                ${text}
            `;
            return originalHTML;
        },
        
        // Hide loading state
        hideLoading: function(element, originalHTML) {
            element.classList.remove('loading');
            element.innerHTML = originalHTML;
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