/**
 * Move Manager - the scan-driven batch move page, shared by items and products.
 *
 * Handles barcode scanning, move queue management, validation, and execution.
 * Everything here is the same whatever is being moved; what differs -- how the
 * thing is recognized, looked up, labelled and saved -- is supplied by a
 * subclass: InventoryMoveManager (inventory-move.js) for JA-ID items and
 * ProductMoveManager (product-move.js) for products. The members a subclass
 * provides are listed in specs/057-product-location-move/contracts/move-manager.md
 * and stubbed at the bottom of this class.
 *
 * "Subject" below means the thing being moved: an item or a product.
 */

class MoveManager {
    constructor() {
        this.moveQueue = [];
        // State machine: 'bulk_location', 'id', 'location', or
        // 'id_or_sub_location'.
        // 'id_or_sub_location' means we've received a location and are waiting for
        // either the next subject ID (no sub-location) or a sub-location string.
        // 'bulk_location' is the entry state when the page was handed a group of
        // preselected subjects: the next input is the destination for all of them.
        this.currentExpectedInput = 'id';
        this.currentId = null;
        this.currentLocation = null;
        this.scannerTimeout = null;
        this.scannerDelay = 100; // ms delay to detect scanner input
        this.manualEntryMode = false;

        // Preselected items that have arrived but have no destination yet. A
        // pending move is not a queued move: it has nothing to validate, so it
        // is never counted in the queue badge and never executed. Giving the
        // group a destination is the whole of the bulk_location transition.
        this.pendingMoves = [];
        // Resolves once every pending move's current location is established.
        this.pendingMovesReady = Promise.resolve();
        // The IDs of the group most recently queued together, so a
        // sub-location scanned afterwards applies to all of them (FR-009)
        // rather than only to the last.
        //
        // Identity, not queue position. Positions go stale the moment anything
        // is removed from the queue -- the per-row Remove button splices
        // moveQueue and shifts every row after it -- and an index kept across
        // that either writes the sub-location onto the wrong item or onto
        // nothing at all. Keying by ID cannot go stale: a removed row simply
        // stops matching.
        this.bulkGroupIds = [];
        // Set when handleBarcodeInput() consumed >>DONE<< and emptied the field.
        // The scanner's Enter is still on its way and would otherwise reach
        // processInput() with nothing to process (FR-016).
        this.doneCodeConsumed = false;

        this.initializeElements();
        this.bindEvents();
        this.initializePreselection();
        this.updateUI();

        console.log(`${this.constructor.name} initialized`);
    }

    /**
     * Adopt the items this page was handed, if it was handed any.
     *
     * The list is server-rendered into #preselected-section, so the state is
     * set synchronously here and a scan arriving immediately is handled
     * correctly. Each subject's current location is established afterwards
     * through lookup() -- the same one finalizeCurrentMove() uses, reused rather
     * than batched (026 contracts/handoff.md section 5). The promise
     * is kept so the bulk_location transition can wait for it rather than
     * queueing rows whose current location has not arrived yet.
     */
    initializePreselection() {
        const section = document.getElementById('preselected-section');
        if (!section) {
            return;
        }

        let ids = [];
        try {
            ids = JSON.parse(section.dataset.ids || '[]');
        } catch (error) {
            console.error('Could not read preselected items:', error);
            return;
        }

        if (ids.length === 0) {
            // Everything handed over was rejected. The page says so in its own
            // markup; here it simply behaves as an ordinary scanning page.
            return;
        }

        this.pendingMoves = ids.map(id => ({
            id: id,
            currentLocation: 'Unknown',
            currentSubLocation: null
        }));
        this.currentExpectedInput = 'bulk_location';
        this.updateStatus(this.bulkPrompt());
        this.updateScannerStatus('Waiting for Destination');

        this.pendingMovesReady = Promise.all(
            this.pendingMoves.map(async pending => {
                const current = await this.fetchCurrentLocation(pending.id);
                pending.currentLocation = current.location;
                pending.currentSubLocation = current.subLocation;
                pending.itemInfo = current.label;
                this.renderPendingMove(pending);
            })
        );
    }

    /** The prompt for the group's destination, worded for one item or many. */
    bulkPrompt() {
        const count = this.pendingMoves.length;
        return count === 1
            ? `${this.pendingMoves[0].id} is awaiting a destination. Scan or enter the location it is going to.`
            : `${count} ${this.nounPlural} are awaiting a destination. Scan or enter the location all ${count} are going to.`;
    }

    /** Take the arrival card off the page; the subjects are no longer pending. */
    discardPreselectedSection() {
        const section = document.getElementById('preselected-section');
        if (section) {
            section.remove();
        }
    }

    /** Fill in one pending row's current location, once it is known. */
    renderPendingMove(pending) {
        const row = document.querySelector(`#pending-moves tr[data-id="${pending.id}"]`);
        if (!row) {
            return;
        }
        const label = row.querySelector('.pending-label');
        if (label && pending.itemInfo) {
            label.textContent = pending.itemInfo;
        }
        row.querySelector('.pending-current-location').textContent =
            pending.currentLocation || 'None';
        row.querySelector('.pending-current-sub-location').textContent =
            pending.currentSubLocation || 'None';
    }
    
