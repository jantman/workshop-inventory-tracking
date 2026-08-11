/**
 * Dimension Requirements - shared by the Add Item and Edit Item forms.
 *
 * The rules themselves are not stated here. They come from app/taxonomy.py,
 * rendered into the page as a JSON constant by the view. If a rule needs to
 * change, that module is the only file that has to.
 *
 * This module owns four behaviours and nothing else:
 *   1. the `required` attribute and the `*` mark on each field
 *   2. the Width -> Diameter label for round shapes
 *   3. filtering the Shape options to the ones the Type can take
 *   4. nothing else - it does not submit, does not fetch, and knows nothing
 *      about threading sections, carry-forward, barcode scanning or photos
 */

class DimensionRequirements {
    // Every field a rule can name. Reset covers all of them so a field never
    // keeps a requirement belonging to a type the operator has moved away from.
    static FIELDS = ['length', 'width', 'thickness', 'wall_thickness',
                     'thread_series', 'thread_size'];

    /**
     * @param {Object} requirements - {Type: {Shape: [field, ...]}}. Defaults to
     *   the table the view rendered into #type-shape-requirements.
     */
    constructor(requirements = null) {
        this.requirements = requirements || DimensionRequirements.readTable();
        this.typeSelect = document.getElementById('item_type');
        this.shapeSelect = document.getElementById('shape');
        this.widthLabel = document.getElementById('width-label');
    }

    /** Read the table the server rendered into the page. */
    static readTable() {
        const el = document.getElementById('type-shape-requirements');
        if (!el) {
            console.warn('DimensionRequirements: no rules table in the page');
            return {};
        }
        try {
            return JSON.parse(el.textContent);
        } catch (error) {
            console.error('DimensionRequirements: unparseable rules table', error);
            return {};
        }
    }

    /**
     * Wire the module to the Type and Shape selects and apply it once, so the
     * form is correct on load as well as after a change.
     */
    init() {
        if (this.typeSelect) {
            this.typeSelect.addEventListener('change', () => {
                this.updateShapeOptions();
                this.apply();
            });
        }
        if (this.shapeSelect) {
            this.shapeSelect.addEventListener('change', () => this.apply());
        }
        this.updateShapeOptions();
        this.apply();
        return this;
    }

    /** The fields the current Type and Shape require. */
    requiredFields() {
        const type = this.typeSelect ? this.typeSelect.value : '';
        const shape = this.shapeSelect ? this.shapeSelect.value : '';
        if (!type || !shape || !this.requirements[type]) {
            return [];
        }
        return this.requirements[type][shape] || [];
    }

    /** Apply requirement marks, enforcement, and the width label. */
    apply() {
        DimensionRequirements.FIELDS.forEach(field => {
            this._setRequired(field, false);
        });
        this.requiredFields().forEach(field => {
            this._setRequired(field, true);
        });
        this.updateWidthLabel();
    }

    _setRequired(field, isRequired) {
        const input = document.getElementById(field);
        if (!input) return;

        if (isRequired) {
            // Valueless, matching how the templates spell it on the fields they
            // mark statically -- so `to_have_attribute('required', '')` means the
            // same thing across the suite.
            input.setAttribute('required', '');
        } else {
            input.removeAttribute('required');
            input.classList.remove('is-invalid');
        }

        // The mark sits beside the label, in the field's column wrapper.
        const indicator = input.closest('.mb-3')?.querySelector('.dimension-required');
        if (indicator) {
            indicator.style.display = isRequired ? 'inline' : 'none';
        }
    }

    /** Width is the diameter of a round item, and is labelled that way. */
    updateWidthLabel() {
        if (!this.widthLabel || !this.shapeSelect) return;
        this.widthLabel.textContent =
            this.shapeSelect.value === 'Round' ? 'Diameter' : 'Width';
    }

    /**
     * Hide the shapes the current Type has no rule for, clearing the selection
     * if it has become one of them.
     */
    updateShapeOptions() {
        if (!this.typeSelect || !this.shapeSelect) return;

        const selectedType = this.typeSelect.value;
        const options = this.shapeSelect.querySelectorAll('option');

        options.forEach(option => {
            if (option.value !== '') {
                option.style.display = 'block';
            }
        });

        if (!selectedType || !this.requirements[selectedType]) return;

        const validShapes = Object.keys(this.requirements[selectedType]);
        options.forEach(option => {
            if (option.value !== '' && !validShapes.includes(option.value)) {
                option.style.display = 'none';
                if (option.selected) {
                    this.shapeSelect.value = '';
                }
            }
        });
    }
}

window.DimensionRequirements = DimensionRequirements;
