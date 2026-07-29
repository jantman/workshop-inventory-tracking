"""
Human-readable age of a timestamp (Story 5.1, FR25).

This module is the single source of truth for turning a stored verification
timestamp into the phrase the operator reads beside the value it verifies. It is
a PURE module: standard library only, no Flask/DB/framework imports, no I/O, and
no exceptions of its own. Routes call it and hand the finished string to the
template (AD-5); templates never compute an age.

Why a phrase and not a date
---------------------------
FR25 asks for the AGE of the last manual assertion to be surfaced, not
corrected. "3 months ago" answers the only question the operator has — how much
to trust the number beside it — where a bare date makes them do the subtraction
themselves, every time they read the page.

The unit ladder
---------------
One phrase, chosen by the largest unit that fits, and deliberately coarse:

- under a minute      -> ``just now``
- under an hour       -> ``N minute ago`` / ``N minutes ago``
- under a day         -> ``N hour(s) ago``
- under 30 days       -> ``N day(s) ago``
- under 365 days      -> ``N month(s) ago``   (a month is exactly 30 days)
- otherwise           -> ``N year(s) ago``    (a year is exactly 365 days)

Integer arithmetic only, and every boundary truncates rather than rounds: an age
of 59 minutes reads ``59 minutes ago``, never ``1 hour ago``. A count is never
inflated, so the phrase never claims a count is fresher OR staler than it is by
more than one unit of its own size.

The 30-day month and the 365-day year are nominal on purpose. Calendar months
have four different lengths and years have two, so a calendar-aware answer would
make the same elapsed interval read differently depending on which month it
started in — a distinction with no meaning at all for "how stale is this count".
The one visible consequence is that 360 to 364 days reads ``12 months ago``
rather than rolling over to a year; that is the honest reading of a nominal
month, and rounding it up would be the arithmetic lying to keep the ladder tidy.

Boundary cases
--------------
``None`` in, ``None`` out — an untracked quantity has no verification stamp, and
the caller renders nothing rather than a phrase about a time that does not
exist. A stamp in the FUTURE (a clock adjustment, a hand-edited row) reads
``just now`` rather than a negative count: the phrase describes staleness, and
"not stale" is the truthful answer for a stamp that has not happened yet.

Both arguments are naive local ``datetime``s, matching what
``CatalogService`` writes with ``datetime.now()`` — the stamp and the comparison
therefore read the same clock. Mixing an aware and a naive value raises
``TypeError`` out of the subtraction, which is the correct loud failure: there
is no timezone this module could assume that would not silently shift an age.

    >>> from datetime import datetime, timedelta
    >>> now = datetime(2026, 7, 29, 12, 0, 0)
    >>> describe_age(now, now)
    'just now'
    >>> describe_age(now - timedelta(seconds=59), now)
    'just now'
    >>> describe_age(now - timedelta(seconds=60), now)
    '1 minute ago'
    >>> describe_age(now - timedelta(minutes=59), now)
    '59 minutes ago'
    >>> describe_age(now - timedelta(minutes=60), now)
    '1 hour ago'
    >>> describe_age(now - timedelta(hours=23), now)
    '23 hours ago'
    >>> describe_age(now - timedelta(hours=24), now)
    '1 day ago'
    >>> describe_age(now - timedelta(days=29), now)
    '29 days ago'
    >>> describe_age(now - timedelta(days=30), now)
    '1 month ago'
    >>> describe_age(now - timedelta(days=364), now)
    '12 months ago'
    >>> describe_age(now - timedelta(days=365), now)
    '1 year ago'
    >>> describe_age(now - timedelta(days=730), now)
    '2 years ago'

Nothing to show, and nothing that has happened yet:

    >>> describe_age(None, now) is None
    True
    >>> describe_age(now + timedelta(days=5), now)
    'just now'
"""

from datetime import datetime
from typing import Optional

# The nominal calendar units. Named rather than inlined so the module docstring
# and the arithmetic cannot drift, and so a reader who disagrees with the
# nominal choice can see it is a choice.
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR
DAYS_PER_MONTH = 30
DAYS_PER_YEAR = 365

# The one phrase that carries no count.
JUST_NOW = 'just now'


def _plural(count: int, unit: str) -> str:
    """`'1 hour ago'` / `'2 hours ago'` — the only pluralization rule here.

    Every unit this module names is a regular English noun, so a bare `'s'` is
    the whole rule; it lives in one place so a new unit cannot be added with its
    plural spelled by hand.
    """
    return f'{count} {unit}{"" if count == 1 else "s"} ago'


def describe_age(then: Optional[datetime],
                 now: Optional[datetime] = None) -> Optional[str]:
    """The age of `then` as an operator-readable phrase, or None.

    Args:
        then: The timestamp being described (naive local), or None.
        now: The instant to measure against; defaults to `datetime.now()`, the
            same clock `CatalogService` stamps `quantity_verified_at` with.
            Passed explicitly by tests and by any caller rendering several ages
            on one page, so every phrase on that page is measured from one
            instant rather than from as many instants as there are values.

    Returns:
        One of `just now`, `N minute(s) ago`, `N hour(s) ago`, `N day(s) ago`,
        `N month(s) ago`, `N year(s) ago` — or None when `then` is None.
    """
    if then is None:
        return None
    if now is None:
        now = datetime.now()

    # int() truncates toward zero, which for a non-negative delta is the floor
    # the ladder wants. A NEGATIVE delta (a stamp in the future) is caught by the
    # very first rung — anything under a minute, backwards included, is
    # `just now` — so no later rung ever divides one and no phrase can count
    # backwards. That is why there is no explicit max(0, …) here: the clamp the
    # docstring promises is the ladder's own first comparison.
    seconds = int((now - then).total_seconds())
    if seconds < SECONDS_PER_MINUTE:
        return JUST_NOW
    if seconds < SECONDS_PER_HOUR:
        return _plural(seconds // SECONDS_PER_MINUTE, 'minute')
    if seconds < SECONDS_PER_DAY:
        return _plural(seconds // SECONDS_PER_HOUR, 'hour')

    days = seconds // SECONDS_PER_DAY
    if days < DAYS_PER_MONTH:
        return _plural(days, 'day')
    if days < DAYS_PER_YEAR:
        return _plural(days // DAYS_PER_MONTH, 'month')
    return _plural(days // DAYS_PER_YEAR, 'year')
