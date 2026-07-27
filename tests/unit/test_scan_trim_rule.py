r"""
Source tripwire for the JavaScript copy of the scan trim rule (DW-59).

The set of characters trimmed off a captured scan exists twice, and it has to:
`app/utils/scan_input.py`'s `SCAN_TRIM` is what the server applies, and
`ScanCapture.stripOuter` in `app/static/js/scan-capture.js` is what the client
uses to decide "is this field blank, or is there a scan in it?". The browser
cannot import Python, so the second copy is unavoidable — but a copy nothing
compares is a copy that drifts.

Drift is expensive in exactly one direction and invisible in both. A JS rule
WIDER than the server's (the obvious "simplification" is `value.trim()`, which
strips the whole Unicode whitespace set — VT, FF, NBSP, BOM) silently drops a
payload the server would have accepted: no request, no toast, no log line, and
an operator who scanned something and got nothing. A JS rule NARROWER than the
server's sends a payload the server then trims to blank and refuses, which at
least produces an error. Neither shows up in any other test in the fast suite:
the client never reads `data.raw` back, so each side is only ever pinned against
its own expectations.

`tests/e2e/test_wedge_scan.py` compares the two behaviorally, driving a real
browser against a real server — that is the honest proof and this file does not
replace it. But the e2e session takes ~20 minutes and is not what a developer
runs before pushing, so the same invariant is asserted here as TEXT, in the fast
`nox -s tests` session, following the shape of
`tests/unit/test_keydown_focus_guards.py` and `tests/unit/test_toast_markup.py`.

What it cannot assert, stated plainly
-------------------------------------
Nothing here executes a line of JavaScript: there is no JS unit-test harness in
this repo. Everything below is a string and regex reading of the source, so it
checks that the rule is SPELLED the same on both sides and that the blank gate
still routes through it — never that a browser then behaves that way. A gate
that calls `stripOuter` and ignores the answer, or any caller reached from
somewhere this module does not read, passes every test here. That is
`tests/e2e/test_wedge_scan.py`'s job.

The extraction is deliberately strict rather than forgiving, because the
failures worth catching are the ones that look harmless. The whole returned
expression must read `return value.replace(<regex>, '').replace(<regex>, '');`,
each of the two regex literals must match its exact expected shape
(`/^[...]+/` and `/[...]+$/`) carrying no flags, and those two must be the only
regex literals in the function. Every part of that earns its keep against a
form that would otherwise compare equal while the rule is dead: a looser
reading that merely hunted for `[...]` anywhere would let `/^[ \t\r\n]+|^\s+/`
through, where the alternation outside the class widens the rule to the entire
Unicode whitespace set; a `y` flag makes the trailing rule match only at
`lastIndex` and trim nothing; a `.replace()` whose result is dropped, or a
replacement argument that is not `''`, leaves both classes reading correctly
while `stripOuter` returns untrimmed text. When the anchor is gone — the
function renamed, the regexes restructured into something this module cannot
read — every assertion fails loudly with a message saying so, rather than
quietly matching nothing and reporting green.
"""

import re
from pathlib import Path

import pytest

from app.utils.scan_input import SCAN_TRIM

SCAN_CAPTURE_JS = (Path(__file__).resolve().parents[2]
                   / 'app' / 'static' / 'js' / 'scan-capture.js')

#: The members of the `ScanCapture` object literal are indented four spaces and
#: each closes on its own `    },` line, so that terminator bounds `stripOuter`
#: without brace-counting a language this module does not parse — the same
#: device `tests/unit/test_toast_markup.py` uses. Reformatting the file makes
#: the extraction fail loudly instead of silently matching the whole file.
MEMBER_END = re.compile(r'^    \},$', re.MULTILINE)