    initializeElements() {
        // Input elements
        this.barcodeInput = document.getElementById('barcode-input');
        this.manualEntryCheckbox = document.getElementById('manual-entry-mode');
        
        // Status elements
        this.scannerStatus = document.getElementById('scanner-status');
        this.inputStatus = document.getElementById('input-status');
        this.statusText = document.getElementById('status-text');
        this.queueCount = document.getElementById('queue-count');
        
        // Queue display elements
        this.queueEmpty = document.getElementById('move-queue-empty');
        this.queueList = document.getElementById('move-queue-list');
        this.queueItems = document.getElementById('queue-items');
        
        // Button elements
        this.clearAllBtn = document.getElementById('clear-all-btn');
        this.clearQueueBtn = document.getElementById('clear-queue-btn');
        this.validateBtn = document.getElementById('validate-btn');
        this.executeMoveBtn = document.getElementById('execute-moves-btn');
        this.validateHint = document.getElementById('validate-hint');
        
        // Alert elements
        this.formAlerts = document.getElementById('form-alerts');
        this.validationSection = document.getElementById('validation-section');
        this.validationResults = document.getElementById('validation-results');
    }
    
    /**
     * Location Pattern Validation Functions
     *
     * These functions implement the centralized location pattern validation logic
     * matching the backend implementation in app/utils/location_validator.py
     *
     * Pattern Rules (applied in order):
     * 1. Subject ID: isSubjectId(), supplied by the subclass
     * 2. Foreign ID: isForeignId(), an ID belonging to the *other* move page
     * 3. Location Patterns:
     *    - Metal stock storage: ^M[0-9]+.*
     *    - Threaded stock storage: ^T-?[0-9]+.*
     *    - General storage: exact match "Other"
     * 4. Sub-location: Any string NOT matching the above
     */

    isLocation(value) {
        if (!value || value.length === 0) {
            return false;
        }

        // Metal stock storage pattern
        if (/^M[0-9]+.*/.test(value)) {
            return true;
        }

        // Threaded stock storage pattern (T + optional dash + digits)
        if (/^T-?[0-9]+.*/.test(value)) {
            return true;
        }

        // Exact match for "Other" (case-sensitive)
        if (value === 'Other') {
            return true;
        }

        return false;
    }

    classifyInput(value) {
        // Classify input as 'id', 'foreign', 'location', or 'sub_location'
        if (this.isSubjectId(value)) {
            return 'id';
        } else if (this.isForeignId(value)) {
            return 'foreign';
        } else if (this.isLocation(value)) {
            return 'location';
        } else {
            return 'sub_location';
        }
    }

    bindEvents() {
        // Barcode input handling
        this.barcodeInput.addEventListener('input', (e) => this.handleBarcodeInput(e));
        this.barcodeInput.addEventListener('keydown', (e) => this.handleKeyDown(e));

        // Manual entry mode toggle
        this.manualEntryCheckbox.addEventListener('change', (e) => {
            this.manualEntryMode = e.target.checked;
            this.updateScannerStatus();
        });

        // Button events
        this.clearAllBtn.addEventListener('click', () => this.clearAll());
        this.clearQueueBtn.addEventListener('click', () => this.clearQueue());
        this.validateBtn.addEventListener('click', () => this.validateMoves());
        this.executeMoveBtn.addEventListener('click', () => this.executeMoves());

        // Focus on barcode input when page loads
        this.barcodeInput.focus();
    }
    
    handleKeyDown(e) {
        // Handle Enter key for both manual and automated modes
        if (e.key === 'Enter') {
            e.preventDefault();
            
            // Clear any pending scanner timeout since Enter takes precedence
            if (this.scannerTimeout) {
                clearTimeout(this.scannerTimeout);
                this.scannerTimeout = null;
            }

            if (this.doneCodeConsumed) {
                // handleBarcodeInput() already consumed >>DONE<< and emptied the
                // field; this Enter is the scanner's terminator for that same
                // scan. Letting it through raises 'Please enter a value' against
                // an empty field -- and because alerts used to overwrite each
                // other, that meaningless warning was the last thing left on
                // screen after >>DONE<<, replacing the message that explained
                // what had actually happened. See FR-016 and verification.md.
                this.doneCodeConsumed = false;
                return;
            }

            this.processInput();
        }
    }
    
    handleBarcodeInput(e) {
        const value = e.target.value.trim();
        
        if (!value) return;
        
        // Clear any existing timeout
        if (this.scannerTimeout) {
            clearTimeout(this.scannerTimeout);
        }
        
        // Check for >>DONE<< immediately (special case for ending scanning session)
        if (this.isDoneCode(value)) {
            this.clearInput();  // Clear input BEFORE handling to prevent double-processing
            this.doneCodeConsumed = true;  // swallow the scanner's Enter (FR-016)
            this.handleDoneCode();
            return;
        }

        this.doneCodeConsumed = false;

        // For barcode scanners that automatically add newline, set a short timeout
        // This allows the scanner's newline to be processed by handleKeyDown
        if (!this.manualEntryMode) {
            this.scannerTimeout = setTimeout(() => {
                // If we reach here, the scanner didn't send Enter, so process directly
                this.processInput();
            }, this.scannerDelay);
        }
        
        // In manual entry mode, only process on Enter key (handled in handleKeyDown)
    }
    
