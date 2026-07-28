"""pin explicit charset and collation

Revision ID: a977ca7315df
Revises: 68707d1f48bf
Create Date: 2026-07-27 23:38:25.677470

DW-34 — pin an explicit charset and per-column collation on every table.

Until this revision nothing in the schema declared a charset or a collation, so
every string comparison the catalog depends on — `product_identifiers`
uniqueness, `product_tags` uniqueness, `products.category_path` prefix
matching, `products.internal_id` scan lookup — ran under whatever the deployed
server's `@@collation_database` happened to be. `set_product_tags`' collision
handling, `list_tags`' Python-side grouping and `rename_category_path`'s
non-canonical-overlap refusal are all written against `utf8mb4_unicode_ci`
semantics *specifically*, and MariaDB 11.8's own built-in default is
`utf8mb4_uca1400_ai_ci` — so the code was correct only by accident of how each
database happened to be created. This revision makes that a property of the
schema.

Two decisions, mirrored in `app/database.py` so `create_all` and a migrated
database describe one schema:

* Every table becomes `utf8mb4` / `utf8mb4_unicode_ci` (folding case AND
  accents), which is the semantics the catalog service is written against.
* `products.internal_id` alone becomes `utf8mb4_bin`. `is_valid_internal_id` is
  deliberately case-sensitive ("silently upper-casing input would let two
  different scanned strings map to one identifier"), so a folding collation
  would make MariaDB disagree with the validator that admitted the value and
  with SQLite. Binary makes `resolve_scan`'s `Product.internal_id == value`
  behave identically on both backends: a lower-cased scan does not resolve and
  falls through to a free-text search (DW-73).

**What `CONVERT TO CHARACTER SET` does.** It REBUILDS each table — a full copy
under a metadata lock, and for `photos` and `attachments` the cost is
proportional to the stored MEDIUMBLOB bytes, not to the row count, even though
the only columns being converted there are `filename`, `content_type` and
`sha256_hash`. It converts every CHAR/VARCHAR/TEXT column to the named charset
and collation, overriding any collation previously set on those columns. It
does NOT touch BLOB/`MEDIUMBLOB` (`photos.*_data`, `attachments.content`),
numeric or datetime columns. It DOES touch `products.attributes`, because
MariaDB implements `JSON` as a `LONGTEXT` alias with a fixed `utf8mb4_bin`
collation — so that one column is restored explicitly afterwards, in both
directions, to keep the migrated schema equal to the `create_all` one.

**Only an already-utf8mb4 schema is converted; anything else is REFUSED.**
Stored bytes are then unchanged and the conversion changes comparison semantics
only, which is every environment this repo configures. `_abort_on_wide_charset`
enforces that up front, and it is not defensiveness for its own sake — widening
from a narrower charset does three bad things this revision has no good answer
for:

* It grows index key bytes. The widest index here is the composite
  `uq_product_identifiers_type_value_scope` at 542 chars (2168 bytes under
  utf8mb4), inside InnoDB's 3072-byte `DYNAMIC` limit but well past the
  767-byte limit that `COMPACT`/`REDUNDANT` row formats impose — and a latin1
  deployment is exactly the vintage likely to be on one of those. That failure
  (`ERROR 1071`) would land on whichever table happened to be Nth in the list,
  stranding the half-converted schema the pre-flight exists to prevent.
* It silently promotes `TEXT` to `MEDIUMTEXT` (and `VARCHAR` toward its byte
  ceiling), because MySQL preserves byte capacity rather than character
  capacity across a widening. The migrated schema would then differ from the
  `create_all` one on `inventory_items.notes`, `material_taxonomy.aliases`,
  `material_taxonomy.notes` and `products.notes` — permanently, and invisibly
  to every check here, which compares collations and charsets rather than
  column types. Keeping those two schemas equal is the entire point of the
  revision.
* It makes the downgrade unreachable. `downgrade()` refuses to convert back to
  a narrower database default (see below), so a latin1 deployment that upgraded
  could never reverse.

The refusal names the offending tables and columns and is actionable: convert
them to utf8mb4 deliberately (moving to the `DYNAMIC` row format first, which
is where the index-length question gets decided with a human present), then
re-run. Narrowing is not attempted either — the check is "everything is already
utf8mb4", not "everything is at most utf8mb4".

**Why the pre-flight check runs first.** MySQL/MariaDB commit DDL implicitly, so
there is no transaction to roll back: a duplicate-key failure on the fourth
`ALTER TABLE` would leave three tables converted and the rest not — a schema no
revision describes. `_abort_on_collisions` therefore reads every UNIQUE index
that spans a string column BEFORE any DDL is issued and raises a `RuntimeError`
naming the table, the index and the offending values, with nothing changed.
Rows that are distinct today can only collide under the target because it
folds; the index itself guarantees they are distinct under the current
collation, so "more than one row per folded key" is exactly the set of new
collisions.

The same "nothing changed" argument is why the three structural checks run too.
`TABLES` below is a fixed list and the two `MODIFY` statements after the loop
name two specific columns, while the schema all of that runs against is a
deployed one. A table a deployment has dropped (`_abort_on_missing_tables`), a
column it lacks or has redefined (`_abort_on_missing_columns`), or a FOREIGN KEY
it has added over a character column (`_abort_on_string_foreign_keys`, which
`CONVERT TO CHARACTER SET` breaks by changing one side of the pair before the
other) would otherwise surface as `ERROR 1146`, `1054` or `3780` partway down
the conversion — with every earlier table already converted and committed —
rather than as a refusal with nothing done. `_abort_on_missing_columns` also
pins the SHAPE of `products.internal_id`, because MySQL's `MODIFY` is a
replacement rather than a patch: the statement below restates `VARCHAR(32) NOT
NULL` from this revision's models, so a deployment whose column is wider would
be silently truncated by the very statement meant only to change its collation.

Those indexes are DISCOVERED from `information_schema`, not listed here. That
is the point rather than a convenience: the schema this check protects is a
*deployed* one, which is not required to match the models. This repo documents
one such divergence itself — `3b7d76c3fb8d`'s upgrade is a no-op "kept for
consistency with existing database instances that may have the constraint", so
some databases still carry `uq_ja_id_active` over `inventory_items(ja_id,
active)`. A hard-coded list would silently skip it, and every future table
would have to be remembered into it.

`uq_products_internal_id` is covered too, even though `internal_id` ends up
`utf8mb4_bin` — which only ever LOOSENS uniqueness. It matters because of the
transient: the table-wide `CONVERT TO` below puts `internal_id` under
`utf8mb4_unicode_ci` first and the `MODIFY` that pins it binary comes after, so
two ids differing only in case would fail the conversion. Unreachable in
practice (issued ids are upper-case Crockford base-32), but the whole point of
the pre-flight is that the abort is actionable rather than mid-conversion.

The downgrade runs the SAME check against the collation it is about to restore,
for the same reason in the opposite direction: going down, `internal_id` moves
from binary to a folding default, which TIGHTENS uniqueness, and `products` is
not the first table in the list. It additionally refuses to run at all when the
database default is narrower than utf8mb4, because that conversion replaces
unrepresentable characters with `?` — silent, irreversible data loss dressed up
as a schema change.

**A cross-column consistency note, stated here so it is not rediscovered.**
`product_identifiers.value` folds while `products.internal_id` does not, so in
principle two internal ids differing only in case could both pass
`uq_products_internal_id` and then collide on their derived global `INTERNAL`
identifier rows. Unreachable in practice for the same reason — the generator
only ever emits upper-case, and `create_product` retries on any UNIQUE
violation — but the asymmetry is deliberate, not an oversight.

MariaDB/MySQL-only. Both directions no-op on any other dialect: SQLite has
binary semantics, no per-table charset, and nothing to pin (making the two
backends agree is DW-72, an app-level engine change, not this). Alembic's
offline/`--sql` mode is not supported, here or anywhere in this chain — four
earlier revisions already read rows through `op.get_bind()` (`8213852b0b94`,
`56dc95692b79`, `f8e66632ee42`, `5aeb89e22451`; DW-197) — and the pre-flight
is inherently unrunnable without a live connection, so it is refused explicitly
rather than emitting a script whose safety check silently did not happen.
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Alembic's own runtime logger, so anything reported here reaches an operator
# through the same handler as `Running upgrade ... -> ...`.
logger = logging.getLogger('alembic.runtime.migration')

# revision identifiers, used by Alembic.
revision: str = 'a977ca7315df'
down_revision: Union[str, None] = '68707d1f48bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# SQLAlchemy reports MariaDB as 'mysql' through a `mysql+pymysql://` URL and as
# 'mariadb' through a `mariadb+pymysql://` one. Both are accepted so the URL
# scheme in someone's `.env` cannot silently turn this migration into a no-op
# against the very backend it exists for.
MYSQL_DIALECTS = frozenset({'mysql', 'mariadb'})

TARGET_CHARSET = 'utf8mb4'
TARGET_COLLATION = 'utf8mb4_unicode_ci'
# The one per-column exception; see the module docstring.
BINARY_COLLATION = 'utf8mb4_bin'

# The pseudo-charset BLOB/VARBINARY columns report. Servers disagree on whether
# `information_schema.columns.character_set_name` is NULL or the literal string
# 'binary' for them, so both spellings are treated as "not a character column":
# such a column is untouched by `CONVERT TO CHARACTER SET` and rejects a
# `COLLATE utf8mb4_*` clause outright.
BINARY_CHARSET = 'binary'

# Every table that exists at this revision, parent-before-child. Order is
# immaterial to correctness (all foreign keys here are over INTEGER columns, so
# no conversion can make a referencing and a referenced column incompatible),
# but a stable order makes a partially-applied failure readable in the log.
TABLES = (
    'inventory_items',
    'material_taxonomy',
    'photos',
    'item_photo_associations',
    'products',
    'purchases',
    'attachments',
    'product_identifiers',
    'product_tags',
)

# `products.attributes` is the schema's only JSON column (NFR2). MariaDB
# implements JSON as a LONGTEXT alias, so `CONVERT TO CHARACTER SET` rewrites it
# like any other text column; re-issuing the type restores the fixed
# `utf8mb4_bin` collation a `JSON` column is created with, which is what
# `Base.metadata.create_all` produces. Nullable, matching the model.
JSON_COLUMNS = (('products', 'attributes', 'JSON NULL'),)

# The columns the two `MODIFY` statements after the conversion loop name, as
# ``(table, column, {acceptable data_type}, is_nullable)``. `_abort_on_missing_
# columns` refuses unless the deployment matches, for the reason the module
# docstring gives: `MODIFY` replaces a definition rather than patching it, and
# both statements run AFTER nine implicitly-committed `ALTER`s.
#
# `data_type` rather than `column_type` because the two servers disagree about
# the latter for JSON (MariaDB reports the `LONGTEXT` it aliases, MySQL reports
# `json`); the length is pinned separately, as it is the part a `MODIFY` can
# silently truncate.
REQUIRED_COLUMNS = (
    ('products', 'internal_id', {'varchar'}, 'NO', 32),
    ('products', 'attributes', {'json', 'longtext'}, 'YES', None),
)

# How many colliding groups to SHOW per index. The reported TOTAL is counted
# separately and is always the real one -- an operator who fixes the ten rows
# named here and re-runs must not be surprised by a second abort with no way to
# size the remaining work.
MAX_REPORTED_GROUPS = 10

# GROUP_CONCAT truncates at `group_concat_max_len` (1024 bytes by default) with
# only a warning, which would quietly drop rows from an abort message whose
# entire job is to name them. This is the value asked for; the value actually
# used is `_group_concat_cap`, because the server bounds the result by
# `max_allowed_packet` as well and raising only this one would leave the
# truncation undetectable again on a server configured below it.
GROUP_CONCAT_MAX_LEN = 1048576

# How the offending values are rendered: columns of one row joined by the
# first, the colliding rows of one group by the second.
COLUMN_SEPARATOR = '|'
ROW_SEPARATOR = ' <> '


def _unique_indexes(bind):
    """Every unique index in the live schema that spans a string column.

    Read from `information_schema` rather than listed in this file, for the
    reason the module docstring gives: the schema being protected is a deployed
    one and is not required to match the models.

    Yields ``(table, index, key_terms, nullable_columns)`` where ``key_terms``
    are ``(sql_expression, collatable)`` pairs in key order:

    * A column with no character set (INT, DATE, VARBINARY, ...) joins the
      GROUP BY as itself, flagged ``collatable=False`` -- the conversion cannot
      change how it compares. The flag is load-bearing rather than tidy: a
      ``COLLATE utf8mb4_unicode_ci`` appended to a binary-charset column is
      `ERROR 1253`, not a no-op, so a deployed index mixing a VARCHAR with a
      VARBINARY column would crash the pre-flight instead of passing it.
    * A string column is wrapped in ``CONVERT(... USING utf8mb4)`` so the check
      cannot itself fail on an "illegal mix of collations", which is a real risk
      precisely because the collations in a deployed database are unknown here.
    * A prefix index (``sub_part``) compares only its first N characters, so the
      GROUP BY must too -- grouping on the whole column would UNDER-report. This
      applies to a prefix over a BINARY column as much as over a character one:
      the binary member cannot itself start folding, but it is still only its
      first N bytes that decide whether two rows share the key, so grouping on
      the whole value would hide a pair that the character member folds
      together.

    ``nullable_columns`` are exactly that: the key columns declared NULLable, so
    the caller can exclude their NULL rows. MySQL and SQLite both allow
    unlimited NULLs in a UNIQUE index, so a row with a NULL anywhere in the key
    is exempt from uniqueness and can neither collide nor be reported as
    colliding. Getting this wrong is not a subtle failure: `purchases` has a
    nullable `request_key` and, until Epic 7, most rows leave it NULL, so a
    check that grouped them would refuse the upgrade on essentially every real
    deployment.

    Indexes over an expression rather than a column (MySQL 8 functional
    indexes) report a NULL ``column_name``; they are skipped and named by the
    caller instead of being silently treated as covered.
    """
    rows = bind.execute(sa.text(
        'SELECT s.table_name, s.index_name, s.seq_in_index, s.column_name, '
        '       s.sub_part, c.character_set_name, c.is_nullable '
        'FROM information_schema.statistics s '
        'LEFT JOIN information_schema.columns c '
        '  ON c.table_schema = s.table_schema '
        ' AND c.table_name = s.table_name '
        ' AND c.column_name = s.column_name '
        'WHERE s.table_schema = database() AND s.non_unique = 0 '
        '  AND s.table_name IN :tables '
        'ORDER BY s.table_name, s.index_name, s.seq_in_index'
    ).bindparams(sa.bindparam('tables', list(TABLES), expanding=True)))

    grouped = {}
    for table, index, _seq, column, sub_part, charset, nullable in rows:
        grouped.setdefault((table, index), []).append(
            (column, sub_part, charset, nullable))

    checkable, skipped = [], []
    for (table, index), members in grouped.items():
        if any(column is None for column, _, _, _ in members):
            skipped.append(f'{table}.{index}')
            continue
        if not any(charset and charset != BINARY_CHARSET
                   for _, _, charset, _ in members):
            # No character column: the collation change cannot affect this key.
            continue

        key_terms, nullable_columns = [], []
        for column, sub_part, charset, nullable in members:
            term = f'`{column}`'
            collatable = bool(charset) and charset != BINARY_CHARSET
            if collatable:
                term = f'CONVERT({term} USING {TARGET_CHARSET})'
            if sub_part:
                term = f'LEFT({term}, {int(sub_part)})'
            key_terms.append((term, collatable))
            if nullable == 'YES':
                nullable_columns.append(column)
        checkable.append((table, index, key_terms, nullable_columns))

    return sorted(checkable), sorted(skipped)


def _collisions(bind, table, index, key_terms, nullable_columns, collation, cap):
    """``(total, samples)`` for rows that are distinct now and collide after.

    Two queries against the same grouping, deliberately: the total is what
    tells an operator how much work the cleanup is, and the samples are what
    tell them where to start. Reporting `len(samples)` as the total -- which a
    single `LIMIT`ed query is all it can give -- would understate a 50,000-row
    problem as ten and send the operator round the loop again.

    The sample query is ORDERed before it is LIMITed, which matters for the same
    operator loop: an unordered `LIMIT` lets InnoDB return a different arbitrary
    ten on every run, so someone fixing the reported rows and re-running could
    be shown a fresh ten each time with no way to tell whether they were making
    progress.
    """
    where = ''
    if nullable_columns:
        where = ' WHERE ' + ' AND '.join(
            f'`{column}` IS NOT NULL' for column in nullable_columns)

    # Only the character terms are collated. Appending COLLATE to a numeric
    # column merely forces a pointless cast, but appending it to a binary one is
    # ERROR 1253 -- see `_unique_indexes`.
    grouping = ', '.join(f'{term} COLLATE {collation}' if collatable else term
                         for term, collatable in key_terms)
    duplicates = (f'SELECT 1 FROM `{table}`{where} '
                  f'GROUP BY {grouping} HAVING COUNT(*) > 1')

    total = bind.execute(sa.text(
        f'SELECT COUNT(*) FROM ({duplicates}) AS d')).scalar()
    if not total:
        return 0, []

    display = ', '.join(term for term, _ in key_terms)
    samples = [row[0] for row in bind.execute(sa.text(
        f"SELECT GROUP_CONCAT(CONCAT_WS('{COLUMN_SEPARATOR}', {display}) "
        f"SEPARATOR '{ROW_SEPARATOR}') AS `values` "
        f'FROM `{table}`{where} '
        f'GROUP BY {grouping} HAVING COUNT(*) > 1 '
        f'ORDER BY {grouping} '
        f'LIMIT {MAX_REPORTED_GROUPS}'))]

    # A key that includes a binary column makes CONCAT_WS -- and therefore
    # GROUP_CONCAT -- return binary, which the driver hands back as `bytes`.
    # Decoded with 'replace' rather than strictly: this is a diagnostic string
    # for a human, and a `UnicodeDecodeError` here would replace the actionable
    # abort with a traceback from the code that exists to produce it.
    decoded = [sample.decode('utf-8', 'replace') if isinstance(sample, bytes)
               else sample for sample in samples]

    # GROUP_CONCAT truncates at the cap with only a warning, and a silently
    # shortened list is the one thing this message must not produce. Detected by
    # length rather than by `@@warning_count`, which the ORDER BY and the
    # server's own housekeeping can both perturb. Measured on the ORIGINAL bytes
    # where there were any, because the cap the server applied was a byte one
    # and a lossy decode does not preserve the length it truncated at.
    return total, [
        text if len(raw if isinstance(raw, bytes) else text.encode('utf-8')) < cap
        else text + ' ...(truncated)'
        for raw, text in zip(samples, decoded)]


def _group_concat_cap(bind) -> int:
    """The number of bytes a ``GROUP_CONCAT`` result can actually reach here.

    `group_concat_max_len` is the limit this migration raises, but it is not the
    only one: the server also bounds the result by `max_allowed_packet`, which
    is commonly 1 MiB or less and is NOT something a migration should be
    changing. Raising only the first would restore exactly the defect the raise
    exists to remove -- a sample silently shortened by a limit the truncation
    check does not know about, in a message whose whole job is to name every
    offending row.
    """
    allowed = bind.execute(sa.text('SELECT @@max_allowed_packet')).scalar()
    return min(GROUP_CONCAT_MAX_LEN, int(allowed))


def _abort_on_collisions(bind, charset, collation) -> None:
    """Raise before any DDL if converting to ``collation`` would break a UNIQUE.

    Every index is checked before anything is raised, so one run reports every
    problem rather than making an operator rediscover them one abort at a time.
    """
    cap = _group_concat_cap(bind)
    previous = bind.execute(
        sa.text('SELECT @@session.group_concat_max_len')).scalar()
    bind.execute(sa.text(f'SET SESSION group_concat_max_len = {cap}'))
    try:
        indexes, skipped = _unique_indexes(bind)
        problems = []
        for table, index, key_terms, nullable_columns in indexes:
            total, samples = _collisions(
                bind, table, index, key_terms, nullable_columns, collation, cap)
            if total:
                problems.append(
                    f'{table}.{index}: {total} colliding group(s), showing '
                    f'{len(samples)} -> ' + '; '.join(samples))
    finally:
        # Restored because this is Alembic's own connection: every later
        # revision in the same `upgrade head` run inherits the session, and a
        # 1 MiB GROUP_CONCAT budget is not something they asked for.
        bind.execute(sa.text(
            f'SET SESSION group_concat_max_len = {int(previous)}'))

    # Announced whether or not anything collided. Folding it into the failure
    # message alone would mean the one outcome where it matters -- the migration
    # proceeding, having not checked an index -- is the one that stays silent.
    if skipped:
        logger.warning(
            'Revision %s did not check these UNIQUE indexes for collisions '
            'because they are over an expression rather than a column: %s. '
            'Verify them by hand if this deployment has any.',
            revision, ', '.join(skipped))

    if problems:
        raise RuntimeError(
            f'Refusing to convert the schema to {charset}/{collation}: rows '
            f'that are distinct under the current collation would become '
            f'duplicates under the target one, and MySQL commits DDL '
            f'implicitly, so a failure partway through would strand a '
            f'half-converted schema. NOTHING HAS BEEN CHANGED. Merge or edit '
            f'the rows below, then re-run. Values are rendered as columns '
            f'joined by {COLUMN_SEPARATOR!r} and colliding rows joined by '
            f'{ROW_SEPARATOR!r}. ' + ' | '.join(problems)
            + (f' NOT CHECKED (indexes over an expression rather than a '
               f'column): {", ".join(skipped)}.' if skipped else ''))


def _abort_on_missing_tables(bind) -> None:
    """Raise before any DDL if the deployment lacks a table ``TABLES`` names.

    ``TABLES`` is a fixed list while the schema it converts is a deployed one.
    A table dropped out from under the chain would otherwise surface as
    `ERROR 1146` from whichever `ALTER` reached it, with every earlier table in
    the list already converted and committed.

    Restricted to `BASE TABLE` because `information_schema.tables` also lists
    VIEWs: a view left behind under a name this revision converts would satisfy
    a bare presence check and then fail the `ALTER` with `ERROR 1347` in exactly
    the mid-loop state this check exists to make unreachable.
    """
    present = {row[0] for row in bind.execute(sa.text(
        'SELECT table_name FROM information_schema.tables '
        "WHERE table_schema = database() AND table_type = 'BASE TABLE'"))}
    missing = [table for table in TABLES if table not in present]
    if missing:
        raise RuntimeError(
            f'Refusing to run revision {revision}: this database is missing '
            f'{", ".join(missing)} as a base table, which every revision up to '
            f'this one creates. NOTHING HAS BEEN CHANGED. Restore the table(s) '
            f'or rebuild the schema from the chain, then re-run.')


def _abort_on_missing_columns(bind) -> None:
    """Raise before any DDL unless the columns the ``MODIFY``s name are as here.

    Those two statements run AFTER the nine implicitly-committed conversions, so
    they are the only DDL in this revision with nothing in front of it -- a
    column a deployment has dropped surfaces as `ERROR 1054` with the whole
    schema already converted. And because MySQL's `MODIFY` is a replacement
    rather than a patch, a column that merely differs in SHAPE is worse than a
    missing one: `MODIFY internal_id VARCHAR(32) NOT NULL` restates this
    revision's definition, so a deployment carrying a wider column would have it
    silently truncated by a statement whose only intended effect is a collation.
    """
    observed = {(row[0], row[1]): (row[2], row[3], row[4])
                for row in bind.execute(sa.text(
                    'SELECT table_name, column_name, data_type, is_nullable, '
                    '       character_maximum_length '
                    'FROM information_schema.columns '
                    'WHERE table_schema = database() AND table_name IN :tables'
                ).bindparams(
                    sa.bindparam('tables', list(TABLES), expanding=True)))}

    wrong = {}
    for table, column, types, nullable, length in REQUIRED_COLUMNS:
        actual = observed.get((table, column))
        if actual is None:
            wrong[f'{table}.{column}'] = 'missing'
            continue
        data_type, is_nullable, max_length = actual
        if (data_type.lower() not in types or is_nullable != nullable
                or (length is not None and max_length != length)):
            wrong[f'{table}.{column}'] = (
                f'{data_type}({max_length}) nullable={is_nullable}, expected '
                f'one of {sorted(types)}({length}) nullable={nullable}')

    if wrong:
        raise RuntimeError(
            f'Refusing to run revision {revision}: it re-issues these column '
            f'definitions in full after converting every table, and MySQL '
            f'`MODIFY` REPLACES a definition rather than patching it, so a '
            f'deployment that disagrees would be silently redefined -- after '
            f'nine ALTERs have already been committed. NOTHING HAS BEEN '
            f'CHANGED. Problems: {wrong}.')


def _abort_on_string_foreign_keys(bind) -> None:
    """Raise before any DDL if a FOREIGN KEY here is over a character column.

    `CONVERT TO CHARACTER SET` rewrites the charset of every character column,
    and MySQL refuses to leave a referencing and a referenced column on
    different ones (`ERROR 3780`/`1833`). Both sides of such a key would be
    converted by the loop below, but SEQUENTIALLY -- so whichever table comes
    first breaks the pair and its own `ALTER` fails, mid-loop.

    The module docstring's "all foreign keys here are over INTEGER columns" is a
    statement about the MODELS. This check protects a DEPLOYED schema, which is
    not required to match them -- the same reason `_unique_indexes` discovers
    indexes instead of listing them.
    """
    offenders = {}
    for table, constraint, column, charset in bind.execute(sa.text(
            'SELECT k.table_name, k.constraint_name, k.column_name, '
            '       c.character_set_name '
            'FROM information_schema.key_column_usage k '
            'JOIN information_schema.columns c '
            '  ON c.table_schema = k.table_schema '
            ' AND c.table_name = k.table_name '
            ' AND c.column_name = k.column_name '
            'WHERE k.table_schema = database() '
            '  AND k.referenced_table_name IS NOT NULL '
            '  AND (k.table_name IN :tables '
            '       OR k.referenced_table_name IN :tables) '
            '  AND c.character_set_name IS NOT NULL '
            '  AND c.character_set_name <> :binary'
    ).bindparams(sa.bindparam('tables', list(TABLES), expanding=True),
                 sa.bindparam('binary', BINARY_CHARSET))):
        offenders[f'{table}.{column} ({constraint})'] = charset

    if offenders:
        raise RuntimeError(
            f'Refusing to run revision {revision}: these FOREIGN KEY columns '
            f'carry a character set, and converting the tables one at a time '
            f'would leave a referencing and a referenced column disagreeing '
            f'about it, which MySQL rejects (ERROR 3780) partway down the '
            f'conversion: {offenders}. NOTHING HAS BEEN CHANGED. Drop the '
            f'key(s), convert both sides deliberately, then re-run.')


def _abort_on_wide_charset(bind) -> None:
    """Raise before any DDL unless the schema is already ``utf8mb4`` throughout.

    See the module docstring: converting a narrower charset is a widening, and
    a widening breaks index key limits on `COMPACT`/`REDUNDANT` row formats,
    silently promotes `TEXT` to `MEDIUMTEXT` (diverging permanently from the
    `create_all` schema this revision exists to match), and leaves the
    downgrade unreachable. Refusing is the only one of those four outcomes an
    operator can act on.

    Both levels are checked. The per-column charset is what the conversion
    actually rewrites, and the table default is what a column added later would
    inherit -- a table defaulting to latin1 with no character columns yet would
    pass a column-only check and then quietly hand the next migration a latin1
    column.
    """
    wrong = {}
    for table, collation in bind.execute(sa.text(
            'SELECT t.table_name, t.table_collation '
            'FROM information_schema.tables t '
            'WHERE t.table_schema = database() AND t.table_name IN :tables'
    ).bindparams(sa.bindparam('tables', list(TABLES), expanding=True))):
        # `table_collation` is NULL for engines without one; nothing to widen.
        if collation and not collation.startswith(f'{TARGET_CHARSET}_'):
            wrong[table] = collation

    for table, column, charset in bind.execute(sa.text(
            'SELECT table_name, column_name, character_set_name '
            'FROM information_schema.columns '
            'WHERE table_schema = database() AND table_name IN :tables '
            '  AND character_set_name IS NOT NULL '
            '  AND character_set_name NOT IN (:target, :binary)'
    ).bindparams(sa.bindparam('tables', list(TABLES), expanding=True),
                 sa.bindparam('target', TARGET_CHARSET),
                 sa.bindparam('binary', BINARY_CHARSET))):
        wrong[f'{table}.{column}'] = charset

    if wrong:
        raise RuntimeError(
            f'Refusing to run revision {revision}: it converts the schema to '
            f'{TARGET_CHARSET}, and these are on something else, so the '
            f'conversion would be a WIDENING rather than a re-labelling: '
            f'{wrong}. NOTHING HAS BEEN CHANGED. A widening grows index key '
            f'bytes past the 767-byte limit of the COMPACT/REDUNDANT row '
            f'formats a deployment this vintage is likely to use, silently '
            f'promotes TEXT to MEDIUMTEXT so the migrated schema stops '
            f'matching the models, and leaves this revision impossible to '
            f'reverse. Convert to {TARGET_CHARSET} deliberately -- moving to '
            f'the DYNAMIC row format first -- then re-run.')


def _is_online() -> bool:
    """False when Alembic is generating SQL rather than applying it.

    Offline mode has no connection to read rows through, so the pre-flight
    cannot run and neither can the downgrade's lookup of the database default.
    Emitting the DDL anyway would hand an operator a script whose entire safety
    argument silently did not happen, so both directions refuse instead.
    """
    return not op.get_context().as_sql


def _refuse_offline(direction: str) -> None:
    raise RuntimeError(
        f'Revision {revision} cannot be {direction} in Alembic offline '
        f'(--sql) mode: its safety check reads existing rows to prove the '
        f'conversion will not violate a UNIQUE constraint, and a generated '
        f'script cannot do that. Run it against a live connection '
        f'(`manage.py db upgrade`).')


def _convert(tables, charset, collation) -> None:
    """Run the conversion loop, reporting each table before it starts.

    Reported rather than silent because of what `CONVERT TO CHARACTER SET`
    costs: it REBUILDS the table, and for `photos` and `attachments` the time is
    proportional to the stored MEDIUMBLOB bytes rather than to the row count, so
    a photo-heavy deployment can sit inside one `ALTER` for a long while under a
    metadata lock. Without this an operator sees nothing between Alembic's
    `Running upgrade ...` line and the end, cannot tell a slow table from a
    hung one, and killing it to find out produces exactly the half-converted
    schema every check above exists to prevent.
    """
    for position, table in enumerate(tables, start=1):
        logger.info('Revision %s: converting %s to %s/%s (%d of %d) -- this '
                    'REBUILDS the table under a metadata lock',
                    revision, table, charset, collation, position, len(tables))
        op.execute(f'ALTER TABLE `{table}` CONVERT TO CHARACTER SET '
                   f'{charset} COLLATE {collation}')


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in MYSQL_DIALECTS:
        return
    if not _is_online():
        _refuse_offline('applied')

    # Cheapest refusals first, then the one that reads rows: an operator whose
    # schema is latin1 gains nothing from a full duplicate scan they will have
    # to repeat after converting it.
    _abort_on_missing_tables(bind)
    _abort_on_missing_columns(bind)
    _abort_on_string_foreign_keys(bind)
    _abort_on_wide_charset(bind)
    _abort_on_collisions(bind, TARGET_CHARSET, TARGET_COLLATION)

    _convert(TABLES, TARGET_CHARSET, TARGET_COLLATION)

    # After the table-wide conversion, not before: `CONVERT TO CHARACTER SET`
    # rewrites every character column and would undo a collation set earlier.
    # The column definition is restated in full because MySQL's `MODIFY` is a
    # replacement, not a patch — omitting `NOT NULL` would make the column
    # nullable and silently break create_product's sole-writer invariant.
    op.execute(f'ALTER TABLE `products` MODIFY `internal_id` VARCHAR(32) '
               f'NOT NULL COLLATE {BINARY_COLLATION}')

    for table, column, definition in JSON_COLUMNS:
        op.execute(f'ALTER TABLE `{table}` MODIFY `{column}` {definition}')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in MYSQL_DIALECTS:
        return
    if not _is_online():
        _refuse_offline('reversed')

    # The same structural refusals as the upgrade, and for the same reason: this
    # direction issues the identical nine conversions plus the JSON `MODIFY`, so
    # a missing table, a redefined column or a character FOREIGN KEY strands the
    # schema here exactly as it would there. `_abort_on_wide_charset` belongs on
    # this side too, even though the upgrade guarantees a utf8mb4 schema on the
    # way in: a later revision is free to add a narrower column to one of these
    # tables, and converting THAT to the utf8mb4 database default below would be
    # the same silent TEXT-to-MEDIUMTEXT widening the upgrade refuses.
    _abort_on_missing_tables(bind)
    _abort_on_missing_columns(bind)
    _abort_on_string_foreign_keys(bind)
    _abort_on_wide_charset(bind)

    # Back to the DATABASE default rather than to a hard-coded charset: what
    # every table had before this revision was whatever it inherited at CREATE
    # time, and the database default is the only recoverable statement of that.
    charset, collation = bind.execute(sa.text(
        'SELECT @@character_set_database, @@collation_database')).one()

    if charset != TARGET_CHARSET:
        raise RuntimeError(
            f'Refusing to reverse revision {revision}: this database defaults '
            f'to {charset}, which is narrower than {TARGET_CHARSET}, and '
            f'`CONVERT TO CHARACTER SET {charset}` would replace every '
            f'unrepresentable character in the stored text with "?" — '
            f'irreversible data loss, not a schema change. Set the database '
            f'default to {TARGET_CHARSET} first if the downgrade is really '
            f'wanted.')

    # The same pre-flight, in the opposite direction and for the same reason:
    # `internal_id` goes from binary to a folding default here, which TIGHTENS
    # uniqueness, and `products` is not the first table converted.
    _abort_on_collisions(bind, charset, collation)

    # No per-column DDL to undo for internal_id: `CONVERT TO CHARACTER SET`
    # overrides the explicit collation along with everything else, so the column
    # goes back to inheriting the table default. The JSON column is restored
    # because its collation is a property of the type, not of the table.
    _convert(tuple(reversed(TABLES)), charset, collation)

    for table, column, definition in JSON_COLUMNS:
        op.execute(f'ALTER TABLE `{table}` MODIFY `{column}` {definition}')