#: The blank gate, as a STATEMENT on its own line. `stripOuter` being correct
#: is worth nothing if the gate stops calling it: the rule would still read
#: right here while the client fell back on whatever the gate does instead.
#: Anchored to the start of a line rather than searched for as a substring,
#: because a substring is still found after the line is commented out — which
#: is the cheapest possible way to disable the gate. The line anchor alone only
#: defeats the `//` form, so the search runs over comment-stripped source: a
#: `/* … */` wrapped around the gate leaves the line itself untouched and
#: matching, and is exactly as cheap. The argument expression is deliberately
#: NOT pinned: hoisting `this.input.value` into a local is a behavior-preserving
#: edit and should not be reported as a reintroduced bug.
BLANK_GATE_STATEMENT = re.compile(
    r'^[ \t]*if \(!this\.stripOuter\(.+\)\) return;$', re.MULTILINE)

#: Block and line comments, for the blank-gate check only. Stripping is scoped
#: to that check on purpose: the `.trim(` ban below is deliberately whole-file
#: INCLUDING comments, so that a commented-out `value.trim()` left behind as a
#: "this is what it used to be" note still has to be justified.
JS_COMMENT = re.compile(r'/\*.*?\*/|//[^\n]*', re.DOTALL)

#: Any JS regex literal, delimiters included. The body class excludes `/` so a
#: literal can never span from one to the next, and `\\.` keeps an escaped
#: slash inside one from ending it early. The flag suffix is `[a-z]*` rather
#: than the flags that exist today, so a literal carrying ANY flag is captured
#: whole and then fails the shape check below. A flag class listing only the
#: known flags would instead leave an unknown one (`d`, `v`) outside the match
#: and step over it silently.
REGEX_LITERAL = re.compile(r'/(?:[^/\\\n]|\\.)+/[a-z]*')

#: The exact shape each of the two rules must have — leading run, then trailing
#: run. Matched in full, so anything extra inside the literal (an alternation,
#: a second class, a lookahead) is a failure rather than something the capture
#: quietly steps over. Which end each rule trims IS the invariant here: two
#: leading rules would leave trailing padding on a scan the server trims.
#:
#: NO flags are permitted, and that is load-bearing rather than tidiness: `y`
#: makes `/[ \t\r\n]+$/` match only at `lastIndex`, so the trailing trim does
#: nothing at all, and `m` makes `/^[ \t\r\n]+/` strip after every newline,
#: so an interior run is eaten. Either leaves the character class reading
#: exactly right while the rule it spells is no longer the server's.
LEADING_RULE = re.compile(r'/\^\[([^\]]*)\]\+/')
TRAILING_RULE = re.compile(r'/\[([^\]]*)\]\+\$/')

#: The whole body of `stripOuter`, matched in full — not merely found within
#: it. Correct character classes are worth nothing unless both rules are
#: actually applied to the value that comes back. Four forms pass every
#: character-set assertion below while the trim is dead, and all four were
#: verified against this extractor: a `value.replace(...)` on its own line whose
#: result is dropped, a replacement argument that is not the empty string
#: (`stripOuter` then returns `' '` for `'   '` — truthy, so the blank gate
#: never fires), a `return value;` after a correct-looking chain, and — the one
#: a mere `search()` for this pattern let through — an early `return value;`
#: GUARDED by a condition, which is live code a linter does not flag and which
#: skips the chain for whatever inputs satisfy it. Requiring this to be the
#: function's only statement is what closes all four: there is nowhere left to
#: put the bypass.
RETURN_SHAPE = re.compile(
    r"return\s+value"
    r"\s*\.replace\(\s*(/(?:[^/\\\n]|\\.)+/[a-z]*)\s*,\s*(?:''|\"\")\s*\)"
    r"\s*\.replace\(\s*(/(?:[^/\\\n]|\\.)+/[a-z]*)\s*,\s*(?:''|\"\")\s*\)"
    r"\s*;")

#: JS whitespace-trimming calls, all of which strip the full Unicode
#: whitespace set the server deliberately keeps. `trimStart`/`trimEnd` are the
#: one-ended forms and are exactly what a "fix" to the leading or trailing half
#: of `stripOuter` would reach for. Whitespace is permitted before the paren
#: because `value.trim ()` is the same call and a plain substring test for
#: `.trim(` does not see it.
JS_TRIM_CALL = re.compile(r'\.(trim|trimStart|trimEnd|trimLeft|trimRight)\s*\(')

