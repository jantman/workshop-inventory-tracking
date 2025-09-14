/**
 * Enhanced Material Selector Component
 * 
 * Provides progressive disclosure interface for material selection with:
 * - Empty state showing top-level categories
 * - Smart filtering across all taxonomy levels
 * - Click-to-navigate and type-to-filter functionality
 * - Visual hierarchy with icons and breadcrumbs
 */

class MaterialSelector {
    constructor(inputElementId, options = {}) {
        this.inputElement = document.getElementById(inputElementId);
        this.suggestionsContainer = null;
        this.breadcrumbContainer = null;
        
        // Configuration
        this.config = {
            maxResults: options.maxResults || 10,
            debounceDelay: options.debounceDelay || 200,
            showBreadcrumbs: options.showBreadcrumbs !== false,
            enableKeyboardNavigation: options.enableKeyboardNavigation !== false,
            ...options
        };
        
        // State
        this.taxonomyData = null;
        this.currentPath = []; // Navigation breadcrumb path
        this.selectedIndex = -1; // For keyboard navigation
        this.isNavigationMode = false; // true when browsing hierarchy, false when searching
        
        // Icons for different levels
        this.icons = {
            category: '📁',
            family: '📂', 
            material: '🔧',
            back: '⬅️',
            search: '🔍'
        };
        
        if (!this.inputElement) {
            console.error(`MaterialSelector: Input element '${inputElementId}' not found`);
            return;
        }
        
        this.init();
    }
    
    async init() {
        // Create suggestions container
        this.createSuggestionsContainer();
        
        // Load taxonomy data
        await this.loadTaxonomyData();
        
        // Set up event listeners
        this.setupEventListeners();
        
        console.log('MaterialSelector initialized for', this.inputElement.id);
    }
    
    createSuggestionsContainer() {
        // Find existing suggestions container or create new one
        this.suggestionsContainer = this.inputElement.parentElement.querySelector('.material-suggestions');
        
        if (!this.suggestionsContainer) {
            this.suggestionsContainer = document.createElement('div');
            this.suggestionsContainer.className = 'material-suggestions dropdown-menu position-absolute w-100';
            this.suggestionsContainer.style.cssText = `
                max-height: 300px;
                overflow-y: auto;
                z-index: 1000;
                display: none;
            `;
            
            // Insert after the input element
            this.inputElement.parentElement.appendChild(this.suggestionsContainer);
        }
        
        // Create breadcrumb container if enabled
        if (this.config.showBreadcrumbs) {
            this.breadcrumbContainer = document.createElement('div');
            this.breadcrumbContainer.className = 'material-breadcrumbs small text-muted p-2 border-bottom';
            this.breadcrumbContainer.style.display = 'none';
        }
    }
    
    async loadTaxonomyData() {
        try {
            const response = await fetch('/api/materials/hierarchy');
            if (!response.ok) {
                throw new Error('Failed to load taxonomy data');
            }
            
            const data = await response.json();
            this.taxonomyData = data.hierarchy;
            
            console.log(`Loaded taxonomy: ${data.summary.categories} categories, ${data.summary.total_materials} materials`);
            
        } catch (error) {
            console.error('MaterialSelector: Failed to load taxonomy data:', error);
            // Fallback to simple suggestions API
            this.taxonomyData = null;
        }
    }
    
    setupEventListeners() {
        // Input events
        this.inputElement.addEventListener('input', this.debounce((e) => {
            this.handleInput(e.target.value);
        }, this.config.debounceDelay));
        
        this.inputElement.addEventListener('focus', () => {
            this.handleFocus();
        });
        
        this.inputElement.addEventListener('blur', (e) => {
            // Delay hiding to allow clicks on suggestions
            setTimeout(() => this.handleBlur(e), 150);
        });
        
        // Keyboard navigation
        if (this.config.enableKeyboardNavigation) {
            this.inputElement.addEventListener('keydown', (e) => {
                this.handleKeyDown(e);
            });
        }
        
        // Click outside to close
        document.addEventListener('click', (e) => {
            if (!this.inputElement.contains(e.target) && 
                !this.suggestionsContainer.contains(e.target)) {
                this.hideSuggestions();
            }
        });
    }
    
