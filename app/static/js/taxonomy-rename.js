/**
 * The rename confirmation dialog for categories and tags.
 *
 * Reports what a rename will affect *before* it happens, from data the page has
 * already rendered -- every category row carries its path and product count,
 * every tag row carries its name and count. There is no fetch here and no
 * preview endpoint: the numbers are on the page, and adding a route to re-send
 * them would be machinery serving one modal.
 *
 * The server re-validates everything on submit and is authoritative. The worst a
 * stale page can produce is a refusal the operator did not expect, which is the
 * correct failure.
 */

(function () {
    'use strict';

    const SEPARATOR = '/';

    /** Canonicalize a path the way app/utils/category.py does. */
    function canonical(path) {
        return (path || '')
            .split(SEPARATOR)
            .map((segment) => segment.trim().toLowerCase())
            .filter((segment) => segment.length > 0)
            .join(SEPARATOR);
    }

    /** Whether `candidate` is `ancestor` or lives beneath it. */
    function isDescendant(candidate, ancestor) {
        if (!ancestor) {
            return false;
        }
        return candidate === ancestor
            || candidate.startsWith(ancestor + SEPARATOR);
    }

    function pluralize(count, singular, plural) {
        return `${count} ${count === 1 ? singular : (plural || singular + 's')}`;
    }

    /** Every rendered row, as {value, count} in page order.
     *
     * Scoped to `.taxonomy-row` rather than to the data attribute alone: the
     * rename button inside each row carries the same pair, and counting both
     * would double every total the dialog reports.
     */
    function readRows() {
        return Array.from(document.querySelectorAll('.taxonomy-row[data-rename-value]'))
            .map((el) => ({
                value: el.dataset.renameValue,
                count: parseInt(el.dataset.renameCount, 10) || 0,
            }));
    }

    class RenameModal {
        constructor(modalEl) {
            this.modalEl = modalEl;
            this.subject = modalEl.dataset.subject;
            this.form = document.getElementById('rename-form');
            this.oldInput = document.getElementById('rename-old-value');
            this.newInput = document.getElementById('rename-new-value');
            this.subjectName = document.getElementById('rename-subject-name');
            this.impact = document.getElementById('rename-impact');
            this.warning = document.getElementById('rename-warning');
            this.bootstrapModal = new bootstrap.Modal(modalEl);

            this.source = '';
            this.rows = [];

            this.newInput.addEventListener('input', () => this.describe());
        }

        open(value, _count) {
            this.rows = readRows();
            this.source = value;
            this.oldInput.value = value;
            this.newInput.value = value;
            this.subjectName.textContent = value;
            this.describe();
            this.bootstrapModal.show();
            this.newInput.focus();
            this.newInput.select();
        }

        describe() {
            const target = this.subject === 'category'
                ? canonical(this.newInput.value)
                : (this.newInput.value || '').trim().toLowerCase();
            const source = this.subject === 'category'
                ? canonical(this.source)
                : this.source.trim().toLowerCase();

            const report = this.subject === 'category'
                ? this.describeCategory(source, target)
                : this.describeTag(source, target);

            this.impact.textContent = report.impact;
            if (report.warning) {
                this.warning.textContent = report.warning;
                this.warning.classList.remove('d-none');
            } else {
                this.warning.classList.add('d-none');
            }
        }

        describeCategory(source, target) {
            // The subtree is the source row plus every descendant row. The
            // boundary is the separator, not the character count, so
            // "elctronics-surplus" is a different category and is not counted.
            const subtree = this.rows.filter(
                (row) => isDescendant(row.value, source)
            );
            const products = subtree.reduce((sum, row) => sum + row.count, 0);

            const impact = `${pluralize(products, 'product')} in `
                + `${pluralize(subtree.length, 'category', 'categories')} will move.`;

            if (!target) {
                return { impact, warning: 'A rename needs a new name.' };
            }
            if (target === source) {
                return {
                    impact,
                    warning: 'That is the same name -- capitalization and spacing '
                        + 'are already treated as one category.',
                };
            }
            if (isDescendant(target, source)) {
                return {
                    impact,
                    warning: `"${target}" sits inside "${source}", so the category `
                        + 'would end up inside itself. This will be refused.',
                };
            }

            // A collision is a row at or under the target that is not itself
            // part of the subtree being moved -- renaming "a" to "b" when "a/b"
            // exists is fine, because "a/b" is coming along and becomes "b/b".
            const collision = this.rows.find(
                (row) => isDescendant(row.value, target)
                    && !isDescendant(row.value, source)
            );
            if (collision) {
                return {
                    impact,
                    warning: `"${collision.value}" already exists. Categories are not `
                        + 'merged by renaming, so this will be refused.',
                };
            }

            return { impact, warning: '' };
        }

        describeTag(source, target) {
            const sourceRow = this.rows.find((row) => row.value === source);
            const count = sourceRow ? sourceRow.count : 0;

            if (!target) {
                return {
                    impact: `${pluralize(count, 'product')} carry this tag.`,
                    warning: 'A rename needs a new name.',
                };
            }
            if (target === source) {
                return {
                    impact: `${pluralize(count, 'product')} carry this tag.`,
                    warning: 'That is the same name -- tags are stored lowercase, so '
                        + 'this changes nothing.',
                };
            }

            const existing = this.rows.find((row) => row.value === target);
            if (existing) {
                return {
                    impact: `This will MERGE "${source}" (${pluralize(count, 'product')}) `
                        + `into "${target}" (${pluralize(existing.count, 'product')}). `
                        + 'One tag will remain, carrying both sets. A product already '
                        + 'carrying both keeps it once.',
                    warning: '',
                };
            }

            return {
                impact: `${pluralize(count, 'product')} will carry "${target}" instead.`,
                warning: '',
            };
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const modalEl = document.getElementById('rename-modal');
        if (!modalEl) {
            return;
        }

        const modal = new RenameModal(modalEl);
        window.taxonomyRenameModal = modal;

        document.querySelectorAll('.rename-btn').forEach((button) => {
            button.addEventListener('click', () => {
                modal.open(
                    button.dataset.renameValue,
                    parseInt(button.dataset.renameCount, 10) || 0
                );
            });
        });
    });
})();