    processInput() {
        const value = this.barcodeInput.value.trim();

        console.log(`processInput() called: value="${value}", currentExpectedInput="${this.currentExpectedInput}"`);

        if (!value) {
            this.showAlert('Please enter a value', 'warning');
            return;
        }

        // Check for done code
        if (this.isDoneCode(value)) {
            console.log('processInput(): Detected >>DONE<< code');
            this.handleDoneCode();
            return;
        }

        // Classify the input
        const inputType = this.classifyInput(value);
        console.log(`processInput(): Classified "${value}" as type: ${inputType}`);

        // An ID belonging to the other move page is never a sub-location, a
        // location or a subject here, whatever the machine is waiting for.
        if (inputType === 'foreign') {
            this.showAlert(this.foreignIdMessage(value), 'warning');
            this.clearInput();
            return;
        }

        // State machine for input processing
        if (this.currentExpectedInput === 'bulk_location') {
            // The page was handed a group of items. The next input is the
            // destination for all of them, and nothing else will do (FR-012).
            if (inputType === 'location') {
                console.log(`processInput(): State=bulk_location, handling group destination: ${value}`);
                this.handleBulkLocationInput(value);
            } else {
                const count = this.pendingMoves.length;
                const noun = count === 1 ? `${this.noun} is` : `${this.nounPlural} are`;
                this.showAlert(
                    `${count} ${noun} waiting for a destination, and ${inputType === 'id' ? `a ${this.idLabel}` : 'a sub-location'} is not one. ` +
                    'Please scan the location they are going to (M*, T*, or Other).',
                    'warning');
                this.clearInput();
            }
        } else if (this.currentExpectedInput === 'id') {
            // Expecting a subject ID
            if (inputType === 'id') {
                console.log(`processInput(): State=id, handling ${this.idLabel}: ${value}`);
                this.handleIdInput(this.normalizeId(value));
            } else {
                this.showAlert(`Expected ${this.idLabel} but received ${inputType}. Please scan a ${this.idLabel} (format: ${this.idExample})`, 'warning');
                this.clearInput();
            }
        } else if (this.currentExpectedInput === 'location') {
            // Expecting a location
            if (inputType === 'location') {
                console.log(`processInput(): State=location, handling location: ${value}`);
                this.handleLocationInput(value);
            } else if (inputType === 'id') {
                // An ID here unambiguously means the previous subject's location
                // was missed, so the machine resolves onto the new item rather
                // than bouncing. This used to warn and leave the state at
                // 'location', which wedged the page: every subsequent JA-ID scan
                // was refused, nothing was ever queued, and >>DONE<< then
                // reported an empty queue. That is issue #107 -- see
                // specs/026-fix-bulk-move-handoff/verification.md for the trace.
                const abandoned = this.currentId;
                const id = this.normalizeId(value);
                if (this.handleIdInput(id)) {
                    this.showAlert(
                        `No location was scanned for ${abandoned}, so it was not queued. ` +
                        `Now waiting for the location for ${id}.`,
                        'warning');
                }
            } else {
                this.showAlert('Expected location but received sub-location. Please scan a valid location (M*, T*, or Other).', 'warning');
                this.clearInput();
            }
        } else if (this.currentExpectedInput === 'id_or_sub_location') {
            // After scanning location, we can receive either:
            // - A subject ID (meaning no sub-location, start next move)
            // - A sub-location (meaning we have a sub-location for current move)
            // - A location would be an error
            console.log(`processInput(): State=id_or_sub_location, inputType=${inputType}`);
            if (inputType === 'id') {
                // No sub-location for current move, finalize it and start new move
                // Save current values before they get overwritten by handleIdInput
                const idToFinalize = this.currentId;
                const locationToFinalize = this.currentLocation;
                console.log(`processInput(): Finalizing previous move: ${idToFinalize} → ${locationToFinalize}`);

                // Start new move first (synchronous state update)
                this.handleIdInput(this.normalizeId(value));

                // Then finalize previous move (async operation). There may be
                // no previous move to finalize: this state is also where a
                // freshly queued preselected group leaves the machine, and
                // those rows are already in the queue. Without this guard the
                // fallback inside finalizeCurrentMove() would pick up the ID
                // handleIdInput() has just set and queue the *new* subject
                // against the *group's* destination.
                if (idToFinalize) {
                    this.finalizeCurrentMove(null, idToFinalize, locationToFinalize);
                }
            } else if (inputType === 'sub_location') {
                // Sub-location for current move
                console.log(`processInput(): Handling sub-location: ${value}`);
                this.handleSubLocationInput(value);
            } else if (inputType === 'location') {
                this.showAlert(`Received two locations in a row. Did you forget to scan a ${this.idLabel}?`, 'warning');
                this.clearInput();
            }
        }
    }
    
    isDoneCode(value) {
        // Only match the exact >>DONE<< string to prevent partial matches
        // during character-by-character typing
        return value === '>>DONE<<';
    }
    
