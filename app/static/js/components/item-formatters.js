/**
 * Item Formatters Module
 *
 * Shared utility functions for formatting inventory item data for display.
 * Used by both inventory list and advanced search pages.
 */

/**
 * Format full dimensions display including thread info and physical dimensions.
 *
 * @param {Object} dimensions - Dimensions object with width, thickness and
 *   wall_thickness properties. (The length property, if present, is ignored here
 *   because length is rendered in its own dedicated column via formatDimensions.)
 * @param {string} itemType - Type of item (Bar, Tube, etc.) - currently unused but kept for API compatibility
 * @param {Object} thread - Thread object with size, series, handedness properties
 * @returns {string} HTML string with formatted dimensions
 *
 * @example
 * // Round bar with thread
 * formatFullDimensions({length: 12, width: 0.5}, 'Bar', {size: '1/2-13', series: 'UNC'})
 * // Returns: '🔩1/2-13 UNC ⌀0.5"'
 *
 * @example
 * // Rectangular plate
 * formatFullDimensions({length: 24, width: 12, thickness: 0.25}, 'Plate', null)
 * // Returns: '12" × 0.25"'
 *
 * @example
 * // Round tube with wall thickness
 * formatFullDimensions({length: 96, width: 2, wall_thickness: 0.125}, 'Tube', null)
 * // Returns: '⌀2" × 0.125"'
 *
 * @note The length is intentionally excluded here; it is shown in its own
 *       dedicated Length column (see formatDimensions).
 */
export function formatFullDimensions(dimensions, itemType, thread) {
    if (!dimensions) return '<span class="text-muted">-</span>';

    const parts = [];

    // For threaded items, show thread info first
    if (thread) {
        const threadDisplay = formatThread(thread, true); // true for display with symbol
        parts.push(threadDisplay);
    }

    // Then show the physical cross-section dimensions. Length is deliberately
    // omitted (it has its own column); wall thickness is appended when present
    // and non-zero.
    const wallThickness = parseFloat(dimensions.wall_thickness);
    const hasWallThickness = !isNaN(wallThickness) && wallThickness !== 0;

    if (dimensions.width && dimensions.thickness) {
        // Rectangular: width × thickness (× wall thickness)
        let dims = `${dimensions.width}" × ${dimensions.thickness}"`;
        if (hasWallThickness) {
            dims += ` × ${dimensions.wall_thickness}"`;
        }
        parts.push(dims);
    } else if (dimensions.width) {
        // Round or Square: diameter/width (× wall thickness)
        const symbol = dimensions.width.toString().includes('⌀') ? '' : '⌀';
        let dims = `${symbol}${dimensions.width}"`;
        if (hasWallThickness) {
            dims += ` × ${dimensions.wall_thickness}"`;
        }
        parts.push(dims);
    }

    return parts.length > 0 ? parts.join(' ') : '<span class="text-muted">-</span>';
}

/**
 * Format dimensions for length-only display (used in Length column).
 *
 * @param {Object} dimensions - Dimensions object with length property
 * @param {string} itemType - Type of item - currently unused but kept for API compatibility
 * @returns {string} HTML string with formatted length
 *
 * @example
 * formatDimensions({length: 36, width: 1}, 'Bar')
 * // Returns: '36"'
 */
export function formatDimensions(dimensions, itemType = null) {
    if (!dimensions) return '<span class="text-muted">-</span>';

    // The Length column should only show the length dimension
    if (dimensions.length) {
        return `${dimensions.length}"`;
    }

    return '<span class="text-muted">-</span>';
}

/**
 * Format thread information for display.
 *
 * @param {Object} thread - Thread object with size, series, handedness properties
 * @param {boolean} includeSymbol - Whether to include 🔩 emoji symbol
 * @returns {string} Formatted thread string
 *
 * @example
 * formatThread({size: '1/4-20', series: 'UNC', handedness: 'RH'}, false)
 * // Returns: '1/4-20 UNC'
 *
 * @example
 * formatThread({size: 'M12x1.75', series: 'Metric', handedness: 'LH'}, true)
 * // Returns: '🔩M12x1.75 Metric LH'
 */
export function formatThread(thread, includeSymbol = false) {
    if (!thread) return '';
    const parts = [];
    if (thread.size) parts.push(thread.size);
    if (thread.series) parts.push(thread.series);
    if (thread.handedness && thread.handedness !== 'RH') parts.push(thread.handedness);

    const threadText = parts.join(' ');
    return includeSymbol && threadText ? `🔩${threadText}` : threadText;
}

/**
 * Escape HTML special characters to prevent XSS attacks.
 *
 * @param {string} text - Text to escape
 * @returns {string} Escaped text safe for HTML insertion
 *
 * @example
 * escapeHtml('<script>alert("XSS")</script>')
 * // Returns: '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'
 */
export function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, (m) => map[m]);
}
