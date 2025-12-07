/**
 * Item Actions Module
 *
 * Shared action handlers for inventory items.
 * These functions are called from table row action buttons.
 *
 * Note: Currently, showItemDetails, showItemHistory, and related modal functions
 * are defined globally in their respective pages and history-viewer.js.
 * This module provides a centralized location for simpler action handlers
 * and will be expanded during page migrations.
 */

/**
 * Navigate to item edit page
 *
 * @param {string} jaId - Item JA ID
 */
export function navigateToEdit(jaId) {
    window.location.href = `/inventory/edit/${jaId}`;
}

/**
 * Show duplicate item confirmation dialog
 *
 * @param {string} jaId - Item JA ID to duplicate
 */
export function showDuplicateDialog(jaId) {
    if (confirm(`Create a duplicate of item ${jaId}?`)) {
        window.location.href = `/inventory/duplicate?ja_id=${jaId}`;
    }
}

/**
 * Show move item confirmation and redirect
 *
 * @param {string} jaId - Item JA ID to move
 */
export function showMoveDialog(jaId) {
    window.location.href = `/inventory/move?ja_id=${jaId}`;
}

/**
 * Show shorten item confirmation and redirect
 *
 * @param {string} jaId - Item JA ID to shorten
 */
export function showShortenDialog(jaId) {
    window.location.href = `/inventory/shorten?ja_id=${jaId}`;
}

/**
 * Print label for item
 *
 * @param {string} jaId - Item JA ID to print label for
 */
export function printLabel(jaId) {
    window.open(`/inventory/print-label/${jaId}`, '_blank');
}

/**
 * Toggle item active/inactive status
 *
 * @param {string} jaId - Item JA ID
 * @param {boolean} activate - True to activate, false to deactivate
 * @returns {Promise<boolean>} Success status
 */
export async function toggleItemStatus(jaId, activate) {
    const action = activate ? 'activate' : 'deactivate';

    if (!confirm(`Are you sure you want to ${action} item ${jaId}?`)) {
        return false;
    }

    try {
        const response = await fetch(`/api/inventory/${jaId}/status`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ active: activate })
        });

        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }

        const data = await response.json();

        if (data.success) {
            // Reload the page to reflect changes
            window.location.reload();
            return true;
        } else {
            alert(`Error: ${data.message || 'Failed to update item status'}`);
            return false;
        }
    } catch (error) {
        console.error('Error toggling item status:', error);
        alert('An error occurred while updating the item status. Please try again.');
        return false;
    }
}

/**
 * Get CSRF token from meta tag
 *
 * @returns {string} CSRF token
 */
function getCSRFToken() {
    const token = document.querySelector('meta[name=csrf-token]');
    return token ? token.getAttribute('content') : '';
}

/**
 * Wrapper functions for global functions (showItemDetails, showItemHistory)
 * These are defined in their respective files (inventory-list.js, history-viewer.js)
 * and called via window global scope.
 */

/**
 * Show item details modal
 *
 * @param {string} jaId - Item JA ID
 */
export function showItemDetails(jaId) {
    if (typeof window.showItemDetails === 'function') {
        window.showItemDetails(jaId);
    } else {
        console.error('showItemDetails function not available');
    }
}

/**
 * Show item history modal
 *
 * @param {string} jaId - Item JA ID
 */
export function showItemHistory(jaId) {
    if (typeof window.showItemHistory === 'function') {
        window.showItemHistory(jaId);
    } else {
        console.error('showItemHistory function not available');
    }
}