    /**
     * Start a new move for `id`.
     *
     * Returns whether the machine actually advanced. Callers that report on the
     * transition need to know: a rejected duplicate leaves the state exactly as
     * it was, and a message describing a transition that did not happen is
     * worse than no message.
     */
    handleIdInput(id) {
        console.log(`handleIdInput() called: id=${id}`);

        // Check if this ID is already in queue
        if (this.moveQueue.some(item => item.id === id)) {
            this.showAlert(`${this.nounTitle} ${id} is already in the move queue`, 'warning');
            this.clearInput();
            return false;
        }

        // Scanning a new subject ends any preselected group: a sub-location from
        // here belongs to this subject, not to the group that came before it.
        this.bulkGroupIds = [];

        // Store the ID and wait for location
        this.currentId = id;
        this.currentExpectedInput = 'location';
        console.log(`handleIdInput(): Set currentId=${this.currentId}, currentExpectedInput=${this.currentExpectedInput}`);
        this.clearInput();
        this.updateStatus(`${this.idLabel} ${id} scanned. Now scan or enter the location (M*, T*, or Other).`);
        this.updateScannerStatus('Waiting for Location');
        this.updateButtonStates();
        return true;
    }

    /**
     * Apply one destination to every preselected subject, queueing them all.
     *
     * FR-008. The group becomes N ordinary queued moves, indistinguishable from
     * scanned ones, which is why validation and execution need no changes at all
     * (FR-013): they are the same objects, not a parallel kind of thing.
     */
    async handleBulkLocationInput(location) {
        this.clearInput();

        // Each pending row's current location is established by a fetch started
        // on load. Queueing before those land would show 'Unknown' for subjects
        // whose location is perfectly well known (FR-010).
        await this.pendingMovesReady;

        const timestamp = new Date().toISOString();
        this.pendingMoves.forEach(pending => {
            this.moveQueue.push({
                id: pending.id,
                itemInfo: pending.itemInfo,
                newLocation: location,
                newSubLocation: null,
                currentLocation: pending.currentLocation,
                currentSubLocation: pending.currentSubLocation,
                status: 'pending',
                timestamp: timestamp
            });
        });

        const count = this.pendingMoves.length;
        this.bulkGroupIds = this.pendingMoves.map(pending => pending.id);
        this.pendingMoves = [];

        this.discardPreselectedSection();

        // The group is queued, so the machine rejoins the ordinary flow: a
        // sub-location from here applies to the whole group, and an ID starts
        // hand scanning into the same batch (FR-011).
        this.currentId = null;
        this.currentLocation = location;
        this.currentExpectedInput = 'id_or_sub_location';
        this.updateStatus(
            `${count} ${this.nounFor(count)} queued for ${location}. ` +
            `Scan the next ${this.idLabel}, or enter a sub-location to apply to all of them.`);
        this.updateScannerStatus(`Waiting for ${this.idLabel} or Sub-Location`);
        this.updateUI();

        console.log(`handleBulkLocationInput(): queued ${count} preselected ${this.nounPlural} for ${location}`);
    }

    handleLocationInput(location) {
        console.log(`handleLocationInput() called: location=${location}`);

        if (!location || location.length < 1) {
            this.showAlert('Location cannot be empty', 'warning');
            return;
        }

        // Store the location and wait for either an ID or sub-location
        this.currentLocation = location;
        this.currentExpectedInput = 'id_or_sub_location';
        console.log(`handleLocationInput(): Set currentLocation=${this.currentLocation}, currentExpectedInput=${this.currentExpectedInput}`);
        this.clearInput();
        this.updateStatus(`Location ${location} scanned. Now scan the next ${this.idLabel} or enter a sub-location (optional).`);
        this.updateScannerStatus(`Waiting for ${this.idLabel} or Sub-Location`);
    }

    handleSubLocationInput(subLocation) {
        if (this.bulkGroupIds.length > 0) {
            // FR-009: the sub-location belongs to the group that was just
            // queued, not to whichever of its rows happens to be last.
            this.applySubLocationToGroup(subLocation);
            this.clearInput();
            return;
        }

        // Finalize current move with sub-location
        this.finalizeCurrentMove(subLocation);
        this.clearInput();
    }

    /**
     * Write a sub-location onto every row of the group most recently queued.
     *
     * These rows are already in the queue, so nothing is added and the queue
     * count does not move -- the state reset below is what happens last, and is
     * therefore what a test can wait on.
     *
     * Rows are matched by ID rather than by remembered position, because the
     * queue can have shrunk since the group was queued: removeFromQueue()
     * splices moveQueue and shifts everything after the removed row. Matching by
     * identity means a removed row simply is not found, instead of the write
     * landing on whichever item slid into its index.
     *
     * The state is reset whatever is found, including nothing. Leaving the
     * machine in a state no input can move it out of is the failure class this
     * feature exists to close (#107), and an emptied group is not a reason to
     * reintroduce it.
     */
    applySubLocationToGroup(subLocation) {
        const group = new Set(this.bulkGroupIds);
        this.bulkGroupIds = [];

        const applied = this.moveQueue.filter(item => group.has(item.id));
        applied.forEach(item => {
            item.newSubLocation = subLocation;
        });

        this.currentId = null;
        this.currentLocation = null;
        this.currentExpectedInput = 'id';

        if (applied.length === 0) {
            // Every row the group put in the queue has since been removed, so
            // there is nothing for this sub-location to attach to.
            this.showAlert(
                `Sub-location ${subLocation} was not applied: the ${this.nounPlural} it belonged to ` +
                'are no longer in the queue.',
                'warning');
            this.updateStatus(`Ready to scan the next ${this.idLabel}.`);
        } else {
            this.updateStatus(
                `Sub-location ${subLocation} applied to ${applied.length} ` +
                `${this.nounFor(applied.length)}. Ready to scan the next ${this.idLabel}.`);
        }

        this.updateScannerStatus(`Ready for ${this.idLabel}`);
        this.updateUI();
    }