#: The two-character escapes a JS regex character class can spell these
#: characters with. Only the ones the rule can legitimately contain are decoded:
#: anything else in the class stays as written and will fail the set comparison
#: below, which is the correct outcome for a character this module does not
#: understand.
JS_ESCAPES = {
    '\\t': '\t',
    '\\r': '\r',
    '\\n': '\n',
    '\\f': '\f',
    '\\v': '\v',
    '\\0': '\x00',
    '\\s': None,        # the Unicode whitespace shorthand — not a character
    '\\\\': '\\',
}


def _source():
    return SCAN_CAPTURE_JS.read_text(encoding='utf-8')


def _strip_outer_source(source=None):
    """The source text of `ScanCapture.stripOuter`, and only it.

    Bounded rather than searched for across the whole file: `scan-capture.js`
    contains other regex literals (the AIM-prefix handling, the toast helpers),
    and a whole-file scan would either pick those up or have to special-case
    them one by one as the file grows.

    `source` defaults to the real file. It is a parameter only so the
    fails-loudly tests at the bottom can hand in a fabricated one — patching
    `Path.read_text` is not an option, since `PurePath` uses `__slots__`.
    """
    if source is None:
        source = _source()

    start = source.find('stripOuter: function')
    assert start != -1, (
        'ScanCapture.stripOuter is gone or was renamed: nothing below is '
        "comparing the client's trim rule against the server's SCAN_TRIM any "
        'more, so this tripwire needs rewriting against whatever replaced it')

    definitions = source.count('stripOuter: function')
    assert definitions == 1, (
        f'expected exactly one `stripOuter: function` in scan-capture.js, '
        f'found {definitions}: with more than one, this tripwire reads the '
        f'first and the live rule may be a later one it never compares')

    end = MEMBER_END.search(source, start)
    assert end is not None, (
        'could not find the end of ScanCapture.stripOuter: the object-literal '
        'indentation this tripwire bounds on has changed, so the slice it '
        'checks is no longer that function')
    return source[start:end.start()]


def _blank_gate_is_live(source=None):
    """Whether the blank-Enter gate still calls `stripOuter` as a statement.

    `source` defaults to the real file, and is a parameter for the same reason
    `_strip_outer_source`'s is: so the fails-loudly tests can hand in a
    fabricated one.
    """
    if source is None:
        source = _source()
    return BLANK_GATE_STATEMENT.search(JS_COMMENT.sub('', source)) is not None


def _decoded_class(class_body):
    """The set of characters a JS regex character class names.

    Two-character escapes are decoded first (longest-match irrelevant here —
    they are all two characters), then whatever is left is taken literally.
    `\\s` decodes to `None`, a deliberate sentinel: it is not a character but a
    shorthand for the full Unicode whitespace set, which is precisely the
    widening this tripwire exists to catch, and it must not silently compare
    equal to anything.
    """
    characters = set()
    index = 0
    while index < len(class_body):
        pair = class_body[index:index + 2]
        if pair in JS_ESCAPES:
            characters.add(JS_ESCAPES[pair])
            index += 2
        else:
            characters.add(class_body[index])
            index += 1
    return characters


