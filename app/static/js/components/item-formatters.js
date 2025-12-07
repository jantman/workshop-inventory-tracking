/**
 * Item Formatters Module
 *
 * Shared utility functions for formatting inventory item data for display.
 * Used by both inventory list and advanced search pages.
 */

/**
 * Format full dimensions display including thread info and physical dimensions.
 *
 * @param {Object} dimensions - Dimensions object with length, width, thickness properties
 * @param {string} itemType - Type of item (Bar, Tube, etc.) - currently unused but kept for API compatibility
 * @param {Object} thread - Thread object with size, series, handedness properties
 * @returns {string} HTML string with formatted dimensions
 *
 * @example
 * // Round bar with thread
 * formatFullDimensions({length: 12, width: 0.5}, 'Bar', {size: '1/2-13', series: 'UNC'})
 * // Returns: '🔩1/2-13 UNC ⌀0.5" × 12"'
 *
 * @example
 * // Rectangular plate
 * formatFullDimensions({length: 24, width: 12, thickness: 0.25}, 'Plate', null)
 * // Returns: '12" × 0.25" × 24"'
 */
export function formatFullDimensions(dimensions, itemType, thread) {
    if (!dimensions) return '<span class="text-muted">-</span>';

    const parts = [];

    // For threaded items, show thread info first
    if (thread) {
        const threadDisplay = formatThread(thread, true); // true for display with symbol
        parts.push(threadDisplay);
    }

    // Then show physical dimensions
    if (dimensions.length) {
        if (dimensions.width && dimensions.thickness) {
            // Rectangular: width × thickness × length
            parts.push(`${dimensions.width}" × ${dimensions.thickness}" × ${dimensions.length}"`);
        } else if (dimensions.width) {
            // Round or Square: diameter/width × length
            const symbol = dimensions.width.toString().includes('⌀') ? '' : '⌀';
            parts.push(`${symbol}${dimensions.width}" × ${dimensions.length}"`);
        } else {
            // Just length
            parts.push(`${dimensions.length}"`);
        }
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