    /**
     * Where a subject is now, for display alongside where it is going.
     *
     * Used both by finalizeCurrentMove() for a scanned subject and by the
     * preselected group on load. It stays per-subject and unbatched: batching
     * it would be an optimization with no measurement behind it (Principle I).
     *
     * A location that is simply not set comes back as null and is shown as
     * "None" -- products in particular often have never been given one. Only a
     * subject that could not be looked up at all reports 'Unknown', and it is
     * queued anyway: validation is where a missing subject is caught.
     */
    async fetchCurrentLocation(id) {
        try {
            const result = await this.lookup(id);
            if (result.found) {
                return {
                    location: result.location || null,
                    subLocation: result.subLocation || null,
                    label: result.label
                };
            }
        } catch (error) {
            console.warn(`Could not fetch current location for ${this.noun}:`, error);
        }
        return { location: 'Unknown', subLocation: null, label: null };
    }

    async finalizeCurrentMove(subLocation, idOverride = null, locationOverride = null) {
        console.log(`finalizeCurrentMove() called: subLocation=${subLocation}, idOverride=${idOverride}, locationOverride=${locationOverride}`);

        // Use provided values or fall back to current state
        const id = idOverride || this.currentId;
        const newLocation = locationOverride || this.currentLocation;
        console.log(`finalizeCurrentMove(): Will use id=${id}, newLocation=${newLocation}`);

        // Fetch current location and sub-location for the subject
        const current = await this.fetchCurrentLocation(id);

        // Add to move queue
        const moveItem = {
            id: id,
            itemInfo: current.label,
            newLocation: newLocation,
            newSubLocation: subLocation || null,
            currentLocation: current.location,
            currentSubLocation: current.subLocation,
            status: 'pending',
            timestamp: new Date().toISOString()
        };

        this.moveQueue.push(moveItem);

        // Build status message
        let statusMsg = `Added ${moveItem.id} → ${newLocation}`;
        if (subLocation) {
            statusMsg += ` (${subLocation})`;
        }
        statusMsg += ` to queue. Ready to scan next ${this.idLabel}.`;

        // Only reset state if we're finalizing the current move
        // If using overrides (idOverride != null), we're finalizing a previous move
        // while a new move has already been started, so don't reset state
        if (!idOverride) {
            console.log('finalizeCurrentMove(): Resetting state (no override)');
            this.currentId = null;
            this.currentLocation = null;
            this.currentExpectedInput = 'id';
            this.updateStatus(statusMsg);
            this.updateScannerStatus(`Ready for ${this.idLabel}`);
        } else {
            console.log('finalizeCurrentMove(): Not resetting state (using override)');
        }

        // Always update UI to reflect new queue count
        this.updateUI();

        console.log('Added to move queue:', moveItem);
    }
    
    async handleDoneCode() {
        this.clearInput();

        // If we were in the middle of entering a move, finalize or clear it
        if (this.currentExpectedInput === 'bulk_location') {
            // Nothing can be queued: the group still has no destination, and
            // there is nothing else in the queue to validate. Say that, rather
            // than reporting an empty queue as though the user had scanned
            // nothing at all.
            const count = this.pendingMoves.length;
            this.showAlert(
                `Nothing was queued: ${count} ${this.nounFor(count)} still ` +
                'need a destination. Scan the location they are going to (M*, T*, or Other).',
                'warning');
            return;
        }

        if (this.currentExpectedInput === 'location') {
            // We have an ID but no location - clear partial entry
            this.currentId = null;
            this.currentExpectedInput = 'id';
            this.showAlert(`Partial entry cleared (${this.idLabel} without location).`, 'info');
        } else if (this.currentExpectedInput === 'id_or_sub_location' && this.currentId) {
            // We have an ID and location but no sub-location - finalize without sub-location.
            // Await it: finalizeCurrentMove() pushes to moveQueue on the far side of a
            // fetch, so without the await the length check below reads 0 and reports the
            // queue empty for the move it is in the middle of queueing.
            await this.finalizeCurrentMove(null);
            this.showAlert('Finalized last entry without sub-location.', 'info');
        } else if (this.currentExpectedInput === 'id_or_sub_location') {
            // A preselected group was queued and nothing has been scanned since,
            // so there is no half-entered move to finalize -- the rows are
            // already in the queue. Just close the group off so a later
            // sub-location cannot reopen it.
            this.bulkGroupIds = [];
            this.currentLocation = null;
            this.currentExpectedInput = 'id';
        }

        if (this.moveQueue.length === 0) {
            this.showAlert(`No ${this.nounPlural} in move queue. Add some ${this.nounPlural} before finishing.`, 'warning');
            return;
        }

        this.updateStatus(`Scan completed. ${this.moveQueue.length} ${this.nounPlural} queued for moving.`);
        this.updateScannerStatus('Done - Ready to Validate');
        this.validateBtn.disabled = false;
        this.updateValidateHint();
    }
    
