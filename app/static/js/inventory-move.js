/**
 * Inventory Move JavaScript - the batch move page for inventory items.
 *
 * Everything about scanning, queueing, validating and executing lives in
 * MoveManager (move-manager.js); this supplies what is particular to items:
 * the JA ID, the item endpoints, and the batch-move request shape.
 */

class InventoryMoveManager extends MoveManager {
    get noun() { return 'item'; }
    get nounPlural() { return 'items'; }
    get idLabel() { return 'JA ID'; }
    get idExample() { return 'JA000123'; }

    isSubjectId(value) {
        // JA ID pattern: JA followed by one or more digits
        return /^JA[0-9]+$/.test(value);
    }

    /**
     * GET /api/items/{ja_id} answers 404 for an item with no active row and
     * nests the item's fields under `item`.
     */
    async lookup(jaId) {
        const response = await fetch(`/api/items/${encodeURIComponent(jaId)}`);
        if (response.status === 404) {
            return { found: false };
        }
        if (!response.ok) {
            throw new Error(`Item lookup failed: HTTP ${response.status}`);
        }
        const data = await response.json();
        if (!data.success || !data.item) {
            throw new Error(data.error || 'Item lookup failed');
        }
        return {
            found: true,
            location: data.item.location,
            subLocation: data.item.sub_location,
            label: data.item.display_name
        };
    }

    get executeUrl() { return '/api/inventory/batch-move'; }

    moveRequest(entry) {
        return {
            ja_id: entry.id,
            new_location: entry.newLocation,
            new_sub_location: entry.newSubLocation || null
        };
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.moveManager = new InventoryMoveManager();
});