def _trim_rules(source=None):
    """The leading and trailing trim rules of `stripOuter`, decoded.

    Returns `(leading_characters, trailing_characters)`. Both are extracted, so
    a change to only one end is still caught, and each literal has to match its
    expected shape in full — see `LEADING_RULE` on why a permissive read would
    miss the widening that matters most.
    """
    body = _strip_outer_source(source)

    replacements = body.count('.replace(')
    assert replacements == 2, (
        f'ScanCapture.stripOuter applies {replacements} replacements, not the '
        f'2 this tripwire compares: either a trim rule was added or removed, '
        f'or the function was restructured into a form this file has to be '
        f'rewritten against before it is checking anything again')

    literals = REGEX_LITERAL.findall(body)
    assert len(literals) == 2, (
        f'ScanCapture.stripOuter contains {len(literals)} regex literal(s), '
        f'not the 2 that trim the leading and trailing ends: the rule is no '
        f'longer expressed as two `/[...]/` literals, so this tripwire is '
        f"comparing nothing against the server's SCAN_TRIM and needs "
        f'rewriting against whatever the function does now')

    # Everything after the function's opening brace, which is the whole body:
    # the signature `stripOuter: function(value) {` supplies the first `{`, and
    # the slice already stops before the closing `    },`. Matched in FULL
    # rather than searched, so the chain must be the only statement there is —
    # see RETURN_SHAPE on the guarded early return a search steps over.
    statements = body.split('{', 1)[1].strip()
    assert RETURN_SHAPE.fullmatch(statements), (
        'ScanCapture.stripOuter is not exactly '
        '`return value.replace(<regex>, \'\').replace(<regex>, \'\');`: the '
        'two rules must both be chained onto the returned value, must both '
        'replace with the empty string, and must be the function\'s only '
        'statement. A dropped `.replace()` result, a non-empty replacement, a '
        '`return value;` after the chain, or an early return that skips it '
        'leaves every character-set assertion in this file true while the trim '
        f'it checks does nothing. Found: {statements!r}')

    leading = LEADING_RULE.fullmatch(literals[0])
    assert leading, (
        f'the first regex in ScanCapture.stripOuter is {literals[0]!r}, not '
        f'the expected unflagged `/^[...]+/`: anything else in the literal — '
        f'an alternation, a second class, a lookahead — or a trailing flag '
        f'can change the rule while the character class it carries still '
        f'reads correctly (`m` alone makes it strip after every newline)')
    trailing = TRAILING_RULE.fullmatch(literals[1])
    assert trailing, (
        f'the second regex in ScanCapture.stripOuter is {literals[1]!r}, not '
        f'the expected unflagged `/[...]+$/`: the trailing end of the trim is '
        f'gone, is being done some other way, or carries a flag that changes '
        f'it (`y` alone makes it trim nothing)')

    return _decoded_class(leading.group(1)), _decoded_class(trailing.group(1))


@pytest.mark.unit
class TestPythonTrimSet:
    """The server's half of the invariant, pinned as a literal."""

    def test_the_trim_set_is_exactly_space_tab_cr_lf(self):
        """FR35 names four characters, and the set is not allowed to grow.

        Restated as a literal rather than derived, so widening `SCAN_TRIM` is a
        deliberate act with a red test in front of it. Anything added here is
        a character an ISO/IEC 15434 envelope or a programmed wedge suffix may
        legitimately carry, and stripping it destroys the payload.
        """
        assert SCAN_TRIM == ' \t\r\n'

    def test_the_separators_an_envelope_is_built_from_are_not_in_the_set(self):
        """GS, RS, EOT, FS and US must never join the trim set.

        Python classifies `\\x1c`-`\\x1f` as whitespace, so this is exactly the
        widening a defaulted `str.strip()` would produce — and it would eat the
        RS that terminates a format-06 envelope.
        """
        for char in ('\x1d', '\x1e', '\x04', '\x1c', '\x1f', '\x0b', '\x0c'):
            assert char not in SCAN_TRIM, (
                f'{char!r} has been added to SCAN_TRIM: a scan carrying it as a '
                f'leading or trailing byte now arrives truncated, and an '
                f'ISO/IEC 15434 envelope loses the separator it is built from')