    clearInput() {
        this.barcodeInput.value = '';
    }
    
    clearAll() {
        this.clearQueue();
        this.currentId = null;
        this.currentLocation = null;
        this.currentExpectedInput = 'id';

        // Discard any preselected group along with everything else, and take its
        // card off the page with it: leaving a list of items on screen that are
        // no longer waiting for anything is exactly the kind of quiet lie this
        // feature exists to remove.
        this.pendingMoves = [];
        this.discardPreselectedSection();

        this.updateStatus(`All data cleared. Ready to scan first ${this.idLabel}.`);
        this.updateScannerStatus('Ready');
        this.hideValidationResults();
        this.clearAlerts();
    }
    
    clearQueue() {
        this.moveQueue = [];

        // The group's rows are gone, so the indexes that pointed at them are
        // stale -- a sub-location scanned afterwards would write into a queue
        // that no longer has those positions.
        this.bulkGroupIds = [];

        // A preselected group cannot be re-fetched by scanning a location
        // again, so having cleared it the page must fall back to ordinary
        // scanning rather than sitting in a state that is waiting for the rest
        // of a move nobody is making. A genuinely half-entered move is left
        // alone: its ID is still on screen and still wants a location.
        if (this.currentExpectedInput === 'id_or_sub_location' && !this.currentId) {
            this.currentLocation = null;
            this.currentExpectedInput = 'id';
            this.updateStatus(`Queue cleared. Ready to scan a ${this.idLabel}.`);
            this.updateScannerStatus(`Ready for ${this.idLabel}`);
        }

        this.updateUI();
        this.validateBtn.disabled = true;
        this.executeMoveBtn.disabled = true;
    }
    
    updateUI() {
        this.updateQueueDisplay();
        this.updateButtonStates();
    }
    
    updateQueueDisplay() {
        const count = this.moveQueue.length;
        // Always "item(s)", whatever is being moved: the badge counts queue
        // entries, and the e2e waiter matches this exact wording.
        this.queueCount.textContent = `${count} item${count !== 1 ? 's' : ''}`;
        
        if (count === 0) {
            this.queueEmpty.style.display = 'block';
            this.queueList.classList.add('d-none');
            this.clearQueueBtn.disabled = true;
        } else {
            this.queueEmpty.style.display = 'none';
            this.queueList.classList.remove('d-none');
            this.clearQueueBtn.disabled = false;
            this.renderQueueItems();
        }
    }
    
