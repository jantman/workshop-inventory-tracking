"""
Unit tests for the item hand-off -- app/utils/handoff.py.

The hand-off is the interface between a list page that names items and a working
page that acts on them (specs/026-fix-bulk-move-handoff/contracts/handoff.md).
It had no contract and no tests before, which is how two producers came to spell
the parameter differently while neither receiver read it at all.

Two halves are covered here, matching the two halves of the module: parsing the
`ja_id` parameter into an ordered, de-duplicated list, and resolving each
identifier against storage into accepted items and named rejections. Nothing
handed off may ever be silently dropped (FR-005), so every rejection path is
asserted on by name and reason.
"""

import pytest

from app.utils.handoff import INACTIVE, NOT_FOUND, parse_ja_ids, resolve_handoff


class TestParseJaIds:
    """contracts/handoff.md section 2, steps 1, 2 and 4."""

    def test_absent_parameter_is_no_hand_off(self):
        assert parse_ja_ids(None) == []

    def test_empty_parameter_is_no_hand_off(self):
        assert parse_ja_ids('') == []

    def test_whitespace_only_parameter_is_no_hand_off(self):
        assert parse_ja_ids('   ') == []

    def test_single_item_is_a_list_of_one(self):
        assert parse_ja_ids('JA000101') == ['JA000101']

    def test_comma_separated_list_keeps_payload_order(self):
        assert parse_ja_ids('JA000117,JA000101,JA000102') == [
            'JA000117', 'JA000101', 'JA000102'
        ]

    def test_surrounding_whitespace_is_trimmed(self):
        assert parse_ja_ids(' JA000101 , JA000102 ') == ['JA000101', 'JA000102']

    def test_empty_elements_are_discarded(self):
        assert parse_ja_ids('JA000101,,JA000102,') == ['JA000101', 'JA000102']

    def test_duplicates_collapse_to_first_occurrence(self):
        """FR-006. A queue cannot move one item to two places."""
        assert parse_ja_ids('JA000101,JA000102,JA000101') == ['JA000101', 'JA000102']

    def test_malformed_elements_are_kept_for_rejection_not_dropped(self):
        """Step 3 rejects a malformed identifier as not_found -- and a rejection
        has to be reported by name, so parsing must not discard it silently."""
        assert parse_ja_ids('JA000101,banana') == ['JA000101', 'banana']


class FakeService:
    """The two InventoryService methods resolution uses, and nothing else."""

    def __init__(self, active=(), inactive=()):
        self._active = set(active)
        self._inactive = set(inactive)

    def get_active_item(self, ja_id):
        return {'ja_id': ja_id} if ja_id in self._active else None

    def ja_id_exists(self, ja_id, only_active=True):
        known = self._active if only_active else self._active | self._inactive
        return ja_id in known


class TestResolveHandoff:
    """contracts/handoff.md section 2, steps 3 and 5; data-model.md section 2."""

    def test_no_hand_off_resolves_to_nothing_at_all(self):
        """FR-004: the receiving page must behave exactly as it does today."""
        handoff = resolve_handoff(None, FakeService(active=['JA000101']))
        assert handoff.preselected_items == []
        assert handoff.rejected_items == []
        assert not handoff.has_hand_off

    def test_an_active_row_is_accepted(self):
        handoff = resolve_handoff('JA000101', FakeService(active=['JA000101']))
        assert handoff.preselected_items == ['JA000101']
        assert handoff.rejected_items == []
        assert handoff.has_hand_off

    def test_a_missing_id_is_rejected_as_not_found(self):
        handoff = resolve_handoff('JA000999', FakeService(active=['JA000101']))
        assert handoff.preselected_items == []
        assert handoff.rejected_items == [
            {'ja_id': 'JA000999', 'reason': NOT_FOUND}
        ]

    def test_an_inactive_row_is_rejected_as_inactive(self):
        """Principle VI: a hand-off must not queue a historical row for a move."""
        service = FakeService(active=['JA000101'], inactive=['JA000102'])
        handoff = resolve_handoff('JA000102', service)
        assert handoff.preselected_items == []
        assert handoff.rejected_items == [
            {'ja_id': 'JA000102', 'reason': INACTIVE}
        ]

    def test_a_malformed_identifier_is_rejected_as_not_found(self):
        """Step 3. It cannot name an item, so it is reported, not consulted."""
        handoff = resolve_handoff('banana', FakeService(active=['JA000101']))
        assert handoff.preselected_items == []
        assert handoff.rejected_items == [{'ja_id': 'banana', 'reason': NOT_FOUND}]

    def test_the_remainder_proceeds_when_one_item_is_rejected(self):
        """FR-005: report the failure, do not fail wholesale."""
        service = FakeService(active=['JA000101', 'JA000103'], inactive=['JA000102'])
        handoff = resolve_handoff('JA000101,JA000102,JA000999,JA000103', service)
        assert handoff.preselected_items == ['JA000101', 'JA000103']
        assert handoff.rejected_items == [
            {'ja_id': 'JA000102', 'reason': INACTIVE},
            {'ja_id': 'JA000999', 'reason': NOT_FOUND},
        ]

    def test_rejections_are_reported_in_payload_order(self):
        service = FakeService(active=['JA000102'])
        handoff = resolve_handoff('banana,JA000102,JA000999', service)
        assert [r['ja_id'] for r in handoff.rejected_items] == ['banana', 'JA000999']

    def test_every_item_rejected_is_distinguishable_from_no_hand_off(self):
        """Edge case: an all-rejected arrival must not look like a normal one."""
        handoff = resolve_handoff('JA000999', FakeService())
        assert handoff.preselected_items == []
        assert handoff.rejected_items
        assert handoff.has_hand_off

    def test_accepted_items_keep_payload_order(self):
        service = FakeService(active=['JA000101', 'JA000102', 'JA000117'])
        handoff = resolve_handoff('JA000117,JA000101,JA000102', service)
        assert handoff.preselected_items == ['JA000117', 'JA000101', 'JA000102']

    def test_a_duplicate_is_resolved_once(self):
        service = FakeService(active=['JA000101'])
        handoff = resolve_handoff('JA000101,JA000101', service)
        assert handoff.preselected_items == ['JA000101']

    def test_first_accepted_is_the_one_a_single_item_page_takes(self):
        """Step 6: Shorten handles one item; a longer list is not an error."""
        service = FakeService(active=['JA000102'], inactive=['JA000101'])
        handoff = resolve_handoff('JA000101,JA000102', service)
        assert handoff.first_accepted == 'JA000102'

    def test_first_accepted_is_none_when_nothing_was_accepted(self):
        assert resolve_handoff('JA000999', FakeService()).first_accepted is None

    def test_first_accepted_is_none_without_a_hand_off(self):
        assert resolve_handoff(None, FakeService()).first_accepted is None