@pytest.mark.unit
class TestJavaScriptCopyMatchesPython:
    """`ScanCapture.stripOuter` names the same four characters, no more."""

    def test_each_regex_class_equals_the_python_trim_set(self):
        """The invariant itself: same characters, both ends, both sides.

        The comparison is on the SET, not on the source text, so reordering
        `[ \\t\\r\\n]` or spelling a character differently is not a failure —
        only naming a different collection of characters is.
        """
        expected = set(SCAN_TRIM)
        for end, characters in zip(('leading', 'trailing'), _trim_rules()):
            assert characters == expected, (
                f'the {end} regex in ScanCapture.stripOuter trims '
                f'{sorted(repr(c) for c in characters)} but the server trims '
                f'{sorted(repr(c) for c in expected)} '
                f'(app/utils/scan_input.py SCAN_TRIM). A wider client rule '
                f'silently drops a scan the server would have accepted — no '
                f'request, no toast; a narrower one posts a payload the server '
                f'then refuses as blank')

    def test_the_blank_gate_still_routes_through_strip_outer(self):
        """A correct `stripOuter` nothing calls is a correct dead function.

        The cheapest way to reintroduce this bug is not to edit `stripOuter` at
        all: it is to write `if (!this.input.value.trim()) return;` at the
        gate, which leaves every assertion about the function's regexes true
        while the client goes back to JS `trim()` and its Unicode whitespace
        set. Commenting the gate out is cheaper still. This is a match on a
        statement line, not an execution — it reads that the gate names
        `stripOuter` in live code, not that the answer is honored.
        """
        assert _blank_gate_is_live(), (
            'the blank-Enter gate is no longer a live '
            '`if (!this.stripOuter(...)) return;` statement: '
            "ScanCapture.stripOuter may still spell the server's trim rule "
            'correctly while nothing consults it, and every other assertion '
            'in this file would stay green')

    def test_the_client_does_not_fall_back_on_the_unicode_whitespace_set(self):
        """`trim()` and `\\s` are the same mistake spelled two ways.

        JS `trim()` strips VT, FF, NBSP and BOM, all of which the server keeps
        deliberately — `tests/e2e/test_wedge_scan.py` drives that difference
        through a real browser. `\\s` inside the class is the same widening
        without the obvious call, and `_decoded_class` maps it to `None` so it
        can never compare equal to a character.

        The `trim()` half is checked across the WHOLE file rather than inside
        `stripOuter`: every trimming decision in `scan-capture.js` is this one
        rule, so a `trim()` appearing anywhere in it is either the gate
        bypassing `stripOuter` or a second copy of the rule that agrees with
        neither side. The one-ended forms count too — `trimEnd()` is what a
        "fix" to only the trailing half of the rule would reach for, and it
        carries the same Unicode whitespace set as the two-ended call.
        """
        source = _source()
        found = JS_TRIM_CALL.search(source)
        assert found is None, (
            f'scan-capture.js calls {found.group(1)}(): the client now strips '
            f'the full Unicode whitespace set (VT, FF, NBSP, BOM) that the '
            f'server deliberately keeps, so those scans are dropped in the '
            f'browser with no request and no error')
        for characters in _trim_rules():
            assert None not in characters, (
                'ScanCapture.stripOuter uses `\\s` in its character class: '
                'that is JS trim()\'s Unicode whitespace set by another name, '
                'and it is wider than the server\'s SCAN_TRIM')


