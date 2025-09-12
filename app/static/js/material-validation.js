/**
 * Shared Material Field Validation Component
 * 
 * Provides taxonomy-based validation for material fields in both Add and Edit forms.
 * Validates that material names match the materials taxonomy exactly.
 */

class MaterialValidator {
    constructor(materialFieldId = 'material', validMaterials = []) {
        this.materialField = document.getElementById(materialFieldId);
        this.validMaterials = new Set(validMaterials.map(m => m.toLowerCase()));
        this.validMaterialsExact = validMaterials; // Keep original case for display
        
        if (!this.materialField) {
            console.warn(`Material field #${materialFieldId} not found`);
            return;
        }
        
        this.setupValidation();
        this.setupCustomValidationMessage();
    }
    
    /**
     * Initialize validation on the material field
     */
    setupValidation() {
        // Add custom validation on input/change
        this.materialField.addEventListener('input', () => this.validateMaterial());
        this.materialField.addEventListener('blur', () => this.validateMaterial());
        this.materialField.addEventListener('change', () => this.validateMaterial());
        
        // Validate on form submission
        const form = this.materialField.closest('form');
        if (form) {
            form.addEventListener('submit', (e) => {
                if (!this.validateMaterial()) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Ensure form shows validation state
                    form.classList.add('was-validated');
                }
            });
        }
    }
    
    /**
     * Set up custom validation message
     */
    setupCustomValidationMessage() {
        // Find or create invalid feedback element
        let invalidFeedback = this.materialField.parentElement.querySelector('.invalid-feedback');
        if (!invalidFeedback) {
            invalidFeedback = document.createElement('div');
            invalidFeedback.className = 'invalid-feedback';
            this.materialField.parentElement.appendChild(invalidFeedback);
        }
        this.invalidFeedback = invalidFeedback;
    }
    
    /**
     * Validate the current material value
     * @returns {boolean} True if valid, false if invalid
     */
    validateMaterial() {
        const value = this.materialField.value.trim();
        
        // Check if empty - let browser's built-in required validation handle empty fields
        if (!value) {
            // Clear our custom validation so HTML5 required validation can work
            this.materialField.setCustomValidity('');
            this.materialField.classList.remove('is-valid', 'is-invalid');
            return this.materialField.checkValidity(); // Return browser's validity check
        }
        
        // Check if material is in taxonomy (case insensitive)
        const isValid = this.validMaterials.has(value.toLowerCase());
        
        if (!isValid) {
            this.setValidationState(false, 'Material must be from materials taxonomy. Use autocomplete suggestions.');
            return false;
        } else {
            this.setValidationState(true, '');
            return true;
        }
    }
    
    /**
     * Set the validation state of the material field
     * @param {boolean} isValid Whether the field is valid
     * @param {string} message Error message to display
     */
    setValidationState(isValid, message) {
        this.materialField.classList.remove('is-valid', 'is-invalid');
        
        if (isValid) {
            this.materialField.classList.add('is-valid');
            if (this.invalidFeedback) {
                this.invalidFeedback.textContent = '';
            }
            // Clear custom validation message
            this.materialField.setCustomValidity('');
        } else {
            this.materialField.classList.add('is-invalid');
            if (this.invalidFeedback) {
                this.invalidFeedback.textContent = message;
            }
            // Set custom validation message for HTML5 validation
            this.materialField.setCustomValidity(message);
        }
    }
    
    /**
     * Get list of material suggestions for the current input
     * @param {string} query Current input value
     * @returns {Array} Array of matching material names
     */
    getSuggestions(query) {
        if (!query) return this.validMaterialsExact.slice(0, 10);
        
        const queryLower = query.toLowerCase();
        const suggestions = [];
        
        // Exact matches first
        for (const material of this.validMaterialsExact) {
            if (material.toLowerCase() === queryLower) {
                suggestions.unshift(material); // Add to beginning
                break;
            }
        }
        
        // Starts with matches
        for (const material of this.validMaterialsExact) {
            if (material.toLowerCase().startsWith(queryLower) && 
                !suggestions.includes(material)) {
                suggestions.push(material);
            }
        }
        
        // Contains matches
        for (const material of this.validMaterialsExact) {
            if (material.toLowerCase().includes(queryLower) && 
                !suggestions.includes(material)) {
                suggestions.push(material);
            }
        }
        
        return suggestions.slice(0, 10); // Limit to 10 suggestions
    }
    
    /**
     * Check if a material name is valid
     * @param {string} materialName The material name to check
     * @returns {boolean} True if valid, false if invalid
     */
    static isValidMaterial(materialName, validMaterials) {
        const validSet = new Set(validMaterials.map(m => m.toLowerCase()));
        return validSet.has(materialName.toLowerCase().trim());
    }
}

// Auto-initialize if valid materials are available in the page
document.addEventListener('DOMContentLoaded', function() {
    // Check for valid materials data in various formats
    let validMaterials = [];
    
    if (window.validMaterials) {
        validMaterials = window.validMaterials;
    } else if (window.materialsData) {
        validMaterials = window.materialsData.map(m => m.name || m);
    } else {
        // Try to get from page data attribute
        const body = document.body;
        if (body.dataset.validMaterials) {
            try {
                validMaterials = JSON.parse(body.dataset.validMaterials);
            } catch (e) {
                console.warn('Failed to parse valid materials data:', e);
            }
        }
    }
    
    if (validMaterials.length > 0) {
        // Initialize for add form
        if (document.getElementById('material')) {
            window.materialValidator = new MaterialValidator('material', validMaterials);
        }
    } else {
        console.warn('No valid materials data found for validation');
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MaterialValidator;
}