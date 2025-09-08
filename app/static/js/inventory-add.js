/**
 * Inventory Add Form - JavaScript functionality
 * 
 * Handles form validation, barcode scanning, carry-forward functionality,
 * and dynamic field requirements based on type/shape selection.
 */

class InventoryAddForm {
    constructor() {
        this.form = document.getElementById('add-item-form');
        this.scanModeActive = false;
        this.scanBuffer = '';
        this.scanTimeout = null;
        this.lastItemData = null;
        
        // Field mappings for dynamic requirements
        this.typeShapeRequirements = {
            'Bar': {
                'Rectangular': ['length', 'width', 'thickness'],
                'Round': ['length', 'width'],
                'Square': ['length', 'width'],
                'Hexagonal': ['length', 'width']
            },
            'Plate': {
                'Rectangular': ['length', 'width', 'thickness'],
                'Square': ['length', 'width', 'thickness'],
                'Round': ['length', 'width', 'thickness']
            },
            'Sheet': {
                'Rectangular': ['length', 'width', 'thickness'],
                'Square': ['length', 'width', 'thickness']
            },
            'Tube': {
                'Round': ['length', 'width', 'wall_thickness'],
                'Square': ['length', 'width', 'wall_thickness'],
                'Rectangular': ['length', 'width', 'wall_thickness']
            },
            'Pipe': {
                'Round': ['length', 'width', 'wall_thickness']
            },
            'Rod': {
                'Round': ['length', 'width']
            },
            'Angle': {
                'L-Shaped': ['length', 'width', 'thickness']
            },
            'Channel': {
                'C-Channel': ['length', 'width', 'thickness'],
                'U-Shaped': ['length', 'width', 'thickness']
            },
            'Beam': {
                'I-Beam': ['length', 'width', 'thickness']
            },
            'Wire': {
                'Round': ['length', 'width']
            },
            'Fastener': {
                'Round': ['width'],
                'Hexagonal': ['width']
            }
        };
        
        // Material suggestions cache
        this.materialSuggestions = [];
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupBarcodeScanning();
        this.setupMaterialAutocomplete();
        this.updateDimensionRequirements();
        this.loadMaterialSuggestions();
    }
    
    setupEventListeners() {
        // Form submission
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
        
        // Submit and continue button
        document.getElementById('submit-and-continue-btn').addEventListener('click', () => {
            this.handleSubmit(null, true);
        });
        
        // Type and shape changes
        document.getElementById('item_type').addEventListener('change', () => {
            this.updateDimensionRequirements();
            this.updateShapeOptions();
        });
        
        document.getElementById('shape').addEventListener('change', () => {
            this.updateDimensionRequirements();
            this.updateWidthLabel();
        });
        
        // Barcode scan buttons
        document.getElementById('scan-ja-id-btn').addEventListener('click', () => {
            this.startBarcodeCapture('ja_id');
        });
        
        // Carry forward functionality
        document.getElementById('carry-forward-btn').addEventListener('click', () => {
            this.carryForwardData();
        });
        
        // Material suggestions button
        document.getElementById('material-suggestions-btn').addEventListener('click', () => {
            this.showMaterialSuggestions();
        });
        
        // Real-time validation
        this.setupRealTimeValidation();
    }
    
    setupBarcodeScanning() {
        // Listen for rapid keystrokes (barcode scanner input)
        document.addEventListener('keydown', (e) => {
            if (!this.scanModeActive) return;
            
            // Clear previous timeout
            if (this.scanTimeout) {
                clearTimeout(this.scanTimeout);
            }
            
            // Add character to buffer (ignore control keys)
            if (e.key.length === 1) {
                this.scanBuffer += e.key;
                e.preventDefault();
            } else if (e.key === 'Enter') {
                this.processBarcodeInput(this.scanBuffer);
                this.scanBuffer = '';
                this.scanModeActive = false;
                e.preventDefault();
                return;
            }
            
            // Set timeout to process buffer (barcode scanners are fast)
            this.scanTimeout = setTimeout(() => {
                if (this.scanBuffer.length > 0) {
                    this.processBarcodeInput(this.scanBuffer);
                    this.scanBuffer = '';
                }
                this.scanModeActive = false;
            }, 100);
        });
    }
    
