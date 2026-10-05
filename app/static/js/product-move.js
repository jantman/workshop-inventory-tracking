/**
 * Product Move JavaScript - the batch move page for products.
 *
 * Everything about scanning, queueing, validating and executing lives in
 * MoveManager (move-manager.js); this supplies what is particular to products:
 * the WIT internal code printed on their labels, the product endpoints, and
 * the batch-move request shape.
 */

// app/utils/internal_id.py: WIT plus ten Crockford base32 characters.
const PRODUCT_CODE = /^WIT[0-9A-HJKMNP-TV-Z]{10}$/;

class ProductMoveManager extends MoveManager {
    get noun() { return 'product'; }
    get nounPlural() { return 'products'; }
    get idLabel() { return 'Product Code'; }
    get idExample() { return 'WIT0123456789'; }

    /**
     * Matched upper-cased: Crockford base32 is upper-case only, so folding a
     * code typed in lower case cannot reach a different product -- the same
     * reasoning as the /products/<code> route.
     */
    isSubjectId(value) {
        return PRODUCT_CODE.test(value.toUpperCase());
    }

    normalizeId(value) {
        return value.toUpperCase();
    }

    /**
     * An inventory item's JA label. Without this it would fall through to
     * "sub-location" after a location and quietly become one.
     */
    isForeignId(value) {
        return /^JA[0-9]+$/.test(value);
    }

    foreignIdMessage(value) {
        return `${value} is an inventory item, not a product. ` +
            'Move inventory items on the Move Items page.';
    }

    async lookup(code) {
        const response = await fetch(`/api/products/by-code/${encodeURIComponent(code)}`);
        if (response.status === 404) {
            return { found: false };
        }
        if (!response.ok) {
            throw new Error(`Product lookup failed: HTTP ${response.status}`);
        }
        const data = await response.json();
        if (!data.success || !data.product) {
            throw new Error(data.error || 'Product lookup failed');
        }
        return {
            found: true,
            location: data.product.location,
            subLocation: data.product.sub_location,
            label: data.product.description
        };
    }

    get executeUrl() { return '/api/products/batch-move'; }

    moveRequest(entry) {
        return {
            code: entry.id,
            new_location: entry.newLocation,
            new_sub_location: entry.newSubLocation || null
        };
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.moveManager = new ProductMoveManager();
});