@pytest.mark.unit
class TestTheTripwireFailsLoudly:
    """The extraction refuses to report green when it has nothing to check."""

    def test_a_missing_function_is_an_assertion_not_a_silent_pass(self):
        """Anchor gone -> named failure, per the spec's edge-case matrix.

        A tripwire that matches nothing and passes is worse than no tripwire,
        because it reads as coverage. Verified by handing the extractor a
        source that genuinely lacks the anchor.
        """
        with pytest.raises(AssertionError, match='stripOuter is gone'):
            _strip_outer_source('// nothing here\n')

    def test_a_duplicated_function_is_an_assertion_not_a_silent_pass(self):
        """Two definitions means the one being read may not be the live one."""
        doubled = (
            '    stripOuter: function(value) {\n'
            "        return value.replace(/^[ \\t\\r\\n]+/, '')"
            ".replace(/[ \\t\\r\\n]+$/, '');\n"
            '    },\n'
        ) * 2
        with pytest.raises(AssertionError, match='exactly one'):
            _strip_outer_source(doubled)

    def test_an_unbounded_function_is_an_assertion_not_a_silent_pass(self):
        """The anchor is there but its terminator line is not.

        Without this, the slice would run to the end of the file and the
        comparison would be made against every regex in `scan-capture.js`.
        """
        with pytest.raises(AssertionError, match='could not find the end'):
            _strip_outer_source(
                '    stripOuter: function(value) {\n'
                '        return value.replace(/^[ \\t\\r\\n]+/, "");\n')

    def test_restructured_regexes_are_an_assertion_not_a_silent_pass(self):
        """Same for a `stripOuter` this module can no longer read.

        The function is present and correctly bounded, but expresses the rule
        without `/[...]/` literals — so there is nothing to compare and the
        honest answer is a failure naming that.
        """
        with pytest.raises(AssertionError, match='regex literal'):
            _trim_rules(
                '    stripOuter: function(value) {\n'
                '        return value.replace(SOME_OTHER_RULE, "")'
                '.replace(ANOTHER_RULE, "");\n'
                '    },\n')

    def test_a_widened_js_class_actually_fails_the_comparison(self):
        """The tripwire's own alarm, exercised rather than assumed.

        The whole file is worth nothing if a widened class still compares
        equal, so the drift it is built to catch is fed through the extractor
        here: `\\x0b` added to the leading rule is a character the server keeps.
        """
        widened = (
            '    stripOuter: function(value) {\n'
            '        return value.replace(/^[ \\t\\r\\n\\v]+/, "")'
            '.replace(/[ \\t\\r\\n]+$/, "");\n'
            '    },\n')
        leading, trailing = _trim_rules(widened)
        assert leading != set(SCAN_TRIM), (
            'a JS class carrying \\v compared equal to SCAN_TRIM: the escape '
            'decoding is dropping characters, so this tripwire would pass a '
            'genuinely widened client rule')
        assert trailing == set(SCAN_TRIM)

    def test_the_unicode_shorthand_sentinel_actually_fails(self):
        """`\\s` inside the class must never compare equal to a character.

        The sentinel in `JS_ESCAPES` is load-bearing and, against the real
        file, vacuously true — no `\\s` is there to find. Exercised here so a
        later "cleanup" that maps `\\s` to a space (every other value in that
        dict is a character) turns this red instead of letting
        `[ \\t\\r\\n\\s]` decode to exactly the server's set.
        """
        shorthand = (
            '    stripOuter: function(value) {\n'
            '        return value.replace(/^[ \\t\\r\\n\\s]+/, "")'
            '.replace(/[ \\t\\r\\n]+$/, "");\n'
            '    },\n')
        leading, _ = _trim_rules(shorthand)
        assert None in leading, (
            '`\\s` no longer decodes to the None sentinel, so a client rule '
            'carrying the whole Unicode whitespace set compares equal to '
            'SCAN_TRIM and this tripwire passes it')
        assert leading != set(SCAN_TRIM)

    def test_an_alternation_outside_the_class_is_an_assertion(self):
        """The widening a permissive extractor would step straight over.

        `/^[ \\t\\r\\n]+|^\\s+/` carries a character class that reads exactly
        right and a second alternative that strips the entire Unicode
        whitespace set. The full-match shape check is what turns it red.
        """
        alternation = (
            '    stripOuter: function(value) {\n'
            '        return value.replace(/^[ \\t\\r\\n]+|^\\s+/, "")'
            '.replace(/[ \\t\\r\\n]+$/, "");\n'
            '    },\n')
        with pytest.raises(AssertionError, match='not the expected'):
            _trim_rules(alternation)

    def test_a_regex_flag_is_an_assertion(self):
        """A flag changes the rule without touching the character class.

        `y` on the trailing rule makes it match only at `lastIndex`, which is
        `0` for a fresh literal, so it trims nothing at all; `m` on the leading
        rule makes `^` match after every newline, so an interior run is eaten.
        Both leave a class that reads exactly like the server's.
        """
        flagged = (
            '    stripOuter: function(value) {\n'
            '        return value.replace(/^[ \\t\\r\\n]+/m, "")'
            '.replace(/[ \\t\\r\\n]+$/y, "");\n'
            '    },\n')
        with pytest.raises(AssertionError, match='not the expected unflagged'):
            _trim_rules(flagged)

    def test_a_non_empty_replacement_is_an_assertion(self):
        """Replacing the run with a space rather than removing it.

        Both classes still name the server's four characters, but
        `stripOuter('   ')` then returns `' '`, which is truthy — so the blank
        gate never fires and a bare Enter posts a scan nobody scanned.
        """
        substituting = (
            '    stripOuter: function(value) {\n'
            '        return value.replace(/^[ \\t\\r\\n]+/, " ")'
            '.replace(/[ \\t\\r\\n]+$/, " ");\n'
            '    },\n')
        with pytest.raises(AssertionError, match='chained onto the returned'):
            _trim_rules(substituting)

    def test_a_dropped_replace_result_is_an_assertion(self):
        """The likeliest way to break this in JavaScript specifically.

        `String.prototype.replace` returns a new string and mutates nothing, so
        a `value.replace(...)` on its own line is a no-op. Two `.replace(`
        calls and two correctly shaped literals are still there; the leading
        trim simply never happens.
        """
        unchained = (
            '    stripOuter: function(value) {\n'
            '        value.replace(/^[ \\t\\r\\n]+/, "");\n'
            '        return value.replace(/[ \\t\\r\\n]+$/, "");\n'
            '    },\n')
        with pytest.raises(AssertionError, match='chained onto the returned'):
            _trim_rules(unchained)

    def test_an_early_return_before_the_chain_is_an_assertion(self):
        """A guarded bypass: live code, correct classes, no trim.

        The three dead-rule forms above are all either unreachable code or a
        visibly wrong chain. This one is neither — it reads like an ordinary
        fast path, a linter is happy with it, and for every input satisfying
        the condition `stripOuter` hands back untrimmed text while both regex
        literals still spell the server's set exactly. A `search()` for the
        return chain finds it further down and reports green; only requiring
        the chain to be the whole body catches it.
        """
        early_return = (
            '    stripOuter: function(value) {\n'
            '        if (value.length < 2) return value;\n'
            '        return value.replace(/^[ \\t\\r\\n]+/, "")'
            '.replace(/[ \\t\\r\\n]+$/, "");\n'
            '    },\n')
        with pytest.raises(AssertionError, match="function's only"):
            _trim_rules(early_return)

    def test_a_commented_out_blank_gate_is_not_live(self):
        """Disabling the gate costs two characters and no other test notices.

        A substring search for the gate's text finds it just as readily inside
        a comment, so the check is anchored to the start of a line AND run over
        comment-stripped source. Both comment forms are exercised: the line
        anchor alone defeats only `//`, since a `/* … */` wrapped around the
        gate leaves the gate's own line untouched and still matching at the
        start of a line.
        """
        live = '            if (!this.stripOuter(this.input.value)) return;\n'
        assert _blank_gate_is_live(live)
        assert not _blank_gate_is_live(f'            // {live.strip()}\n')
        assert not _blank_gate_is_live(f'            /*\n{live}            */\n')
        assert not _blank_gate_is_live(f'            /* {live.strip()} */\n')

    def test_a_hoisted_gate_argument_is_still_live(self):
        """The other half of that: a behavior-preserving edit stays green.

        Reading the field into a local before the gate changes nothing about
        which function decides "blank", and pinning the argument expression
        would report that refactor as a reintroduced bug.
        """
        assert _blank_gate_is_live(
            '            if (!this.stripOuter(raw)) return;\n')

    def test_two_leading_rules_are_an_assertion(self):
        """Both ends must still be trimmed, and by the rule for that end.

        Two leading rules leaves trailing padding on a scan the server trims,
        so the client's blank gate and the server disagree in the direction
        that posts a payload the server then refuses.
        """
        both_leading = (
            '    stripOuter: function(value) {\n'
            '        return value.replace(/^[ \\t\\r\\n]+/, "")'
            '.replace(/^[ \\t\\r\\n]+/, "");\n'
            '    },\n')
        with pytest.raises(AssertionError, match='not the expected'):
            _trim_rules(both_leading)
