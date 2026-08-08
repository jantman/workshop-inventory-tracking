"""Small SQL helpers shared by the services.

One function, and it is here rather than in either caller because both the
catalogue and the shared vocabulary need it and two copies of an escaping rule
are two chances to fix a bug once.
"""


def escape_like(value: str) -> str:
    """Escape LIKE wildcards in operator-supplied filter text.

    A search for ``10%`` or a specification value of ``5%`` must match that
    literal string rather than acting as a wildcard. This is correctness, not
    defence -- an unescaped ``%`` returns the wrong answers, and nobody is
    attacking a home LAN.

    Args:
        value: The operator's text, as typed.

    Returns:
        The text with ``\\``, ``%`` and ``_`` escaped, for use with
        ``like(..., escape='\\\\')``.
    """
    return (
        value.replace('\\', '\\\\')
        .replace('%', '\\%')
        .replace('_', '\\_')
    )
