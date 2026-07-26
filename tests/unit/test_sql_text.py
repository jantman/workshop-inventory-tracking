"""
Unit tests for app/utils/sql_text.py — the ONE LIKE-literal escaper and the ONE
storability predicate (DW-42, DW-77).

Six query sites in three modules now build their patterns through
`escape_like_literal`, and four entry points refuse unstorable text through
`is_storable_text`, so this module is a single point of failure for the
catalog's search, the scan fallthrough, the category rename, and all seven
fields of the suggestions endpoint. These tests pin the two functions
directly; the callers' behavioral tests live with the callers.
"""

import pytest

from app.utils.sql_text import (LIKE_ESCAPE_CHAR, escape_like_literal,
                                is_storable_text)


class TestLikeEscapeChar:

    @pytest.mark.unit
    def test_the_escape_character_is_a_single_backslash(self):
        """The character every caller must ALSO pass as `escape=`: a pattern
        escaped with a character the statement never declares is worse than no
        escaping, because the escape characters then match literally."""
        assert LIKE_ESCAPE_CHAR == '\\'
        assert len(LIKE_ESCAPE_CHAR) == 1


class TestEscapeLikeLiteral:
    """Literal text in, LIKE-safe text out. The wildcards the CALLER wants
    (the surrounding `%…%`) are concatenated afterwards, never here."""

    @pytest.mark.unit
    @pytest.mark.parametrize('value, expected', [
        ('', ''),                              # nothing to escape
        ('plain text', 'plain text'),          # ditto, with a space
        ('10%', '10\\%'),                      # the percent wildcard
        ('%', '\\%'),                          # ...alone
        ('power_supplies', 'power\\_supplies'),  # the single-char wildcard
        ('_', '\\_'),                          # ...alone
        ('a\\b', 'a\\\\b'),                    # the escape character itself
        ('\\', '\\\\'),                        # ...alone
        ('%_\\', '\\%\\_\\\\'),                # all three at once
        ('50% off_1\\2', '50\\% off\\_1\\\\2'),  # all three, embedded
    ])
    def test_every_metacharacter_is_escaped_and_nothing_else_is(
            self, value, expected):
        assert escape_like_literal(value) == expected

    @pytest.mark.unit
    def test_the_escape_character_is_replaced_before_the_wildcards(self):
        """Order is the whole correctness argument. Escaping `%` first would
        insert backslashes that the later `\\` pass then doubles, so
        `'%'` would come out as `'\\\\%'` — a pattern matching a literal
        backslash followed by ANY string, rather than a literal percent."""
        assert escape_like_literal('%') == '\\%'
        assert escape_like_literal('_') == '\\_'
        # The already-escaped-looking input proves the same thing from the
        # other side: both characters are literal, so both are escaped.
        assert escape_like_literal('\\%') == '\\\\\\%'

    @pytest.mark.unit
    def test_escaping_is_deliberately_not_idempotent(self):
        """The input is literal TEXT, not a pattern, so escaping twice escapes
        the escape characters again — correct, and the reason every caller
        passes raw text exactly once. Pinned so nobody 'fixes' it into an
        idempotent function and quietly makes double-escaping invisible."""
        once = escape_like_literal('50%')
        assert once == '50\\%'
        assert escape_like_literal(once) == '50\\\\\\%'
        assert escape_like_literal(once) != once

    @pytest.mark.unit
    def test_the_category_pattern_is_built_on_this_function(self):
        """`descendant_like_pattern` is the escaper's oldest caller and must
        not carry a second copy: its output is this function's output plus the
        one live wildcard it appends (DW-42)."""
        from app.utils.category import (CATEGORY_LIKE_ESCAPE_CHAR,
                                        descendant_like_pattern)

        assert CATEGORY_LIKE_ESCAPE_CHAR == LIKE_ESCAPE_CHAR
        assert (descendant_like_pattern('power_supplies/50%')
                == escape_like_literal('power_supplies/50%') + '/%')


class TestIsStorableText:
    """Whether text can reach the database intact and mean what it says. Both
    False cases are silent wrong answers rather than errors, which is why they
    are refused before a query rather than caught after one."""

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '',                # nothing at all is storable
        'plain',
        '10% off_1\\2',    # LIKE metacharacters are storable, just escaped
        'café',            # non-ASCII with a valid UTF-8 encoding
        '\U0001f600',      # astral: a legitimate surrogate PAIR in UTF-16
        '\t\r\n',          # control characters other than NUL are fine
    ])
    def test_ordinary_text_is_storable(self, value):
        assert is_storable_text(value) is True

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '\x00',        # alone: the pattern degenerates to a bare `%`
        'a\x00b',      # embedded: the pattern truncates to a prefix
        '\x00abc',     # leading
        'abc\x00',     # trailing
        '\x00' * 4096,  # the classic wedge no-read
    ])
    def test_a_nul_anywhere_is_not_storable(self, value):
        """A NUL binds without error and then compares WRONG: SQLite reads the
        LIKE pattern as a C string and stops there, so the pattern that runs is
        a prefix of the one built."""
        assert is_storable_text(value) is False

    @pytest.mark.unit
    @pytest.mark.parametrize('value', [
        '\ud800',       # a lone high surrogate
        '\udfff',       # a lone low surrogate
        'a\ud800b',     # embedded in otherwise ordinary text
    ])
    def test_an_unpaired_surrogate_is_not_storable(self, value):
        """No UTF-8 encoding exists, so a driver raises UnicodeEncodeError on
        binding — the predicate answers instead of letting the caller raise."""
        assert is_storable_text(value) is False

    @pytest.mark.unit
    def test_the_predicate_itself_never_raises_on_unencodable_text(self):
        """It is the guard for callers contracted not to raise (NFR8), so it
        cannot be the thing that raises."""
        assert is_storable_text('\ud800') is False
        with pytest.raises(UnicodeEncodeError):
            '\ud800'.encode('utf-8')