    startBarcodeCapture(fieldId) {
        this.scanModeActive = true;
        this.scanTargetField = fieldId;
        this.scanBuffer = '';
        
        // Visual feedback
        const button = document.getElementById('scan-ja-id-btn');
        const icon = button.querySelector('i');
        icon.className = 'bi bi-stopwatch';
        button.classList.add('btn-warning');
        button.classList.remove('btn-outline-secondary');
        
        // Show notification
        WorkshopInventory.utils.showToast('Ready to scan barcode...', 'info');
        
        // Auto-cancel after 10 seconds
        setTimeout(() => {
            if (this.scanModeActive) {
                this.cancelBarcodeCapture();
            }
        }, 10000);
    }
    
    cancelBarcodeCapture() {
        this.scanModeActive = false;
        this.scanBuffer = '';
        
        // Reset button appearance
        const button = document.getElementById('scan-ja-id-btn');
        const icon = button.querySelector('i');
        icon.className = 'bi bi-upc-scan';
        button.classList.remove('btn-warning');
        button.classList.add('btn-outline-secondary');
    }
    
    processBarcodeInput(scannedData) {
        // Clean up the scanned data
        const cleanData = scannedData.trim().toUpperCase();
        
        // Validate JA ID format if that's what we're scanning
        if (this.scanTargetField === 'ja_id') {
            if (/^JA\d{6}$/.test(cleanData)) {
                document.getElementById('ja_id').value = cleanData;
                WorkshopInventory.utils.showToast(`Scanned JA ID: ${cleanData}`, 'success');
                
                // Check if this ID already exists
                this.checkJAIDExists(cleanData);
            } else {
                WorkshopInventory.utils.showToast(`Invalid JA ID format: ${cleanData}`, 'error');
            }
        }
        
        this.cancelBarcodeCapture();
    }
    
    updateDimensionRequirements() {
        const typeSelect = document.getElementById('item_type');
        const shapeSelect = document.getElementById('shape');
        
        const selectedType = typeSelect.value;
        const selectedShape = shapeSelect.value;
        
        // Reset all dimension requirements
        const dimensionFields = ['length', 'width', 'thickness', 'wall_thickness'];
        dimensionFields.forEach(field => {
            const input = document.getElementById(field);
            const indicator = input.closest('.mb-3').querySelector('.dimension-required');
            
            input.removeAttribute('required');
            indicator.style.display = 'none';
            input.classList.remove('is-invalid');
        });
        
        // Apply requirements based on type/shape combination
        if (selectedType && selectedShape && this.typeShapeRequirements[selectedType]) {
            const requirements = this.typeShapeRequirements[selectedType][selectedShape];
            
            if (requirements) {
                requirements.forEach(field => {
                    const input = document.getElementById(field);
                    const indicator = input.closest('.mb-3').querySelector('.dimension-required');
                    
                    input.setAttribute('required', 'required');
                    indicator.style.display = 'inline';
                });
            }
        }
    }
    
    updateShapeOptions() {
        const typeSelect = document.getElementById('item_type');
        const shapeSelect = document.getElementById('shape');
        const selectedType = typeSelect.value;
        
        // Get all shape options
        const allOptions = shapeSelect.querySelectorAll('option');
        
        // Show all options first
        allOptions.forEach(option => {
            if (option.value !== '') {
                option.style.display = 'block';
            }
        });
        
        // Filter based on type if we have restrictions
        if (selectedType && this.typeShapeRequirements[selectedType]) {
            const validShapes = Object.keys(this.typeShapeRequirements[selectedType]);
            
            allOptions.forEach(option => {
                if (option.value !== '' && !validShapes.includes(option.value)) {
                    option.style.display = 'none';
                    
                    // If currently selected shape is invalid, clear it
                    if (option.selected) {
                        shapeSelect.value = '';
                    }
                }
            });
        }
    }
    
    updateWidthLabel() {
        const shapeSelect = document.getElementById('shape');
        const widthLabel = document.getElementById('width-label');
        
        // Update label based on shape
        if (shapeSelect.value === 'Round') {
            widthLabel.textContent = 'Diameter';
        } else {
            widthLabel.textContent = 'Width';
        }
    }
    
