"""Unit tests for app/utils/batch_move.py, shared by both batch-move routes."""

import pytest

from app.utils.batch_move import batch_result, destination, parse_moves


class TestParseMoves:
    @pytest.mark.parametrize('data', [None, {}, {'other': 1}])
    def test_missing_body_or_key_is_invalid(self, data):
        with pytest.raises(ValueError, match='Invalid request data'):
            parse_moves(data)

    @pytest.mark.parametrize('moves', [[], None, 'JA000001', {'ja_id': 'JA000001'}])
    def test_empty_or_non_list_is_no_moves(self, moves):
        with pytest.raises(ValueError, match='No moves provided'):
            parse_moves({'moves': moves})

    def test_returns_the_list(self):
        moves = [{'ja_id': 'JA000001', 'new_location': 'M1'}]
        assert parse_moves({'moves': moves}) is moves


class TestDestination:
    def test_strips_both(self):
        assert destination('  M1-A ', ' Drawer 3 ') == ('M1-A', 'Drawer 3')

    @pytest.mark.parametrize('sub', [None, '', '   '])
    def test_absent_or_blank_sub_location_clears(self, sub):
        assert destination('M1-A', sub) == ('M1-A', None)


class TestBatchResult:
    def test_all_moved(self):
        assert batch_result(2, 2, []) == {
            'success': True, 'moved_count': 2, 'total_count': 2, 'failed_moves': [],
        }

    def test_partial_names_the_failure_count(self):
        failed = [{'code': 'WIT0000000000', 'error': 'Product not found'}]
        result = batch_result(1, 2, failed)
        assert result['success'] is False
        assert result['failed_moves'] == failed
        assert result['error'] == '1 items failed to move'
