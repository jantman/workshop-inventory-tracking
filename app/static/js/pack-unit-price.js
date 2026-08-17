/**
 * The unit price of one item out of a pack, worked out on the capture form.
 *
 * A listing that sells a 3-pack quotes one price, and that price is what the
 * *pack* cost; a purchase records what *one* costs. This divides the first by
 * the pack size so that nobody has to reach for a calculator, and leaves the
 * result in an ordinary editable field so the operator can disagree with it.
 *
 * **The arithmetic is `BigInt`, and that is the whole point.** JavaScript's
 * only number type is an IEEE double, and Principle III has no exemption for a
 * value that is merely passing through. Both operands are parsed out of their
 * digit strings into integers, divided as integers, and formatted back to a
 * decimal string by string assembly -- so there is no `parseFloat`, no
 * `toFixed`, and no arithmetic on a `Number` anywhere in this file. The value
 * the operator ends up submitting is a string, exactly as a hand-typed price
 * is, and it becomes a `Decimal` in `_validate_price` like every other price.
 *
 * `Number` would in fact be exact here -- prices in cents are nowhere near
 * 2^53. `BigInt` is used anyway because the exactness should be *visible*
 * rather than something each reader has to re-derive.
 *
 * A plain global rather than an ES module, matching `label-count.js`:
 * `capture.html` loads plain scripts, and exposing the pure function on
 * `window` is what lets the E2E suite drive the rounding table directly
 * instead of typing into the form fifteen times.
 */

// A deliberate strict *subset* of what `_validate_price` accepts. That method
// is `Decimal(str(price).strip())`, which also takes `5.`, `.5`, `+5`, `1e2`
// and -- less comfortably -- `Infinity` and `NaN`. The direction that matters
// is that everything accepted here is accepted there, so this can never derive
// a unit price the server would then refuse. Tightening rather than matching is
// the point: none of those forms is how a person writes what they paid, and
// "$17.99" and "1,249.50", which are, are refused at both ends.
const PACK_PRICE_PATTERN = /^\d+(\.\d+)?$/;
const PACK_SIZE_PATTERN = /^\d+$/;

/**
 * The price of one unit, given what a pack cost and how many it held.
 *
 * Pure: no DOM, no side effects. Both arguments are strings and so is the
 * result -- a price is a digit string on this path from the operator's
 * keystroke to the `Decimal` the service builds.
 *
 * @param {string} paid - what the whole pack cost
 * @param {string} packSize - how many units came in it
 * @returns {{ok: true, value: string, exact: boolean}
 *          |{ok: false, error: string, field: 'pack_price'|'pack_size'}}
 *          `exact` is false when the division discarded a remainder, which is
 *          the ordinary case: 17.99 across three is 5.996666...
 */
window.unitPriceFromPack = function(paid, packSize) {
    // A non-string is not a price string. This is the guard that makes "no
    // float, ever" true rather than merely intended -- a Number handed in here
    // is refused instead of being coerced into the arithmetic below.
    const amount = typeof paid === 'string' ? paid.trim() : '';
    const size = typeof packSize === 'string' ? packSize.trim() : '';

    if (!PACK_PRICE_PATTERN.test(amount)) {
        return {
            ok: false,
            field: 'pack_price',
            error: amount
                ? `Not a price: ${amount}`
                : 'Fill in what you paid for the pack to work out the unit price',
        };
    }

    // A pack of one is not a division. The amount comes back verbatim --
    // unparsed, unrounded, unreformatted -- so 1249.50 stays 1249.50 and a
    // hand-typed 12.345 is not quietly rounded by a feature nobody invoked.
    if (size === '' || size === '1') {
        return { ok: true, value: amount, exact: true };
    }

    if (!PACK_SIZE_PATTERN.test(size) || BigInt(size) < 1n) {
        return {
            ok: false,
            field: 'pack_size',
            error: 'The pack size must be a whole number of units, one or more',
        };
    }

    // Integers from here down. `fraction.length` is the scale of the amount
    // paid, and the factor of 100 is what makes the quotient come out in
    // cents -- the precision a purchase price is recorded at.
    const [whole, fraction = ''] = amount.split('.');
    const cents = BigInt(whole + fraction) * 100n;
    const divisor = BigInt(size) * 10n ** BigInt(fraction.length);

    let quotient = cents / divisor;
    const remainder = cents % divisor;
    // Half away from zero. Both operands are non-negative by the patterns
    // above, so that is plain half-up and there is no sign to handle.
    if (2n * remainder >= divisor) {
        quotient += 1n;
    }

    return {
        ok: true,
        value: `${quotient / 100n}.${String(quotient % 100n).padStart(2, '0')}`,
        exact: remainder === 0n,
    };
};

document.addEventListener('DOMContentLoaded', function() {
    const paidField = document.getElementById('pack_price');
    const sizeField = document.getElementById('pack_size');
    const priceField = document.getElementById('unit_price');
    const inexactNote = document.getElementById('unit-price-inexact');
    const errorNote = document.getElementById('unit-price-error');

    // Inert on every page that is not the capture form.
    if (!paidField || !sizeField || !priceField || !inexactNote || !errorNote) {
        return;
    }

    function show(element, text) {
        element.textContent = text;
        element.classList.remove('d-none');
    }

    function hide(element) {
        element.classList.add('d-none');
    }

    /**
     * Recompute, and say what came of it.
     *
     * `editing` is the difference between the operator having just typed
     * something and the page having merely loaded, and it governs the two
     * things that would be wrong to do on load:
     *
     * - **Writing the field.** A re-render -- the duplicate question, the
     *   recycled-item-number question -- may be carrying a unit price the
     *   operator typed over the derived one before the form came back. Writing
     *   on load would discard it without a trace.
     * - **Showing the error.** An error is feedback on an edit. A capture page
     *   nobody has typed into yet has an empty pack price, and telling the
     *   operator off for that before they have done anything is noise.
     *
     * The inexactness note is shown either way, so that a rounded price still
     * explains itself on the far side of a question (FR-008, FR-012).
     */
    function recompute(editing) {
        const result = window.unitPriceFromPack(paidField.value, sizeField.value);

        if (!result.ok) {
            if (editing) {
                show(errorNote, result.error);
            }
            hide(inexactNote);
            return;
        }

        hide(errorNote);
        if (editing) {
            priceField.value = result.value;
        }

        if (result.exact) {
            hide(inexactNote);
        } else {
            show(inexactNote, `Rounded to the cent: ${sizeField.value.trim()} at `
                + `${result.value} each do not add back up to the `
                + `${paidField.value.trim()} you paid.`);
        }
    }

    // Only the two pack fields. Nothing listens on #unit_price: an operator
    // typing there is overruling the derivation, and a derivation that
    // recomputed itself back over the top of that would be useless (FR-004).
    paidField.addEventListener('input', () => recompute(true));
    sizeField.addEventListener('input', () => recompute(true));

    recompute(false);
});
