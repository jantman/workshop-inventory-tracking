/**
 * The units and unit price one order line's pack implies, on the review.
 *
 * An Amazon order page counts *listings* and a listing can be a pack of 100
 * screws. The review asks how many came in one, and this keeps that row's
 * Units and Unit price in step with the answer so nobody reaches for a
 * calculator (feature 046, issue #137).
 *
 * **The arithmetic is not repeated here.** The price division is
 * `window.unitPriceFromPack` from `pack-unit-price.js`, unchanged: it parses
 * digit strings into `BigInt`, divides as integers, and assembles the decimal
 * string back by hand, specifically so that Principle III holds for a value
 * merely passing through the browser. Writing a second price division in
 * JavaScript is the exact mistake that file exists to prevent. The quantity is
 * integer multiplication and needs no helper.
 *
 * **This script is an ergonomic aid, not part of the write path.** The server
 * performs the same conversion and decides for itself whether a submitted
 * number was overridden, by reconstructing what it rendered -- see
 * `specs/046-pack-quantity-order-lines/contracts/pack-conversion.md` §2. With
 * this script and without it, the same submission records the same purchase.
 * That is deliberate: a pack size entered in a browser with JavaScript
 * disabled must not silently record one item at the price of a whole pack,
 * which is the defect the feature exists to fix.
 *
 * Two rules are carried over verbatim from `pack-unit-price.js`, and both are
 * load-bearing:
 *
 * - **Write a derived field only once the operator has typed in the pack
 *   field, never on load.** A re-render after a refused submission may be
 *   carrying values the operator typed over the derived ones, and writing on
 *   load would discard them without a trace. The server supplies the initial
 *   derived values instead.
 * - **Nothing listens on the derived fields themselves.** An operator typing
 *   in Units or Unit price is overruling the derivation, and a derivation that
 *   recomputed over the top of that would be useless.
 *
 * A separate file from `pack-unit-price.js` because that one binds to single
 * `id`s on the capture form and a review has one row per line. A plain global
 * rather than an ES module, matching the rest of this directory. Inert on
 * every page without the hooks.
 */

document.addEventListener('DOMContentLoaded', function () {
    const table = document.getElementById('order-lines');

    // Inert on every page that is not an order review, and on the reviews of
    // the two vendors that state their own packs or none.
    if (!table || typeof window.unitPriceFromPack !== 'function') {
        return;
    }

    /**
     * The row a pack-size input belongs to, and the three fields it drives.
     *
     * Scoped to the row rather than looked up by name, because **two lines of
     * one order can carry the same item** and a selector that matched by item
     * would drive both from one input. The same trap `form_key` closes on the
     * server.
     */
    function rowOf(packField) {
        const row = packField.closest('tr.order-line');
        if (!row) {
            return null;
        }
        return {
            quantity: row.querySelector('.line-quantity'),
            unitPrice: row.querySelector('.line-unit-price'),
            converted: row.querySelector('.line-converted'),
            arithmetic: row.querySelector('.conversion-arithmetic'),
            suggested: row.querySelector('.pack-size-suggested'),
        };
    }

    /**
     * What the vendor charged for this row, as digit strings.
     *
     * Read off the row's own markup rather than re-derived from the fields the
     * operator may have edited: `data-packs` and `data-pack-price` are what
     * Amazon said, and dividing an already-divided price would compound.
     */
    function stated(packField) {
        const row = packField.closest('tr.order-line');
        return {
            packs: row.getAttribute('data-packs') || '',
            packPrice: row.getAttribute('data-pack-price') || '',
        };
    }

    function recompute(packField) {
        const fields = rowOf(packField);
        if (!fields) {
            return;
        }

        const source = stated(packField);

        // **A cleared field is "this is not a pack", not "leave it as it
        // was".** Clearing has to put the line back to what the vendor stated
        // and drop the conversion marking, or the operator is looking at a
        // converted quantity the server is about to record as unconverted.
        // `unitPriceFromPack` already treats an empty size this way.
        const size = packField.value.trim() || '1';

        // A pack size the server would refuse changes nothing here. The
        // refusal is the server's to give, with the line named; guessing at a
        // replacement value in the browser would hide it.
        if (!/^\d+$/.test(size) || BigInt(size) < 1n) {
            return;
        }

        // The quantity, in items. Integers throughout -- no `parseFloat`.
        if (fields.quantity && /^\d+$/.test(source.packs)) {
            fields.quantity.value = String(BigInt(source.packs) * BigInt(size));
        }

        // The price of one item, through the exact helper.
        if (fields.unitPrice && source.packPrice) {
            const result = window.unitPriceFromPack(source.packPrice, size);
            if (result.ok) {
                fields.unitPrice.value = result.value;
            }
        }

        // The marking follows the number it explains. A pack size the operator
        // has touched is no longer a guess, whatever it now holds.
        if (fields.suggested) {
            fields.suggested.remove();
        }
        if (fields.arithmetic && /^\d+$/.test(source.packs)) {
            fields.arithmetic.textContent = source.packs + ' × ' + size;
        }
        if (fields.converted) {
            fields.converted.classList.toggle('d-none', BigInt(size) < 2n);
        }
    }

    table.querySelectorAll('.line-pack-size').forEach(function (packField) {
        packField.addEventListener('input', function () {
            recompute(packField);
        });
    });
});
