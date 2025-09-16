/**
 * History Viewer JavaScript - Item History Display Interface
 * 
 * Handles displaying item history in a modal timeline format,
 * with API integration and proper error handling.
 */

class HistoryViewer {
    constructor() {
        this.modal = null;
        this.modalBody = null;
        this.historyItemId = null;
        this.editItemLink = null;
        
        this.initializeElements();
        console.log('HistoryViewer initialized');
    }
    
    initializeElements() {
        this.modal = document.getElementById('item-history-modal');
        this.modalBody = document.getElementById('history-modal-body');
        this.historyItemId = document.getElementById('history-item-id');
        this.editItemLink = document.getElementById('edit-item-from-history-link');
    }
    
    showHistory(jaId) {
        if (!this.modal || !this.modalBody) {
            console.error('History modal elements not found');
            return;
        }
        
        // Update modal title and edit link
        this.historyItemId.textContent = jaId;
        this.editItemLink.href = `/inventory/edit/${jaId}`;
        
        // Show loading state
        this.modalBody.innerHTML = this.createLoadingHTML();
        
        // Show modal
        const modal = new bootstrap.Modal(this.modal);
        modal.show();
        
        // Fetch history data
        this.fetchHistoryData(jaId);
    }
    
    fetchHistoryData(jaId) {
        fetch(`/api/items/${jaId}/history`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.modalBody.innerHTML = this.createHistoryTimelineHTML(data);
                } else {
                    this.modalBody.innerHTML = this.createErrorHTML(data.error || 'Unable to load item history');
                }
            })
            .catch(error => {
                console.error('Error fetching item history:', error);
                this.modalBody.innerHTML = this.createErrorHTML('Network error occurred while loading history');
            });
    }
    
    createLoadingHTML() {
        return `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-3 text-muted">Loading item history...</p>
            </div>
        `;
    }
    
    createErrorHTML(errorMessage) {
        return `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i>
                <strong>Error Loading History</strong>
                <p class="mb-0 mt-2">${errorMessage}</p>
            </div>
        `;
    }
    
    createHistoryTimelineHTML(data) {
        if (!data.history || data.history.length === 0) {
            return `
                <div class="text-center py-5">
                    <div class="display-6 text-muted mb-3">
                        <i class="bi bi-clock-history"></i>
                    </div>
                    <h5>No History Found</h5>
                    <p class="text-muted">This item has no recorded history.</p>
                </div>
            `;
        }
        
        const summaryHTML = this.createHistorySummaryHTML(data);
        const timelineHTML = this.createTimelineHTML(data.history);
        
        return `
            ${summaryHTML}
            <hr>
            ${timelineHTML}
        `;
    }
    
    createHistorySummaryHTML(data) {
        return `
            <div class="row mb-3">
                <div class="col-md-4">
                    <div class="text-center">
                        <div class="h4 text-primary mb-1">${data.total_items}</div>
                        <small class="text-muted">Total Versions</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center">
                        <div class="h4 text-success mb-1">${data.active_item_count}</div>
                        <small class="text-muted">Active Items</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center">
                        <div class="h4 text-secondary mb-1">${data.total_items - data.active_item_count}</div>
                        <small class="text-muted">Inactive Items</small>
                    </div>
                </div>
            </div>
        `;
    }
    
    createTimelineHTML(history) {
        let timelineHTML = '<div class="history-timeline">';
        
        history.forEach((item, index) => {
            const isFirst = index === 0;
            const isLast = index === history.length - 1;
            
            timelineHTML += this.createTimelineItemHTML(item, isFirst, isLast);
        });
        
        timelineHTML += '</div>';
        return timelineHTML;
    }
    
    createTimelineItemHTML(item, isFirst, isLast) {
        const statusBadge = item.active 
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-secondary">Inactive</span>';
            
        const dimensions = this.formatDimensions(item.dimensions);
        const dateAdded = this.formatDate(item.date_added);
        const lastModified = this.formatDate(item.last_modified);
        
        return `
            <div class="timeline-item ${item.active ? 'timeline-item-active' : 'timeline-item-inactive'}">
                <div class="timeline-marker ${item.active ? 'timeline-marker-active' : 'timeline-marker-inactive'}">
                    <i class="bi bi-${item.active ? 'check-circle-fill' : 'circle-fill'}"></i>
                </div>
                <div class="timeline-content">
                    <div class="card">
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <h6 class="card-title mb-0">${item.display_name || item.ja_id}</h6>
                                ${statusBadge}
                            </div>
                            
                            <div class="row mb-2">
                                <div class="col-md-6">
                                    <small class="text-muted">Dimensions:</small><br>
                                    <strong>${dimensions}</strong>
                                </div>
                                <div class="col-md-6">
                                    <small class="text-muted">Dates:</small><br>
                                    <small>Added: ${dateAdded}</small><br>
                                    <small>Modified: ${lastModified}</small>
                                </div>
                            </div>
                            
                            ${item.notes ? `
                                <div class="mt-2">
                                    <small class="text-muted">Notes:</small><br>
                                    <span class="text-info">${item.notes}</span>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    formatDimensions(dimensions) {
        if (!dimensions) return 'N/A';
        
        const parts = [];
        if (dimensions.length) parts.push(`L: ${dimensions.length}"`);
        if (dimensions.width) parts.push(`W: ${dimensions.width}"`);
        if (dimensions.thickness) parts.push(`T: ${dimensions.thickness}"`);
        if (dimensions.diameter) parts.push(`⌀: ${dimensions.diameter}"`);
        if (dimensions.inner_diameter) parts.push(`ID: ${dimensions.inner_diameter}"`);
        if (dimensions.outer_diameter) parts.push(`OD: ${dimensions.outer_diameter}"`);
        
        return parts.length > 0 ? parts.join(', ') : 'N/A';
    }
    
    formatDate(dateString) {
        if (!dateString) return 'N/A';
        
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        } catch (error) {
            return dateString;
        }
    }
}

// Initialize the history viewer when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    window.historyViewer = new HistoryViewer();
});

// Global function to show item history (called from inventory list)
window.showItemHistory = function(jaId) {
    if (window.historyViewer) {
        window.historyViewer.showHistory(jaId);
    } else {
        console.error('HistoryViewer not initialized');
    }
};