    async handleInput(value) {
        const query = value.trim();
        
        if (query === '') {
            // Show categories when input is empty
            this.isNavigationMode = true;
            this.currentPath = [];
            await this.showCategories();
        } else {
            // Search mode - filter across all levels
            this.isNavigationMode = false;
            await this.showSearchResults(query);
        }
    }
    
    async handleFocus() {
        const query = this.inputElement.value.trim();
        
        if (query === '') {
            // Show categories on focus if empty
            this.isNavigationMode = true;
            this.currentPath = [];
            await this.showCategories();
        } else {
            // Show search results if there's a query
            this.isNavigationMode = false;
            await this.showSearchResults(query);
        }
    }
    
    handleBlur(e) {
        // Only hide if not clicking on suggestions
        if (!this.suggestionsContainer.contains(e.relatedTarget)) {
            this.hideSuggestions();
        }
    }
    
    handleKeyDown(e) {
        if (!this.suggestionsContainer || this.suggestionsContainer.style.display === 'none') {
            return;
        }
        
        const items = this.suggestionsContainer.querySelectorAll('.suggestion-item:not(.disabled)');
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.selectedIndex = Math.min(this.selectedIndex + 1, items.length - 1);
                this.updateSelection(items);
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                this.selectedIndex = Math.max(this.selectedIndex - 1, -1);
                this.updateSelection(items);
                break;
                
            case 'Enter':
                e.preventDefault();
                if (this.selectedIndex >= 0 && items[this.selectedIndex]) {
                    items[this.selectedIndex].click();
                }
                break;
                
            case 'Escape':
                this.hideSuggestions();
                break;
        }
    }
    
    updateSelection(items) {
        items.forEach((item, index) => {
            item.classList.toggle('active', index === this.selectedIndex);
        });
    }
    
    async showCategories() {
        if (!this.taxonomyData) {
            console.warn('MaterialSelector: No taxonomy data available');
            return;
        }
        
        let html = '';
        
        // Show back button if we're in a sub-category
        if (this.currentPath.length > 0) {
            html += `
                <a href="#" class="suggestion-item dropdown-item d-flex align-items-center back-button" 
                   data-action="back">
                    <span class="me-2">${this.icons.back}</span>
                    <div>
                        <div class="fw-medium">Back</div>
                        <small class="text-muted">Return to ${this.getBreadcrumbText()}</small>
                    </div>
                </a>
                <div class="dropdown-divider"></div>
            `;
        }
        
        // Get current level items
        const currentItems = this.getCurrentLevelItems();
        
        currentItems.forEach(item => {
            const icon = this.getItemIcon(item);
            const hasChildren = this.hasChildren(item);
            
            html += `
                <a href="#" class="suggestion-item dropdown-item d-flex align-items-center ${hasChildren ? 'navigable' : 'selectable'}" 
                   data-name="${item.name}" data-level="${item.level}" data-type="${hasChildren ? 'navigate' : 'select'}">
                    <span class="me-2">${icon}</span>
                    <div class="flex-grow-1">
                        <div class="fw-medium">${item.name}</div>
                        ${hasChildren ? `<small class="text-muted">Click to explore</small>` : ''}
                    </div>
                    ${hasChildren ? '<span class="text-muted">›</span>' : ''}
                </a>
            `;
        });
        
        if (currentItems.length === 0) {
            html = '<div class="dropdown-item-text text-muted">No items found</div>';
        }
        
        this.suggestionsContainer.innerHTML = html;
        this.showSuggestions();
        this.attachItemClickHandlers();
        this.updateBreadcrumb();
    }
    
    async showSearchResults(query) {
        // First get exact matches from the simple API
        const exactMatches = await this.getExactMatches(query);
        
        // Then get taxonomy branches that contain matches
        const taxonomyMatches = this.getTaxonomyMatches(query);
        
        let html = '';
        
        // Show search context
        html += `
            <div class="dropdown-item-text text-primary small border-bottom pb-2 mb-2">
                ${this.icons.search} Search results for "${query}"
            </div>
        `;
        
        // Exact material matches first
        if (exactMatches.length > 0) {
            html += '<div class="dropdown-item-text small text-muted fw-medium mb-1">Materials:</div>';
            
            exactMatches.slice(0, this.config.maxResults).forEach(material => {
                html += `
                    <a href="#" class="suggestion-item dropdown-item d-flex align-items-center selectable" 
                       data-name="${material}" data-type="select">
                        <span class="me-2">${this.icons.material}</span>
                        <div>
                            <div class="fw-medium">${this.highlightMatch(material, query)}</div>
                        </div>
                    </a>
                `;
            });
        }
        
        // Taxonomy branches with matches
        if (taxonomyMatches.length > 0) {
            if (exactMatches.length > 0) {
                html += '<div class="dropdown-divider"></div>';
            }
            html += '<div class="dropdown-item-text small text-muted fw-medium mb-1">Categories:</div>';
            
            taxonomyMatches.slice(0, 5).forEach(branch => {
                const icon = this.getItemIcon(branch.item);
                html += `
                    <a href="#" class="suggestion-item dropdown-item d-flex align-items-center navigable" 
                       data-name="${branch.item.name}" data-level="${branch.item.level}" data-type="navigate" data-path="${branch.path}">
                        <span class="me-2">${icon}</span>
                        <div class="flex-grow-1">
                            <div class="fw-medium">${this.highlightMatch(branch.item.name, query)}</div>
                            <small class="text-muted">${branch.path} • ${branch.matchCount} matches</small>
                        </div>
                        <span class="text-muted">›</span>
                    </a>
                `;
            });
        }
        
        if (exactMatches.length === 0 && taxonomyMatches.length === 0) {
            html += '<div class="dropdown-item-text text-muted">No matches found</div>';
        }
        
        this.suggestionsContainer.innerHTML = html;
        this.showSuggestions();
        this.attachItemClickHandlers();
        this.updateBreadcrumb();
    }
    
    async getExactMatches(query) {
        try {
            const params = new URLSearchParams();
            params.append('q', query);
            params.append('limit', this.config.maxResults.toString());
            
            const response = await fetch(`/api/materials/suggestions?${params}`);
            if (!response.ok) {
                throw new Error('Failed to fetch suggestions');
            }
            
            return await response.json();
        } catch (error) {
            console.warn('MaterialSelector: Failed to get exact matches:', error);
            return [];
        }
    }
    
    getTaxonomyMatches(query) {
        if (!this.taxonomyData) return [];
        
        const matches = [];
        const queryLower = query.toLowerCase();
        
        // Search through all levels of taxonomy
        this.taxonomyData.forEach(category => {
            if (category.name.toLowerCase().includes(queryLower)) {
                const matchCount = this.countMatches(category, queryLower);
                matches.push({
                    item: category,
                    path: category.name,
                    matchCount
                });
            }
            
            category.families.forEach(family => {
                if (family.name.toLowerCase().includes(queryLower)) {
                    const matchCount = this.countMatches(family, queryLower);
                    matches.push({
                        item: family,
                        path: `${category.name} › ${family.name}`,
                        matchCount
                    });
                }
            });
        });
        
        return matches.sort((a, b) => b.matchCount - a.matchCount);
    }
    
    countMatches(item, query) {
        let count = 0;
        
        if (item.name.toLowerCase().includes(query)) count++;
        
        if (item.families) {
            item.families.forEach(family => {
                count += this.countMatches(family, query);
            });
        }
        
        if (item.materials) {
            item.materials.forEach(material => {
                if (material.name.toLowerCase().includes(query)) count++;
            });
        }
        
        return count;
    }
    
    getCurrentLevelItems() {
        if (!this.taxonomyData) return [];
        
        let currentLevel = this.taxonomyData;
        
        // Navigate to current path
        for (let i = 0; i < this.currentPath.length; i++) {
            const pathItem = this.currentPath[i];
            const found = currentLevel.find(item => item.name === pathItem.name);
            
            if (found) {
                if (pathItem.level === 1 && found.families) {
                    currentLevel = found.families;
                } else if (pathItem.level === 2 && found.materials) {
                    currentLevel = found.materials;
                }
            }
        }
        
        return currentLevel;
    }
    
    hasChildren(item) {
        return (item.families && item.families.length > 0) || 
               (item.materials && item.materials.length > 0);
    }
    
    getItemIcon(item) {
        if (item.level === 1) return this.icons.category;
        if (item.level === 2) return this.icons.family;
        return this.icons.material;
    }
    
    highlightMatch(text, query) {
        if (!query) return text;
        
        const regex = new RegExp(`(${query})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }
    
    getBreadcrumbText() {
        if (this.currentPath.length === 0) return 'Categories';
        if (this.currentPath.length === 1) return this.currentPath[0].name;
        return this.currentPath.map(p => p.name).join(' › ');
    }
    
    updateBreadcrumb() {
        if (!this.config.showBreadcrumbs || !this.breadcrumbContainer) return;
        
        if (this.currentPath.length === 0) {
            this.breadcrumbContainer.style.display = 'none';
        } else {
            this.breadcrumbContainer.innerHTML = `Currently browsing: ${this.getBreadcrumbText()}`;
            this.breadcrumbContainer.style.display = 'block';
            
            // Insert breadcrumb at top of suggestions
            if (this.suggestionsContainer.firstChild) {
                this.suggestionsContainer.insertBefore(this.breadcrumbContainer, this.suggestionsContainer.firstChild);
            }
        }
    }
    
    attachItemClickHandlers() {
        const items = this.suggestionsContainer.querySelectorAll('.suggestion-item');
        
        items.forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleItemClick(item);
            });
        });
    }
    
    handleItemClick(item) {
        const action = item.dataset.action;
        const type = item.dataset.type;
        const name = item.dataset.name;
        const level = parseInt(item.dataset.level);
        
        if (action === 'back') {
            this.navigateBack();
        } else if (type === 'navigate') {
            this.navigateToItem(name, level);
        } else if (type === 'select') {
            this.selectMaterial(name);
        }
    }
    
    navigateBack() {
        if (this.currentPath.length > 0) {
            this.currentPath.pop();
            this.showCategories();
        }
    }
    
    navigateToItem(name, level) {
        this.currentPath.push({ name, level });
        this.showCategories();
    }
    
    selectMaterial(materialName) {
        // Set the input value
        this.inputElement.value = materialName;
        
        // Trigger validation events
        this.inputElement.dispatchEvent(new Event('input', { bubbles: true }));
        this.inputElement.dispatchEvent(new Event('change', { bubbles: true }));
        this.inputElement.dispatchEvent(new Event('blur', { bubbles: true }));
        
        // Hide suggestions
        this.hideSuggestions();
        
        // Reset state
        this.currentPath = [];
        this.isNavigationMode = false;
        
        console.log('MaterialSelector: Selected material:', materialName);
    }
    
    showSuggestions() {
        this.suggestionsContainer.style.display = 'block';
        this.selectedIndex = -1; // Reset keyboard selection
    }
    
    hideSuggestions() {
        if (this.suggestionsContainer) {
            this.suggestionsContainer.style.display = 'none';
        }
        this.selectedIndex = -1;
    }
    
    // Utility: debounce function
    debounce(func, wait) {
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
    
    // Public API methods
    getValue() {
        return this.inputElement.value;
    }
    
    setValue(value) {
        this.inputElement.value = value;
        this.inputElement.dispatchEvent(new Event('input', { bubbles: true }));
    }
    
    clear() {
        this.setValue('');
        this.hideSuggestions();
        this.currentPath = [];
    }
    
    destroy() {
        // Clean up event listeners and DOM elements
        if (this.suggestionsContainer) {
            this.suggestionsContainer.remove();
        }
        if (this.breadcrumbContainer) {
            this.breadcrumbContainer.remove();
        }
        console.log('MaterialSelector destroyed');
    }
}

// Auto-initialize MaterialSelector for material inputs if available
document.addEventListener('DOMContentLoaded', function() {
    // Look for material input fields
    const materialInputs = document.querySelectorAll('#material');
    
    materialInputs.forEach(input => {
        // Check if not already enhanced
        if (!input.classList.contains('material-selector-enhanced')) {
            new MaterialSelector(input.id);
            input.classList.add('material-selector-enhanced');
        }
    });
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MaterialSelector;
} else {
    window.MaterialSelector = MaterialSelector;
}