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
        this.photoManager = null;

        // Requirement marks, the Diameter label and Shape filtering are owned
        // by the shared module, which reads the rules the server rendered into
        // the page. This form does not restate them.
        this.dimensionRequirements = new DimensionRequirements().init();

        // Material suggestions cache
        this.materialSuggestions = [];
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupBarcodeScanning();
        // Only set up old autocomplete if MaterialSelector is not active
        if (!window.MATERIAL_SELECTOR_ACTIVE) {
            console.log('InventoryAdd: Setting up old autocomplete');
            this.setupMaterialAutocomplete();
        } else {
            console.log('InventoryAdd: MaterialSelector is active, skipping old autocomplete');
        }
        this.autoPopulateJaId();
        
        // Initialize carry forward data from sessionStorage if available
        this.initializeCarryForwardData();
        
        // Initialize photo manager
        this.initializePhotoManager();
    }
    
    setupEventListeners() {
        // Form submission. Both submit buttons go through this one listener --
        // which one was pressed is read from event.submitter inside the handler.
        // A second listener on the continue button would be a second entry point
        // for one user action, which is what this replaced.
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        // Honour "continue" on the bulk path. Bulk creation answers with JSON
        // consumed by fetch(), so the server cannot redirect the way it does for
        // a single item -- the client owns this navigation. Re-rendering the
        // form is what makes the end state identical to the single-item path
        // rather than merely similar. Registered once, not per submission.
        const bulkModal = document.getElementById('bulkLabelPrintingModal');
        if (bulkModal) {
            bulkModal.addEventListener('hidden.bs.modal', () => {
                if (this.continueAfterBulk) {
                    window.location.href = '/inventory/add';
                }
            });
        }

        // Type and shape changes are handled by DimensionRequirements.

        // Quantity to create field
        const quantityField = document.getElementById('quantity_to_create');
        if (quantityField) {
            quantityField.addEventListener('input', () => this.updateBulkCreationInfo());
            quantityField.addEventListener('change', () => this.updateBulkCreationInfo());
        }

        // JA ID field changes should also update bulk creation info
        document.getElementById('ja_id').addEventListener('input', () => this.updateBulkCreationInfo());

        // Barcode scan buttons
        document.getElementById('scan-ja-id-btn').addEventListener('click', () => {
            this.startBarcodeCapture('ja_id');
        });
        
        // Carry forward functionality
        document.getElementById('carry-forward-btn').addEventListener('click', () => {
            this.carryForwardData();
        });
        
        // Material suggestions button removed - using pure autocomplete

        // Thread size lookup
        this.setupThreadSizeLookup();

        // Real-time validation
        this.setupRealTimeValidation();
        
        // Prevent Enter key submission for barcode scanner fields
        this.setupEnterKeyPrevention();
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
    
    
    async autoPopulateJaId() {
        const jaIdInput = document.getElementById('ja_id');
        
        // Only auto-populate if the field is empty
        if (jaIdInput.value.trim() !== '') {
            return;
        }
        
        try {
            const response = await fetch('/api/inventory/next-ja-id');
            const data = await response.json();
            
            if (response.ok && data.success) {
                // Re-check the guard on this side of the await. The field was empty
                // when we started the fetch, but the user (or a barcode scanner) may
                // have typed into it since, and overwriting that both loses their
                // input and can concatenate with it -- a programmatic fill selects
                // the field's contents and then inserts, and a write landing between
                // those two steps collapses the selection so the insert appends.
                if (jaIdInput.value.trim() !== '') {
                    return;
                }

                jaIdInput.value = data.next_ja_id;
                console.log(`Auto-populated JA ID: ${data.next_ja_id}`);
                
                // Clear validation errors explicitly
                jaIdInput.classList.remove('is-invalid');
                jaIdInput.setCustomValidity('');
                
                // Trigger validation events to update Bootstrap validation state
                jaIdInput.dispatchEvent(new Event('input', { bubbles: true }));
                jaIdInput.dispatchEvent(new Event('change', { bubbles: true }));
                
                // Always force revalidation to clear any remaining errors
                jaIdInput.checkValidity();
                
                // Remove was-validated class to clear error displays if form is now valid
                if (this.form.checkValidity()) {
                    this.form.classList.remove('was-validated');
                } else {
                    // If form is still invalid but JA ID is now valid, still try to clear its specific errors
                    this.form.classList.add('was-validated');
                }
            } else {
                console.warn('Failed to auto-populate JA ID:', data.error);
            }
        } catch (error) {
            console.warn('Error auto-populating JA ID:', error);
            // Silently fail - user can still manually enter or use generate button
        }
    }
    
    setupMaterialAutocomplete() {
        const materialInput = document.getElementById('material');
        const suggestionsDiv = document.getElementById('material-suggestions');
        
        materialInput.addEventListener('input', WorkshopInventory.utils.debounce(async (e) => {
            const query = e.target.value.trim();
            if (query.length >= 1) {
                await this.showMaterialMatches(query);
            } else {
                suggestionsDiv.style.display = 'none';
            }
        }, 200));
        
        // Show initial suggestions when field is focused
        materialInput.addEventListener('focus', async () => {
            const query = materialInput.value.trim();
            if (query.length >= 1) {
                await this.showMaterialMatches(query);
            } else {
                // Show categories when no query
                await this.showMaterialMatches('');
            }
        });
        
        // Hide suggestions when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#material') && !e.target.closest('#material-suggestions')) {
                suggestionsDiv.style.display = 'none';
            }
        });
    }
    
    // Material suggestions now use dynamic API calls
    
    async showMaterialMatches(query) {
        const suggestionsDiv = document.getElementById('material-suggestions');
        
        try {
            // Build API query
            const params = new URLSearchParams();
            if (query) {
                params.append('q', query);
            }
            params.append('limit', '10');
            
            const response = await fetch(`/api/materials/suggestions?${params}`);
            if (!response.ok) {
                throw new Error('Failed to fetch suggestions');
            }
            
            const matches = await response.json();
            
            if (matches.length === 0) {
                suggestionsDiv.style.display = 'none';
                return;
            }
            
            const html = matches.map(material => 
                `<a class="dropdown-item" href="#" data-material="${material}">${material}</a>`
            ).join('');
            
            suggestionsDiv.innerHTML = html;
            suggestionsDiv.style.display = 'block';
            
            // Add click handlers
            suggestionsDiv.querySelectorAll('.dropdown-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    e.preventDefault();
                    const materialInput = document.getElementById('material');
                    materialInput.value = item.dataset.material;
                    suggestionsDiv.style.display = 'none';
                    
                    // Trigger validation events to clear validation state
                    materialInput.dispatchEvent(new Event('input', { bubbles: true }));
                    materialInput.dispatchEvent(new Event('change', { bubbles: true }));
                    materialInput.dispatchEvent(new Event('blur', { bubbles: true }));
                });
            });
            
        } catch (error) {
            console.warn('Failed to fetch material suggestions:', error);
            // Fallback to hiding suggestions
            suggestionsDiv.style.display = 'none';
        }
    }
    
    // showMaterialSuggestions method removed - using pure autocomplete

    setupThreadSizeLookup() {
        const threadSizeInput = document.getElementById('thread_size');
        const threadSeriesSelect = document.getElementById('thread_series');

        if (!threadSizeInput || !threadSeriesSelect) {
            return; // Thread fields not present on this form
        }

        // Add event listener for thread size changes
        threadSizeInput.addEventListener('blur', async () => {
            const threadSize = threadSizeInput.value.trim();

            if (!threadSize) {
                return; // No thread size entered
            }

            try {
                // Call the API to lookup thread series
                const response = await fetch(`/api/thread-series-lookup?thread_size=${encodeURIComponent(threadSize)}`);
                const data = await response.json();

                if (data.success && data.series) {
                    // Check if the series exists in the dropdown options
                    const seriesOption = Array.from(threadSeriesSelect.options)
                        .find(option => option.value === data.series);

                    if (seriesOption && threadSeriesSelect.value !== data.series) {
                        // Auto-populate the series field with brief visual feedback
                        threadSeriesSelect.value = data.series;

                        // Add brief highlight effect
                        threadSeriesSelect.style.backgroundColor = '#fff3cd';
                        threadSeriesSelect.style.border = '1px solid #ffeaa7';

                        // Remove highlight after 2 seconds
                        setTimeout(() => {
                            threadSeriesSelect.style.backgroundColor = '';
                            threadSeriesSelect.style.border = '';
                        }, 2000);

                        // Trigger change event for any dependent validation
                        threadSeriesSelect.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            } catch (error) {
                console.warn('Failed to lookup thread series:', error);
                // Silently fail - don't interrupt user workflow
            }
        });
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
        console.log('CarryForward: Starting carry forward process');
        
        // First try to get data from sessionStorage (for cross-page persistence)
        let itemData = this.lastItemData;
        if (!itemData) {
            console.log('CarryForward: No data in memory, checking sessionStorage');
            try {
                const storedData = sessionStorage.getItem('workshop_inventory_last_item');
                if (storedData) {
                    itemData = JSON.parse(storedData);
                    console.log('CarryForward: Retrieved data from sessionStorage:', itemData);
                    // Update in-memory cache
                    this.lastItemData = itemData;
                } else {
                    console.log('CarryForward: No data found in sessionStorage either');
                }
            } catch (error) {
                console.error('CarryForward: Error reading from sessionStorage:', error);
            }
        } else {
            console.log('CarryForward: Using data from memory:', itemData);
        }
        
        if (!itemData) {
            console.log('CarryForward: No previous item data available');
            WorkshopInventory.utils.showToast('No previous item data to carry forward', 'info');
            return;
        }
        
        // Fields to carry forward
        const carryFields = [
            'item_type', 'shape', 'material',
            'location', 'sub_location', 'vendor', 'purchase_location',
            'purchase_date', 'thread_series', 'thread_handedness', 'thread_size',
            'notes', 'vendor_part_number'
        ];

        console.log('CarryForward: Populating fields with data');
        const fieldsPopulated = [];
        carryFields.forEach(field => {
            const input = document.getElementById(field);
            if (input && itemData[field]) {
                const oldValue = input.value;
                input.value = itemData[field];
                fieldsPopulated.push(`${field}: "${oldValue}" -> "${itemData[field]}"`);
                console.log(`CarryForward: Set ${field} = "${itemData[field]}"`);
            }
        });

        // Carry forward dimension fields (stored in nested dimensions object)
        const dimensionFields = ['length', 'width', 'thickness', 'wall_thickness', 'weight'];
        if (itemData.dimensions) {
            dimensionFields.forEach(field => {
                const input = document.getElementById(field);
                if (input && itemData.dimensions[field]) {
                    const oldValue = input.value;
                    input.value = itemData.dimensions[field];
                    fieldsPopulated.push(`${field}: "${oldValue}" -> "${itemData.dimensions[field]}"`);
                    console.log(`CarryForward: Set ${field} = "${itemData.dimensions[field]}"`);
                }
            });
        }

        console.log('CarryForward: Fields populated:', fieldsPopulated);
        
        // Carry-forward writes Type and Shape directly, so the marks and the
        // width label have to be re-applied for the values it set.
        this.dimensionRequirements.updateShapeOptions();
        this.dimensionRequirements.apply();


        console.log('CarryForward: Successfully carried forward data');
        WorkshopInventory.utils.showToast('Previous item data carried forward', 'success');
    }
    
    initializeCarryForwardData() {
        console.log('Init: Checking for previous item data in sessionStorage');
        try {
            const storedData = sessionStorage.getItem('workshop_inventory_last_item');
            if (storedData) {
                this.lastItemData = JSON.parse(storedData);
                console.log('Init: Restored previous item data from sessionStorage:', this.lastItemData);
            } else {
                console.log('Init: No previous item data found in sessionStorage');
            }
        } catch (error) {
            console.error('Init: Error reading previous item data from sessionStorage:', error);
            // Clear corrupted data
            try {
                sessionStorage.removeItem('workshop_inventory_last_item');
            } catch (clearError) {
                console.error('Init: Error clearing corrupted sessionStorage data:', clearError);
            }
        }
    }
    
    initializePhotoManager() {
        if (typeof PhotoManager !== 'undefined') {
            console.log('Initializing PhotoManager for Add Item form');
            this.photoManager = PhotoManager.init('#photo-manager-container', {
                readOnly: false,
                itemId: null // No item ID yet since we're adding a new item
            });
            console.log('PhotoManager initialized successfully');
        } else {
            console.warn('PhotoManager not available');
        }
    }
    
    async handleSubmit(event) {
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

        // One submission per user action. The buttons are disabled below while a
        // request is in flight, but Enter still reaches the form even when they
        // are, so the flag is what actually guarantees it.
        if (this.submitting) {
            console.log('Submit: Ignoring submission, one is already in flight');
            return;
        }
        this.submitting = true;

        // Which control was pressed. Implicit submission (Enter) reports the
        // form's first submit button, which is #submit-btn -- so Enter means
        // Add, matching the previous behavior.
        const continueAdding = event?.submitter?.value === 'continue';

        // Carry the choice in the form's own hidden field rather than appending
        // one per submission: form.submit() sends no submitter, and appended
        // inputs outlive a bulk submission that never navigates away.
        document.getElementById('submit-type').value = continueAdding ? 'continue' : 'add';

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
        console.log('Submit: Collected form data for carry forward:', this.lastItemData);
        
        // Store in sessionStorage for persistence across page redirects
        try {
            sessionStorage.setItem('workshop_inventory_last_item', JSON.stringify(this.lastItemData));
            console.log('Submit: Stored form data in sessionStorage for carry forward');
        } catch (error) {
            console.error('Submit: Failed to store data in sessionStorage:', error);
        }
        
        // Log submission type for debugging
        console.log(`Submit: Submitting form with type: ${continueAdding ? 'continue' : 'add'}`);

        // Check if this is bulk creation (quantity > 1)
        const quantityField = document.getElementById('quantity_to_create');
        const quantity = quantityField ? parseInt(quantityField.value) : 1;
        console.log(`Submit: Detected quantity=${quantity} from field value="${quantityField?.value}"`);

        if (quantity > 1) {
            console.log(`Submit: Using AJAX for bulk creation (quantity=${quantity})`);
            // Set on every bulk submission, not only the continue ones, so a
            // failed continue cannot leave the flag set for a later plain Add.
            this.continueAfterBulk = continueAdding;
            // Use AJAX for bulk creation to handle JSON response
            try {
                const formData = new FormData(this.form);
                const response = await fetch(this.form.action, {
                    method: 'POST',
                    body: formData
                });
                console.log(`Submit: Got response status ${response.status}`);

                const data = await response.json();
                console.log(`Submit: Parsed JSON response:`, data);

                if (data.success) {
                    console.log(`Submit: Success! Created ${data.count} items, showing modal...`);
                    // Store created JA IDs for label printing
                    this.createdJaIds = data.ja_ids;
                    this.bulkCreationCount = data.count;

                    // Show success message
                    WorkshopInventory.utils.showToast(data.message, 'success');

                    // Trigger bulk label printing modal (will be implemented in next task)
                    this.showBulkLabelPrintingModal();
                } else {
                    console.log(`Submit: Error in response:`, data.error);
                    // Show error message
                    WorkshopInventory.utils.showToast(data.error || 'Failed to create items', 'error');
                }
            } catch (error) {
                console.error('Error during bulk creation:', error);
                WorkshopInventory.utils.showToast('An error occurred. Please try again.', 'error');
            } finally {
                // One restore for success, failure and error alike (FR-005).
                // Two copies of this drifting apart is how a disabled button
                // gets stranded.
                submitBtn.innerHTML = originalSubmitHTML;
                continueBtn.innerHTML = originalContinueHTML;
                submitBtn.disabled = false;
                continueBtn.disabled = false;
                this.submitting = false;
            }
        } else {
            // Submit form normally for single item creation. The page is being
            // replaced, so the loading state stays up and `submitting` stays set
            // until the new document loads.
            this.form.submit();
        }
    }
    
    collectFormData() {
        const formData = new FormData(this.form);
        const data = {};
        
        // Basic fields
        const basicFields = [
            'ja_id', 'item_type', 'shape', 'material',
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
            if (threadSeries) {
                data.thread.series = threadSeries;
                data.thread_series = threadSeries;  // Store at top level for carry forward
            }
            if (threadHandedness) {
                data.thread.handedness = threadHandedness;
                data.thread_handedness = threadHandedness;  // Store at top level for carry forward
            }
            if (threadSize) {
                data.thread.size = threadSize.trim();
                data.thread_size = threadSize.trim();  // Store at top level for carry forward
            }
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
    
    showValidationErrors() {
        const invalidFields = this.form.querySelectorAll(':invalid');
        const errors = Array.from(invalidFields).map(field => {
            const label = field.closest('.mb-3')?.querySelector('label')?.textContent || field.name;
            return `${label}: ${field.validationMessage}`;
        });
        
        this.showFormErrors(errors);
    }
    
    setupEnterKeyPrevention() {
        // Prevent Enter key from submitting form when pressed in JA ID or Location fields
        // This is needed because barcode scanners send Enter after scanning
        const fieldsToPrevent = ['ja_id', 'location'];
        
        fieldsToPrevent.forEach(fieldId => {
            const field = document.getElementById(fieldId);
            if (field) {
                field.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        // Move focus to next field instead of submitting
                        const nextField = this.getNextField(field);
                        if (nextField) {
                            nextField.focus();
                        }
                    }
                });
            }
        });
    }
    
    getNextField(currentField) {
        // Get all focusable form elements
        const formElements = this.form.querySelectorAll('input:not([type="hidden"]), select, textarea');
        const elementsArray = Array.from(formElements);
        const currentIndex = elementsArray.indexOf(currentField);

        // Return next focusable element, or null if it's the last one
        return elementsArray[currentIndex + 1] || null;
    }

    updateBulkCreationInfo() {
        const quantityField = document.getElementById('quantity_to_create');
        const jaIdField = document.getElementById('ja_id');
        const infoDiv = document.getElementById('bulk-creation-info');
        const messageSpan = document.getElementById('bulk-creation-message');

        if (!quantityField || !jaIdField || !infoDiv || !messageSpan) {
            return;
        }

        const quantity = parseInt(quantityField.value) || 1;
        const jaId = jaIdField.value.trim();

        // Validate quantity range
        if (quantity < 1) {
            quantityField.value = 1;
            infoDiv.classList.add('d-none');
            return;
        }
        if (quantity > 100) {
            quantityField.value = 100;
            WorkshopInventory.utils.showToast('Maximum quantity is 100', 'warning');
            return;
        }

        // Show info message if quantity > 1 and JA ID is valid
        if (quantity > 1 && jaId.match(/^JA\d{6}$/)) {
            // Calculate JA ID range (starting from current + 1 for the additional items)
            const jaNum = parseInt(jaId.substring(2));
            const firstNewId = `JA${String(jaNum + 1).padStart(6, '0')}`;
            const lastNewId = `JA${String(jaNum + quantity - 1).padStart(6, '0')}`;

            messageSpan.textContent = `This will create ${quantity} items: ${jaId} (original) and ${quantity - 1} copies (${firstNewId} - ${lastNewId})`;
            infoDiv.classList.remove('d-none');
        } else if (quantity > 1) {
            messageSpan.textContent = `This will create ${quantity} items with sequential JA IDs`;
            infoDiv.classList.remove('d-none');
        } else {
            infoDiv.classList.add('d-none');
        }
    }

    showBulkLabelPrintingModal() {
        console.log('showBulkLabelPrintingModal: Called');
        const modal = document.getElementById('bulkLabelPrintingModal');
        console.log('showBulkLabelPrintingModal: modal element found:', !!modal);
        console.log('showBulkLabelPrintingModal: createdJaIds:', this.createdJaIds);
        console.log('showBulkLabelPrintingModal: bulkCreationCount:', this.bulkCreationCount);

        if (!modal || !this.createdJaIds || this.createdJaIds.length === 0) {
            console.log('showBulkLabelPrintingModal: Early return - missing modal or JA IDs');
            return;
        }

        // Update modal title
        const modalTitle = document.querySelector('#bulkLabelPrintingModalLabel');
        if (modalTitle) {
            modalTitle.innerHTML = `<i class="bi bi-printer"></i> ${this.bulkCreationCount} Items Created Successfully`;
            console.log('showBulkLabelPrintingModal: Updated modal title');
        }

        // Update summary
        const summary = document.getElementById('bulk-creation-summary');
        const firstId = this.createdJaIds[0];
        const lastId = this.createdJaIds[this.createdJaIds.length - 1];
        summary.textContent = `Created ${this.bulkCreationCount} items: ${firstId} - ${lastId}`;
        console.log('showBulkLabelPrintingModal: Updated summary');

        // Populate items list
        const itemsList = document.getElementById('bulk-label-items-list');
        if (itemsList) {
            itemsList.innerHTML = '';
            this.createdJaIds.forEach(jaId => {
                const li = document.createElement('li');
                li.className = 'list-group-item';
                // Try to get display name from form data
                const material = document.getElementById('material').value || 'Item';
                li.textContent = `${jaId} - ${material}`;
                itemsList.appendChild(li);
            });
            console.log('showBulkLabelPrintingModal: Populated items list');
        }

        // Reset modal state
        document.getElementById('bulk-print-progress').classList.add('d-none');
        document.getElementById('bulk-print-all-btn').classList.remove('d-none');
        document.getElementById('bulk-print-done-btn').classList.add('d-none');
        document.getElementById('bulk-print-skip').classList.remove('d-none');

        // Setup print button handler
        const printBtn = document.getElementById('bulk-print-all-btn');
        printBtn.onclick = () => this.printAllLabels();

        // Show modal
        console.log('showBulkLabelPrintingModal: Showing modal...');
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        console.log('showBulkLabelPrintingModal: Modal show() called');
    }

    async printAllLabels() {
        const labelSize = document.getElementById('bulk-label-size').value;
        const progressDiv = document.getElementById('bulk-print-progress');
        const progressBar = document.getElementById('bulk-print-progress-bar');
        const statusSpan = document.getElementById('bulk-print-status');
        const errorsDiv = document.getElementById('bulk-print-errors');
        const printBtn = document.getElementById('bulk-print-all-btn');
        const doneBtn = document.getElementById('bulk-print-done-btn');
        const skipBtn = document.getElementById('bulk-print-skip');

        // Show progress
        progressDiv.classList.remove('d-none');
        printBtn.classList.add('d-none');
        skipBtn.classList.add('d-none');

        let successCount = 0;
        let failureCount = 0;
        const errors = [];

        for (let i = 0; i < this.createdJaIds.length; i++) {
            const jaId = this.createdJaIds[i];
            const progress = Math.round(((i + 1) / this.createdJaIds.length) * 100);

            statusSpan.textContent = `Printing ${i + 1} of ${this.createdJaIds.length}: ${jaId}`;
            progressBar.style.width = `${progress}%`;
            progressBar.textContent = `${progress}%`;

            try {
                const response = await fetch('/api/labels/print', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        ja_id: jaId,
                        label_size: labelSize
                    })
                });

                if (response.ok) {
                    successCount++;
                } else {
                    failureCount++;
                    errors.push(`${jaId}: ${response.statusText}`);
                }
            } catch (error) {
                failureCount++;
                errors.push(`${jaId}: ${error.message}`);
            }
        }

        // Show results
        if (failureCount > 0) {
            errorsDiv.classList.remove('d-none');
            errorsDiv.innerHTML = `
                <strong>Warning:</strong> ${failureCount} label(s) failed to print:<br>
                ${errors.map(e => `• ${e}`).join('<br>')}
            `;
        }

        statusSpan.textContent = `Complete: ${successCount} printed, ${failureCount} failed`;
        progressBar.classList.remove('progress-bar-animated');

        // Show done button
        doneBtn.classList.remove('d-none');

        // Show success message
        if (successCount > 0) {
            WorkshopInventory.utils.showToast(`Printed ${successCount} label(s) successfully`, 'success');
        }
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
    // Exposed like window.moveManager on the move page, so a test can drive
    // autoPopulateJaId() across its own await boundary.
    window.addItemForm = new InventoryAddForm();
});