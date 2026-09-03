"""The application's clock, and the one distinction it exists to enforce.

Two kinds of value get stored in a ``DateTime`` column, and they are not the
same kind of thing:

* An **instant the application recorded** -- when a row was created, last
  changed, counted, flagged; when a photo was stored. Nobody typed it, nobody
  reads it as a wall-clock reading, and its only use is comparison: against
  another recorded instant, or against now. Those come from :func:`utc_now`.
* A **day the operator stated**, or accepted as "today" -- the day an order was
  placed, the day a shipment arrived. It is displayed as a day, checked against
  paper, and belongs to the operator's own calendar. Those come from
  :func:`local_now`.

Mixing them is what issue #134 was: ``products`` took ``date_added`` from the
database server's clock and ``quantity_updated_at`` from the application's
local one, so a single UPDATE wrote two columns four hours apart. Nothing
displayed either, so nothing looked wrong.

**Both return naive datetimes.** MariaDB's ``DATETIME`` stores no offset and
SQLAlchemy's ``DateTime(timezone=True)`` is a no-op there, so an aware value is
a fiction the database will not keep -- and a naive/aware comparison raises
``TypeError``, which this codebase has already taken as a production 500 once
(see ``app/models.py`` ``_naive``, PR #128). Naive means the value that comes
back is the value that went in.

There is deliberately no parameter, no configuration read, no injectable clock
and no freeze hook: tests patch the module attribute, which needs no
affordance in production code.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """The current instant in UTC, naive, for recording that something happened.

    Every persisted recorded timestamp comes from here, and so does every
    comparison against one -- both ends of an age subtraction have to share a
    basis or the answer is nonsense.

    Not ``datetime.utcnow()``, which is deprecated from Python 3.12 and returns
    the same thing by a route that is going away.

    Returns:
        The current UTC time with ``tzinfo`` stripped.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def local_now() -> datetime:
    """The current instant on the operator's wall clock, naive.

    For defaulting a calendar day the operator did not type. Converting these
    to UTC would push an order captured at nine in the evening onto the
    following day, which is a visible bug traded for an invisible one.

    This is exactly what a bare ``datetime.now()`` returns. It exists to be
    *named*: after issue #134, a bare ``datetime.now()`` in a service reads as
    a mistake, and the handful of sites that mean it need to say so where they
    are rather than in a comment a later sweep can miss.

    Returns:
        The current local time, naive, as ``datetime.now()`` gives it.
    """
    return datetime.now()