    setupMaterialAutocomplete() {
        const materialInput = document.getElementById('material');
        const suggestionsDiv = document.getElementById('material-suggestions');
        
        materialInput.addEventListener('input', WorkshopInventory.utils.debounce((e) => {
            const query = e.target.value.trim();
            if (query.length >= 2) {
                this.showMaterialMatches(query);
            } else {
                suggestionsDiv.style.display = 'none';
            }
        }, 300));
        
        // Hide suggestions when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#material') && !e.target.closest('#material-suggestions')) {
                suggestionsDiv.style.display = 'none';
            }
        });
    }
    
    async loadMaterialSuggestions() {
        try {
            const response = await fetch('/api/materials/suggestions');
            if (response.ok) {
                this.materialSuggestions = await response.json();
            } else {
                // Fallback to basic material list if API doesn't exist
                this.materialSuggestions = [
                    'Steel', 'Aluminum', 'Stainless Steel', 'Brass', 'Copper', 
                    'Iron', 'Carbon Steel', 'Alloy Steel', 'Titanium', 'Bronze'
                ];
            }
        } catch (error) {
            console.warn('Failed to load material suggestions:', error);
            // Ensure materialSuggestions is always an array
            this.materialSuggestions = [
                'Steel', 'Aluminum', 'Stainless Steel', 'Brass', 'Copper', 
                'Iron', 'Carbon Steel', 'Alloy Steel', 'Titanium', 'Bronze'
            ];
        }
    }
    
    showMaterialMatches(query) {
        const suggestionsDiv = document.getElementById('material-suggestions');
        const matches = this.materialSuggestions
            .filter(material => material.toLowerCase().includes(query.toLowerCase()))
            .slice(0, 8);
        
        if (matches.length === 0) {
            suggestionsDiv.style.display = 'none';
            return;
        }
        
        const html = matches.map(material => 
            `<a class="dropdown-item" href="#" data-material="${material}">${material}</a>`
        ).join('');
        
        suggestionsDiv.innerHTML = html;
        suggestionsDiv.style.display = 'block';
        
        // Position the dropdown
        const materialInput = document.getElementById('material');
        const rect = materialInput.getBoundingClientRect();
        suggestionsDiv.style.top = `${rect.bottom}px`;
        suggestionsDiv.style.left = `${rect.left}px`;
        suggestionsDiv.style.width = `${rect.width}px`;
        
        // Add click handlers
        suggestionsDiv.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                materialInput.value = item.dataset.material;
                suggestionsDiv.style.display = 'none';
            });
        });
    }
    
    showMaterialSuggestions() {
        this.showMaterialMatches('');
    }
    
    setupRealTimeValidation() {
        // JA ID validation
        const jaIdInput = document.getElementById('ja_id');
        jaIdInput.addEventListener('blur', () => {
            const jaId = jaIdInput.value.trim();
            if (jaId && /^JA\d{6}$/.test(jaId)) {
                this.checkJAIDExists(jaId);
            }
        });
        
        // Dimension validation (positive numbers, fractions)
        const dimensionInputs = ['length', 'width', 'thickness', 'wall_thickness', 'weight'];
        dimensionInputs.forEach(fieldName => {
            const input = document.getElementById(fieldName);
            input.addEventListener('input', (e) => {
                this.validateDimensionInput(e.target);
            });
        });
    }
    
    validateDimensionInput(input) {
        const value = input.value.trim();
        if (!value) return;
        
        // Allow decimals, fractions, and mixed numbers
        const validPattern = /^(\d+(\.\d+)?|\d*\s*\/\s*\d+|\d+\s+\d+\s*\/\s*\d+)$/;
        
        if (!validPattern.test(value)) {
            input.classList.add('is-invalid');
            input.setCustomValidity('Enter a valid number or fraction (e.g., 1.5, 3/4, 1 1/2)');
        } else {
            input.classList.remove('is-invalid');
            input.setCustomValidity('');
        }
    }
    
    async checkJAIDExists(jaId) {
        try {
            const response = await fetch(`/api/items/${jaId}/exists`);
            if (response.ok) {
                const data = await response.json();
                if (data.exists) {
                    WorkshopInventory.utils.showToast(`Warning: JA ID ${jaId} already exists!`, 'warning');
                    document.getElementById('ja_id').classList.add('is-invalid');
                }
            }
        } catch (error) {
            console.warn('Failed to check JA ID:', error);
        }
    }
    
    carryForwardData() {
        if (!this.lastItemData) {
            WorkshopInventory.utils.showToast('No previous item data to carry forward', 'info');
            return;
        }
        
        // Fields to carry forward
        const carryFields = [
            'item_type', 'shape', 'material', 'quantity',
            'location', 'sub_location', 'vendor', 'purchase_location',
            'thread_series', 'thread_handedness'
        ];
        
        carryFields.forEach(field => {
            const input = document.getElementById(field);
            if (input && this.lastItemData[field]) {
                input.value = this.lastItemData[field];
            }
        });
        
        // Trigger updates
        this.updateDimensionRequirements();
        this.updateWidthLabel();
        
        WorkshopInventory.utils.showToast('Previous item data carried forward', 'success');
    }
    
    async handleSubmit(event, continueAdding = false) {
        if (event) {
            event.preventDefault();
        }
        
        // Validate form
        if (!this.form.checkValidity()) {
            event?.stopPropagation();
            this.form.classList.add('was-validated');
            this.showValidationErrors();
            return;
        }
        
        // Set submit type for continue functionality
        if (continueAdding) {
            const submitTypeInput = document.createElement('input');
            submitTypeInput.type = 'hidden';
            submitTypeInput.name = 'submit_type';
            submitTypeInput.value = 'continue';
            this.form.appendChild(submitTypeInput);
        }
        
        // Show loading state
        const submitBtn = document.getElementById('submit-btn');
        const continueBtn = document.getElementById('submit-and-continue-btn');
        const originalSubmitHTML = submitBtn.innerHTML;
        const originalContinueHTML = continueBtn.innerHTML;
        
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Adding...';
        continueBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Adding...';
        submitBtn.disabled = true;
        continueBtn.disabled = true;
        
        // Store form data for carry-forward before submitting
        this.lastItemData = this.collectFormData();
        
        // Submit form normally (not via API)
        this.form.submit();
    }
    
    collectFormData() {
        const formData = new FormData(this.form);
        const data = {};
        
        // Basic fields
        const basicFields = [
            'ja_id', 'item_type', 'shape', 'material', 'quantity',
            'location', 'sub_location', 'notes', 'vendor', 'vendor_part_number',
            'purchase_location'
        ];
        
        basicFields.forEach(field => {
            const value = formData.get(field);
            if (value && value.trim()) {
                data[field] = value.trim();
            }
        });
        
        // Dimensions
        const dimensionFields = ['length', 'width', 'thickness', 'wall_thickness', 'weight'];
        data.dimensions = {};
        dimensionFields.forEach(field => {
            const value = formData.get(field);
            if (value && value.trim()) {
                data.dimensions[field] = value.trim();
            }
        });
        
        // Thread info
        const threadSeries = formData.get('thread_series');
        const threadHandedness = formData.get('thread_handedness');
        const threadSize = formData.get('thread_size');
        
        if (threadSeries || threadHandedness || threadSize) {
            data.thread = {};
            if (threadSeries) data.thread.series = threadSeries;
            if (threadHandedness) data.thread.handedness = threadHandedness;
            if (threadSize) data.thread.size = threadSize.trim();
        }
        
        // Purchase info
        const purchaseDate = formData.get('purchase_date');
        const purchasePrice = formData.get('purchase_price');
        
        if (purchaseDate) data.purchase_date = purchaseDate;
        if (purchasePrice && purchasePrice.trim()) {
            data.purchase_price = purchasePrice.trim();
        }
        
        // Active status
        data.active = formData.has('active');
        
        return data;
    }
    
    clearFormForContinue() {
        // Clear specific fields but keep others for carry-forward
        const clearFields = [
            'ja_id', 'length', 'width', 'thickness', 'wall_thickness', 
            'weight', 'thread_size', 'notes', 'vendor_part_number',
            'purchase_date', 'purchase_price'
        ];
        
        clearFields.forEach(field => {
            const input = document.getElementById(field);
            if (input) {
                input.value = '';
            }
        });
        
        // Clear validation states
        this.form.classList.remove('was-validated');
        this.form.querySelectorAll('.is-invalid').forEach(el => {
            el.classList.remove('is-invalid');
        });
        
        // Focus on JA ID for next item
        document.getElementById('ja_id').focus();
    }
    
    showValidationErrors() {
        const invalidFields = this.form.querySelectorAll(':invalid');
        const errors = Array.from(invalidFields).map(field => {
            const label = field.closest('.mb-3')?.querySelector('label')?.textContent || field.name;
            return `${label}: ${field.validationMessage}`;
        });
        
        this.showFormErrors(errors);
    }
    
    showFormErrors(errors) {
        const alertsDiv = document.getElementById('form-alerts');
        
        if (errors.length === 0) {
            alertsDiv.innerHTML = '';
            return;
        }
        
        const errorList = errors.map(error => `<li>${error}</li>`).join('');
        
        alertsDiv.innerHTML = `
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <h6><i class="bi bi-exclamation-triangle"></i> Please correct the following errors:</h6>
                <ul class="mb-0">${errorList}</ul>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    new InventoryAddForm();
});