    renderQueueItems() {
        this.queueItems.innerHTML = '';

        this.moveQueue.forEach((item, index) => {
            const row = document.createElement('tr');

            // Format location display. A null current location is one that was
            // never set; 'Unknown' is one that could not be looked up.
            const currentLoc = item.currentLocation
                ? `<span class="text-muted">${item.currentLocation}</span>`
                : '<span class="text-muted fst-italic">None</span>';
            const currentSubLoc = item.currentSubLocation || '<span class="text-muted fst-italic">None</span>';
            let newSubLoc;
            if (item.newSubLocation) {
                newSubLoc = `<span class="fw-bold text-primary">${item.newSubLocation}</span>`;
            } else if (item.currentSubLocation) {
                // Clearing sub-location
                newSubLoc = '<span class="text-danger fst-italic">Cleared</span>';
            } else {
                // No sub-location before or after
                newSubLoc = '<span class="text-muted fst-italic">None</span>';
            }

            row.innerHTML = `
                <td>
                    <strong>${item.id}</strong>
                    ${item.itemInfo ? `<br><small class="text-muted">${item.itemInfo}</small>` : ''}
                </td>
                <td>
                    ${currentLoc}
                </td>
                <td>
                    ${currentSubLoc}
                </td>
                <td>
                    <span class="fw-bold text-primary">${item.newLocation}</span>
                </td>
                <td>
                    ${newSubLoc}
                </td>
                <td>
                    <span class="badge ${this.getStatusBadgeClass(item.status)}">${item.status}</span>
                </td>
                <td>
                    <button type="button" class="btn btn-sm btn-outline-danger"
                            onclick="window.moveManager.removeFromQueue(${index})"
                            title="Remove from queue">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            this.queueItems.appendChild(row);
        });
    }
    
    getStatusBadgeClass(status) {
        switch (status) {
            case 'pending': return 'bg-secondary';
            case 'validated': return 'bg-success';
            case 'error': return 'bg-danger';
            case 'not_found': return 'bg-warning';
            default: return 'bg-secondary';
        }
    }
    
    removeFromQueue(index) {
        if (index >= 0 && index < this.moveQueue.length) {
            const removed = this.moveQueue.splice(index, 1)[0];
            this.updateUI();
            this.showAlert(`Removed ${removed.id} from move queue`, 'info');
            
            // If queue becomes empty, reset validation
            if (this.moveQueue.length === 0) {
                this.hideValidationResults();
            }
        }
    }
    
    updateButtonStates() {
        const hasItems = this.moveQueue.length > 0;
        this.clearQueueBtn.disabled = !hasItems;

        // Validate button enabled only when we have items and nothing is
        // half-entered. This is deliberately not "enabled whenever the queue is
        // non-empty": that would let a user validate a batch missing items they
        // believe they scanned, which is worse than the bug it would hide.
        this.validateBtn.disabled = !hasItems || this.halfEnteredReason() !== '';

        // Execute moves button only enabled after successful validation
        const allValidated = hasItems && this.moveQueue.every(item => item.status === 'validated');
        this.executeMoveBtn.disabled = !allValidated;

        this.updateValidateHint();
    }

    /**
     * Why the batch cannot be validated yet, or '' if it can.
     *
     * A preselected group that has been queued leaves the machine in
     * `id_or_sub_location` with no move in progress, and nothing about that
     * is half-entered -- the rows are complete and the state is only held open
     * so a sub-location can still be applied to the group.
     */
    halfEnteredReason() {
        if (this.currentExpectedInput === 'bulk_location') {
            const count = this.pendingMoves.length;
            return `${count} ${this.nounFor(count)} still need a destination.`;
        }
        if (this.currentExpectedInput === 'location') {
            return `${this.currentId} has no location yet. Scan its location to finish the entry.`;
        }
        if (this.currentExpectedInput === 'id_or_sub_location' && this.currentId) {
            return `${this.currentId} is not queued yet. Scan the next ${this.idLabel}, a sub-location, or >>DONE<< to finish it.`;
        }
        return '';
    }

    /**
     * FR-018. A disabled button that says nothing is what made issue #107
     * impossible for the user to act on: the reason was always knowable, and
     * was never on screen.
     */
    updateValidateHint() {
        if (!this.validateHint) {
            return;
        }
        const reason = this.moveQueue.length > 0 ? this.halfEnteredReason() : '';
        this.validateHint.textContent = reason;
        this.validateBtn.title = reason || 'Validate the queued moves before executing them';
    }
    
    updateStatus(message) {
        this.statusText.textContent = message;
    }
    
    updateScannerStatus(status = 'Ready') {
        this.scannerStatus.textContent = status;
        this.scannerStatus.className = 'badge ms-2 ' + this.getScannerStatusClass(status);
    }
    
    getScannerStatusClass(status) {
        if (status.includes('Ready')) return 'bg-success';
        if (status.includes('Waiting')) return 'bg-warning';
        if (status.includes('Done')) return 'bg-info';
        if (status.includes('Error')) return 'bg-danger';
        return 'bg-secondary';
    }
    
    async validateMoves() {
        if (this.moveQueue.length === 0) {
            this.showAlert(`No ${this.nounPlural} to validate`, 'warning');
            return;
        }
        
        this.validateBtn.disabled = true;
        this.validateBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Validating...';
        
        try {
            // Validate each item
            const validationPromises = this.moveQueue.map(item => this.validateMoveItem(item));
            const results = await Promise.all(validationPromises);
            
            // Update move queue with validation results
            results.forEach((result, index) => {
                this.moveQueue[index] = { ...this.moveQueue[index], ...result };
            });
            
            this.displayValidationResults();
            this.updateUI();
            
        } catch (error) {
            console.error('Validation error:', error);
            this.showAlert('Validation failed. Please try again.', 'danger');
        } finally {
            this.validateBtn.disabled = false;
            this.validateBtn.innerHTML = '<i class="bi bi-check-square"></i> Validate & Preview';
        }
    }
    
    /**
     * Re-check one queued move against the server.
     *
     * One lookup() per entry, the same call that established the current
     * location when the move was queued. The item page used to call
     * /api/items/{id}/exists and then /api/items/{id}, reading the second
     * response without its `item` envelope -- so every validated row lost its
     * real current location to 'Unknown'. One call read one way cannot do that.
     */
    async validateMoveItem(item) {
        try {
            const result = await this.lookup(item.id);
            if (!result.found) {
                return {
                    status: 'not_found',
                    error: `${this.nounTitle} ${item.id} not found`
                };
            }
            return {
                status: 'validated',
                currentLocation: result.location || null,
                currentSubLocation: result.subLocation || null,
                itemInfo: result.label || item.itemInfo
            };
        } catch (error) {
            console.error(`Error validating ${this.noun}:`, error);
            return {
                status: 'error',
                error: 'Validation failed'
            };
        }
    }

    displayValidationResults() {
        const validCount = this.moveQueue.filter(item => item.status === 'validated').length;
        const errorCount = this.moveQueue.filter(item => item.status === 'error').length;
        const notFoundCount = this.moveQueue.filter(item => item.status === 'not_found').length;
        
        let resultsHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-success">${validCount}</div>
                        <small class="text-muted">Valid ${this.nounPluralTitle}</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-danger">${errorCount}</div>
                        <small class="text-muted">Errors</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-warning">${notFoundCount}</div>
                        <small class="text-muted">Not Found</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <div class="display-6 text-info">${this.moveQueue.length}</div>
                        <small class="text-muted">Total ${this.nounPluralTitle}</small>
                    </div>
                </div>
            </div>
        `;
        
        if (errorCount > 0 || notFoundCount > 0) {
            resultsHTML += '<div class="alert alert-warning mt-3">';
            resultsHTML += '<i class="bi bi-exclamation-triangle"></i> ';
            resultsHTML += `Some ${this.nounPlural} have validation issues. Please review the move queue and remove or correct problematic ${this.nounPlural} before executing moves.`;
            resultsHTML += '</div>';
        } else {
            resultsHTML += '<div class="alert alert-success mt-3">';
            resultsHTML += '<i class="bi bi-check-circle"></i> ';
            resultsHTML += `All ${this.nounPlural} validated successfully! You can now execute the moves.`;
            resultsHTML += '</div>';
        }
        
        this.validationResults.innerHTML = resultsHTML;
        this.validationSection.style.display = 'block';
    }
    
    hideValidationResults() {
        this.validationSection.style.display = 'none';
    }
    
    async executeMoves() {
        const validItems = this.moveQueue.filter(item => item.status === 'validated');
        
        if (validItems.length === 0) {
            this.showAlert(`No valid ${this.nounPlural} to move`, 'warning');
            return;
        }
        
        if (!confirm(`Are you sure you want to move ${validItems.length} ${this.nounPlural}? This action cannot be undone.`)) {
            return;
        }
        
        this.executeMoveBtn.disabled = true;
        this.executeMoveBtn.innerHTML = `<i class="bi bi-hourglass-split"></i> Moving ${this.nounPluralTitle}...`;
        
        try {
            const response = await fetch(this.executeUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
                },
                body: JSON.stringify({
                    moves: validItems.map(item => this.moveRequest(item))
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showAlert(`Successfully moved ${result.moved_count} ${this.nounPlural}!`, 'success');
                this.clearAll();
            } else {
                this.showAlert(`Move failed: ${result.error}`, 'danger');
            }
            
        } catch (error) {
            console.error('Execute moves error:', error);
            this.showAlert('Failed to execute moves. Please try again.', 'danger');
        } finally {
            this.executeMoveBtn.disabled = false;
            this.executeMoveBtn.innerHTML = '<i class="bi bi-play-fill"></i> Execute Moves';
        }
    }
    
    showAlert(message, type = 'info') {
        const alertClass = `alert-${type}`;
        const iconClass = type === 'danger' ? 'bi-exclamation-triangle' : 
                         type === 'success' ? 'bi-check-circle' : 
                         type === 'warning' ? 'bi-exclamation-triangle' :
                         'bi-info-circle';
        
        const alertHTML = `
            <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
                <i class="bi ${iconClass}"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        // Appended, not assigned. Assigning meant each message replaced the
        // previous one, so fourteen refused scans rendered as a single warning
        // and the user scanning into a machine that was refusing everything
        // could not see that it was. That masking is half of issue #107 -- see
        // specs/026-fix-bulk-move-handoff/verification.md.
        this.formAlerts.insertAdjacentHTML('beforeend', alertHTML);
        const alert = this.formAlerts.lastElementChild;

        // Auto-dismiss info and success alerts after 5 seconds. Warnings and
        // errors stay: they are the record of what went wrong.
        if (type === 'info' || type === 'success') {
            setTimeout(() => {
                if (alert && alert.isConnected) {
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                }
            }, 5000);
        }
    }
    
    clearAlerts() {
        this.formAlerts.innerHTML = '';
    }

    /** "item" or "items" (or the subclass's noun) to agree with `count`. */
    nounFor(count) {
        return count === 1 ? this.noun : this.nounPlural;
    }

    get nounTitle() {
        return this.noun.charAt(0).toUpperCase() + this.noun.slice(1);
    }

    get nounPluralTitle() {
        return this.nounPlural.charAt(0).toUpperCase() + this.nounPlural.slice(1);
    }

    // ------------------------------------------------------------------
    // Supplied by the subclass. See contracts/move-manager.md.
    // ------------------------------------------------------------------

    /** Singular and plural noun for the subject: 'item'/'items'. */
    get noun() { throw new Error('subclass must define noun'); }
    get nounPlural() { throw new Error('subclass must define nounPlural'); }

    /** What a subject ID is called in messages and badges: 'JA ID'. */
    get idLabel() { throw new Error('subclass must define idLabel'); }

    /** An example ID shown when the wrong kind of input arrives. */
    get idExample() { throw new Error('subclass must define idExample'); }

    /** Whether a scan is this page's subject ID. */
    isSubjectId(value) { throw new Error('subclass must define isSubjectId'); }

    /** The canonical form of a subject ID that isSubjectId() accepted. */
    normalizeId(value) { return value; }

    /** Whether a scan is the *other* move page's ID, refused here. */
    isForeignId(value) { return false; }

    /** The alert shown when a foreign ID is scanned. */
    foreignIdMessage(value) { return `${value} cannot be moved on this page.`; }

    /**
     * Look one subject up. Resolves to
     * {found: true, location, subLocation, label} or {found: false} when the
     * server says it does not exist; throws on any other failure.
     */
    async lookup(id) { throw new Error('subclass must define lookup'); }

    /** The endpoint Execute Moves posts to. */
    get executeUrl() { throw new Error('subclass must define executeUrl'); }

    /** One queue entry as the execute endpoint expects it. */
    moveRequest(entry) { throw new Error('subclass must define moveRequest'); }
}