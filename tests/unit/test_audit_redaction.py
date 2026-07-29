"""
Secrets must never reach the audit log.

Seven route handlers pass `request.form.to_dict()` straight into
`log_audit_operation`, so every form POST used to persist its `csrf_token` into
the audit trail. The fix is a single redaction choke point inside the audit
helpers themselves (`app/logging_config.py`), which is what these tests pin:
one place covers all 40+ existing call sites and any future one.

Companion to `tests/unit/test_audit_json_fix.py`, which pins the opposite
requirement — that the benign reconstruction data still round-trips intact.

The file now pins ALL FOUR helpers that accept a caller-supplied dict, not just
the two audit ones: `log_operation(details=…)` and `log_performance(context=…)`
merged theirs into the record unfiltered, which is the same asymmetry that
produced the original leak. It also pins the collision guard
(`TestDenylistDoesNotSwallowRealFields`) against the payloads the redaction walk
*actually* receives — `_item_to_audit_dict`, the ORM `to_dict()` snapshots and
the dict literals at the audit call sites — rather than against `database.py`
column names and static template `name=` attributes, neither of which is what
gets walked.
"""

import ast
import inspect
import io
import json
import logging
import re
import textwrap
from collections import deque, namedtuple
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import ImmutableMultiDict

import app as app_package
from app.database import (
    Attachment,
    Base,
    InventoryItem,
    Product,
    ProductIdentifier,
    Purchase,
)
from app.logging_config import (
    JSONFormatter,
    MAX_REDACTION_DEPTH,
    REDACTED_VALUE,
    SENSITIVE_FIELD_SUBSTRINGS,
    _MODULE_RECORD_ATTRS,
    _is_sensitive_name,
    _redact_payload,
    _redact_sensitive,
    log_audit_batch_operation,
    log_audit_operation,
    log_operation,
    log_performance,
)
from app.main.routes import (
    _JSON_ITEM_FIELDS,
    _PRODUCT_PREFILL_ARGS,
    _ecia_prefill,
    _item_to_audit_dict,
    _normalize_json_item_payload,
    _scan_prefill_args,
)
from app.models import ScanClassification, ScanKind

LOGGER_NAME = 'test_audit_redaction'

APP_DIR = Path(app_package.__file__).parent

# The two helpers the AST scan (prong 3) SCANS FOR, and the parameters that
# carry a caller dict into them. All four helpers redact — the sibling pair is
# covered behaviourally by `TestSiblingHelperRedaction` above — but only these
# two nest their payload under `audit_data`, and only these two are what the
# call-site scan looks for. `error_details` is deliberately absent from the
# parameters: it is a `str` at every call site, and the one test above that
# passes a dict through it covers the annotation being unenforced.
AUDIT_HELPERS = {'log_audit_operation': log_audit_operation,
                 'log_audit_batch_operation': log_audit_batch_operation}
PAYLOAD_PARAMS = frozenset({'form_data', 'item_before', 'item_after', 'changes',
                            'batch_data', 'results'})

# Every parameter of the four helpers that is free-form CALLER data — the audit
# payloads above plus the two siblings' dicts and `error_details`, which is
# annotated `str` but is routed through the choke point anyway because nothing
# enforces the annotation. Used by the structural guard to check the invariant
# from the parameter end as well as from the merge end.
CALLER_PAYLOAD_PARAMS = PAYLOAD_PARAMS | {'details', 'context', 'error_details'}

# Calls whose result the AST scan accepts as "a payload some OTHER prong
# already covers". Every entry needs a comment naming the prong that actually
# enumerates its keys; recognising a builder nothing checks is the exact hole
# this prong exists to close, and is worse than not recognising it at all.
RECOGNISED_BUILDERS = frozenset({
    # Prong 1 exercises it directly and walks the result recursively.
    '_item_to_audit_dict',
    # Its OUTER keys are `_item_to_audit_dict`'s, so prong 1 again; its inner
    # keys are the literal `{'before': …, 'after': …}` it assigns per changed
    # field, which the subscript-assignment indexing in `_ModuleIndex` collects
    # (asserted as a sentinel in the prong 3 test below).
    '_detect_item_changes',
    # Its output keys are bounded by `_JSON_ITEM_FIELDS` — it rejects anything
    # else with a `ValueError` — and that constant is checked against the
    # denylist by `test_the_json_item_payload_fields_are_not_redacted`.
    '_normalize_json_item_payload',
})

# Every `X.to_dict()` reaching an audit payload argument, mapped to the prong
# that actually enumerates the keys it produces.
#
# PINNED rather than waved through. `to_dict` is not an ORM-only name — prong 2
# parametrizes `Base` subclasses in `app/database.py`, but `app/models.py`,
# `app/export_schemas.py` and `app/mariadb_inventory_service.py` define their
# own, and `SearchFilter.to_dict()` builds its keys DYNAMICALLY (`f'min_{field}'`
# and whatever key `add_exact_match` was handed), so its key set is bounded by
# no prong at all. Accepting any `.to_dict()` credited prong 2 with key sets it
# had never seen, which is the same "recognised but checked by nothing" hole
# `RECOGNISED_BUILDERS` exists to keep shut.
#
# A new receiver here is a REVIEW request, not a failure of the code under
# test: name the prong that covers it, or give it one.
REVIEWED_TO_DICT_RECEIVERS = {
    # The form-field prong (`test_no_form_field_name_is_redacted`) enumerates
    # these from the templates.
    'request.form': 'form-field scan',
    # Prong 2 (`_orm_models_with_to_dict`) parametrizes every one of these.
    'attachment': 'prong 2 — Attachment',
    'identifier': 'prong 2 — ProductIdentifier',
    'product': 'prong 2 — Product',
    'purchase': 'prong 2 — Purchase',
    'current_db_item': 'prong 2 — InventoryItem',
    'new_db_item': 'prong 2 — InventoryItem',
}


def _orm_models_with_to_dict():
    """Every mapped class under `app/database.py`'s `Base` that defines `to_dict`.

    DISCOVERED rather than listed, because `_classify_builder` waves through
    ANY `X.to_dict()` at an audit call site as "prong 2 covers that". With a
    hardcoded five, a brand-new `SomeNewModel.to_dict()` reaching an audit
    payload would be declared covered by a prong that had never heard of it —
    the recognition would be a lie the moment the schema grew. Parametrizing
    over whatever `Base` actually has makes accepting any `.to_dict()` sound.

    `vars(subclass)` rather than `hasattr`: an inherited `to_dict` is the
    parent's, already covered as the parent.
    """
    models = []
    pending = [Base]
    while pending:
        for subclass in pending.pop().__subclasses__():
            pending.append(subclass)
            if 'to_dict' in vars(subclass):
                models.append(subclass)
    return sorted(models, key=lambda model: model.__name__)


def _every_key(value):
    """Every mapping key anywhere in a payload, at any nesting depth.

    The redaction walk recurses, so the collision check has to as well:
    `_item_to_audit_dict` hides the `Dimensions` and `Thread` key sets one level
    down, and a denylist collision there deletes audit data just as silently as
    one at the top level.
    """
    keys = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(key)
            keys |= _every_key(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            keys |= _every_key(item)
    return keys


def _nested_dict_literals(node):
    """`node` and every dict literal nested inside it through values/elements.

    The redaction walk recurses into nested mappings and into sequences of
    them, so a scan that reads only the TOP-LEVEL keys of a payload literal
    enumerates strictly less than what the walk sees: a
    `changes={'location': {'before': …, 'after': …}}` contributed `location`
    and nothing else, while the walk goes on to visit the inner pair — and a
    denylist collision down there deletes audit data just as silently as one at
    the top. `_every_key` (prongs 1 and 2) already recurses; this is prong 3
    catching up to it.
    """
    if isinstance(node, ast.Dict):
        yield node
        for value in node.values:
            yield from _nested_dict_literals(value)
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            yield from _nested_dict_literals(element)


def _nested_payload_expressions(node):
    """Nested values of a payload literal that themselves build a mapping.

    A payload literal's nested dict LITERALS are read directly by
    `_literal_dict_keys`, but `item_after={'snap': product.to_dict()}` hides a
    builder one level down: its keys are in no literal, and the
    `REVIEWED_TO_DICT_RECEIVERS` pin never saw the receiver at all.

    Only the shapes that unmistakably build a mapping are handed on — see
    `_builds_a_mapping`. Any OTHER nested call is treated as a scalar leaf,
    which is this scan's boundary and is stated rather than hidden: an AST pass
    cannot tell `str(x)` from a dict-returning helper, and demanding that every
    nested expression be justified would fail on every `{'ja_id': item.ja_id}`
    in the package.
    """
    for literal in _nested_dict_literals(node):
        for value in literal.values:
            if _builds_a_mapping(value):
                yield value


def _builds_a_mapping(node):
    """Whether an expression unmistakably produces a mapping.

    Used where the scan has to decide, from syntax alone, whether a value that
    is not a literal still contributes keys it ought to account for — nested in
    a payload literal, or assigned into one by subscript.
    """
    if isinstance(node, ast.DictComp):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == 'to_dict':
            return True
        if isinstance(func, ast.Name) and func.id in RECOGNISED_BUILDERS:
            return True
    return False


class _UnreadableBinding:
    """A binding whose value the scan cannot attribute to the name it binds.

    `_ModuleIndex` used to index `ast.Assign` and nothing else, so a name bound
    by a tuple unpack, an annotated assignment, a loop target or a `with … as`
    had NO recorded binding at all — and `_classify_builder`'s "a dict-literal
    binding and nothing else is fully accounted for" fallback then waved it
    through on the strength of some unrelated `changes = {…}` elsewhere in the
    module. Whether the guard is strict came down to the statement shape the
    author happened to use, which is the same arbitrariness
    `_dict_literal_is_opaque` was added to remove one pass earlier.

    Recording the shape as a binding the scan cannot read makes it fail and say
    so, instead.
    """

    def __init__(self, node, shape):
        self.lineno = getattr(node, 'lineno', 0)
        self.shape = shape


def _visible_dict_keys(node):
    """The string keys of a dict literal, skipping any it cannot see.

    The lenient half of the pair. `_ModuleIndex` calls this for EVERY
    `name = {…}` in the package, the overwhelming majority of which have nothing
    to do with audit logging: a `defaults = {**BASE, 'x': 1}` or a
    `lookup = {SomeEnum.A: 1}` anywhere under `app/` is perfectly legitimate and
    must not abort the scan with a message about audit payloads. What it
    contributes is only ever an over-approximation feeding the collision check,
    so a key it cannot read is a key that check simply does not gain.

    Lenient about the KEYS, not about the silence: `_ModuleIndex` records the
    same literal in `opaque_bindings`, so if that name does turn out to reach an
    audit payload the scan says so rather than reporting the visible half as the
    whole thing. See `_dict_literal_is_opaque`.

    Recurses through nested literals for the reason in `_nested_dict_literals`.
    """
    return {key.value
            for literal in _nested_dict_literals(node)
            for key in literal.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)}


def _dict_literal_is_opaque(node):
    """Whether a dict literal carries a key the scan cannot enumerate.

    A `{**other, 'x': 1}` unpack puts a `None` in `node.keys` and a computed key
    puts a non-`Constant` there — the two shapes `_literal_dict_keys` refuses
    outright. That refusal only ever fired for a literal passed INLINE to a
    payload argument, so the identical literal bound to a name first
    (`payload = {**request_form, 'ja_id': …}`, then
    `log_audit_operation(…, form_data=payload)`) went down the lenient path and
    the scan reported full success on a payload half of which it had never seen.
    Whether the guard is strict must not depend on whether the author used a
    temporary variable.

    Nested literals count too: a `{'changes': {**computed}}` is just as unreadable
    as a `{**computed}`.
    """
    return any(not (isinstance(key, ast.Constant) and isinstance(key.value, str))
               for literal in _nested_dict_literals(node)
               for key in literal.keys)


def _literal_dict_keys(node):
    """The string keys of a dict literal, asserting the shape it expects.

    The strict half, used ONLY where a literal reaches a payload argument
    directly — which is where the message is true and where an unreadable key
    really does mean the scan can no longer say what that payload contains.

    A `{**other, 'x': 1}` unpack puts a `None` in `node.keys`, and a computed
    key puts a non-`Constant` there. Either would silently contribute nothing,
    which is exactly the "collected an empty key set and called it success"
    failure this scan must not have — so it fails loudly instead.

    Recurses through nested literals for the reason in `_nested_dict_literals`.
    """
    keys = set()
    for literal in _nested_dict_literals(node):
        for key in literal.keys:
            assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
                f'audit payload literal at line {literal.lineno} has a '
                f'non-literal key; the scan can no longer enumerate what it '
                f'contributes')
            keys.add(key.value)
    return keys


class _ModuleIndex:
    """One `app/**/*.py` file, indexed for the payload-argument resolution.

    KEY collection is deliberately an over-approximation WITHIN a module: a
    `changes = {…}` literal anywhere in `app/main/routes.py` counts as a
    candidate for any `changes=` argument in that file. Extra keys only tighten
    the collision check — there is no false-negative risk — and precise
    dataflow would be far more fragile than this tripwire is worth.

    BUILDER classification cannot share that latitude, which is why the
    non-literal bindings are scoped to the function they occur in (plus module
    level, which any function can read). An extra key is harmless; an extra
    *builder* is a demand that something unrelated be justified — `normalized`
    is bound to `_normalize_json_item_payload(...)` in one function, to
    `dict(updated_fields)` in a second and to a suggestion-normalising service
    call in a third, and only the first ever reaches an audit payload. Pooling
    those would force two builders that log nothing into `RECOGNISED_BUILDERS`,
    which is precisely the "recognised but checked by no prong" hole this scan
    exists to prevent.
    """

    def __init__(self, path):
        self.path = path
        self.tree = ast.parse(path.read_text(encoding='utf-8'))
        # name -> keys of every dict LITERAL bound to it (the over-approximation)
        self.dict_bindings = {}
        # names among those whose literal had a key the scan could not read, so
        # "some literal bound this name" cannot be read as "the scan has seen
        # everything that literal contributes".
        self.opaque_bindings = set()
        # (enclosing function or None, name) -> every other value bound to it,
        # for the builder classification.
        self.other_bindings = {}
        # node -> the function it sits in, so a payload argument that is a
        # parameter can be traced out to the callers that supply it.
        self.enclosing = {}
        self.functions = {}
        # local name -> the name it was imported under. Matching a call site on
        # the spelling at the call site alone meant one
        # `from app.logging_config import log_audit_operation as _audit` made a
        # whole site invisible: not counted, its payload never resolved, nothing
        # flagged — the scan reporting success on a payload it never saw.
        self.import_aliases = {}

        for func in ast.walk(self.tree):
            if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions.setdefault(func.name, []).append(func)
                # Overwritten, NOT `setdefault`. `ast.walk` is breadth-first, so
                # an OUTER function is always reached before the functions
                # nested in it, and the outer function's own `ast.walk` already
                # covers every node inside those. `setdefault` therefore kept
                # the OUTERMOST enclosing function for every nested node — so
                # `_parameter_names` checked the wrong parameter list and
                # `_calls_to(…, func.name)` went looking for callers of the
                # wrong function. Overwriting lets the later (deeper, hence
                # innermost) function win, which is what the resolution means.
                for node in ast.walk(func):
                    self.enclosing[node] = func

        for node in ast.walk(self.tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.asname:
                        self.import_aliases[alias.asname] = \
                            alias.name.split('.')[-1]
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    self._index_binding(node, target, node.value)
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                self._index_binding(node, node.target, node.value)
            elif isinstance(node, ast.NamedExpr):
                self._index_binding(node, node.target, node.value)
            # Every remaining shape that BINDS a name to something the scan
            # cannot attribute to it. Each of these used to leave no trace at
            # all; see `_UnreadableBinding` for why that was the hole.
            elif isinstance(node, ast.AugAssign):
                self._index_unreadable(node, node.target, 'augmented assignment')
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                self._index_unreadable(node, node.target, 'loop target')
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        self._index_unreadable(
                            node, item.optional_vars, '`with … as`')
            elif isinstance(node, ast.comprehension):
                self._index_unreadable(
                    node.target, node.target, 'comprehension target')
            elif isinstance(node, ast.ExceptHandler) and node.name:
                self._bind_unreadable(node, node.name, '`except … as`')
            # `payload.update(src)`: the contents arrive from somewhere the
            # literal index cannot see, so "some literal bound this name" stops
            # meaning "the scan has seen everything in it".
            elif (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'update'
                    and isinstance(node.func.value, ast.Name)
                    and len(node.args) == 1):
                name = node.func.value.id
                if isinstance(node.args[0], ast.Dict):
                    self.dict_bindings.setdefault(name, set()).update(
                        _visible_dict_keys(node.args[0]))
                    if _dict_literal_is_opaque(node.args[0]):
                        self.opaque_bindings.add(name)
                else:
                    self.opaque_bindings.add(name)

    def _index_binding(self, node, target, value):
        """Record `target = value` for one assignment-like statement."""
        # `name[…] = …` contributes to `name` too: a constant subscript IS a key
        # of the payload nested under that name, and a subscript assignment is
        # the only way an incrementally built dict is visible at all. It is how
        # `_detect_item_changes`'s `changes[key] = {'before': …, 'after': …}`
        # gets collected — and, since the constant slice is read as well, how a
        # `payload = {}` filled in one `payload['ja_id'] = …` at a time stops
        # scanning as an empty key set the scan called success.
        if isinstance(target, ast.Subscript):
            if not isinstance(target.value, ast.Name):
                return
            name = target.value.id
            if (isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)):
                self.dict_bindings.setdefault(name, set()).add(
                    target.slice.value)
            if isinstance(value, ast.Dict):
                self.dict_bindings.setdefault(name, set()).update(
                    _visible_dict_keys(value))
                if _dict_literal_is_opaque(value):
                    self.opaque_bindings.add(name)
            elif _builds_a_mapping(value):
                scope = self.enclosing.get(node)
                self.other_bindings.setdefault((scope, name), []).append(value)
            return
        if isinstance(target, (ast.Tuple, ast.List, ast.Starred)):
            # An unpack: which element of `value` lands on which name is not
            # something this scan models.
            self._index_unreadable(node, target, 'tuple unpacking')
            return
        if not isinstance(target, ast.Name):
            return
        if isinstance(value, ast.Dict):
            self.dict_bindings.setdefault(target.id, set()).update(
                _visible_dict_keys(value))
            if _dict_literal_is_opaque(value):
                self.opaque_bindings.add(target.id)
        else:
            scope = self.enclosing.get(node)
            self.other_bindings.setdefault(
                (scope, target.id), []).append(value)

    def _index_unreadable(self, node, target, shape):
        """Record every name `target` binds as one the scan cannot read."""
        if isinstance(target, ast.Name):
            self._bind_unreadable(node, target.id, shape)
        elif isinstance(target, ast.Starred):
            self._index_unreadable(node, target.value, shape)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._index_unreadable(node, element, shape)

    def _bind_unreadable(self, node, name, shape):
        scope = self.enclosing.get(node)
        self.other_bindings.setdefault((scope, name), []).append(
            _UnreadableBinding(node, shape))

    def bindings_visible_from(self, node, name):
        """Non-literal bindings of `name` a `node` could actually be reading.

        Its own function first, then module level — a function may read a
        module global, but not another function's local. See the class
        docstring for why classification is scoped and key collection is not.
        """
        values = []
        for scope in dict.fromkeys((self.enclosing.get(node), None)):
            values += self.other_bindings.get((scope, name), [])
        return values


def _parameter_names(func):
    return [a.arg for a in
            func.args.posonlyargs + func.args.args + func.args.kwonlyargs]


def _argument_for_parameter(call, func, param):
    """What one call site passes for `param` of `func`, keyword or positional."""
    for keyword in call.keywords:
        if keyword.arg == param:
            return keyword.value
    positional = [a.arg for a in func.args.posonlyargs + func.args.args]
    # A BOUND call (`self._emit(payload)`) does not pass the receiver
    # positionally, so it has to come off the list or every index below is one
    # too far — which would not fail, it would silently credit the payload with
    # the wrong argument.
    if (isinstance(call.func, ast.Attribute) and positional
            and positional[0] in ('self', 'cls')):
        positional = positional[1:]
    if param in positional:
        index = positional.index(param)
        if index < len(call.args):
            return call.args[index]
    return None


def _called_name(node, module):
    """The name a `ast.Call` invokes, resolved through the module's aliases.

    `ast.Attribute` as well as `ast.Name`, so `self._log_audit(…)` and
    `logging_config.log_audit_operation(…)` are call sites too — and through
    the alias map, because a scan whose recognition can be switched off by one
    `import … as` is exactly the rot it exists to detect.
    """
    if isinstance(node.func, ast.Name):
        called = node.func.id
    elif isinstance(node.func, ast.Attribute):
        called = node.func.attr
    else:
        return None
    return module.import_aliases.get(called, called)


def _calls_to(modules, name):
    for module in modules:
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call) and _called_name(node, module) == name:
                yield module, node


def _resolve_payload_arg(node, module, modules, through_parameter=True):
    """`(literal keys, unresolved nodes)` for one payload argument.

    Handles a dict literal directly, both branches of an `IfExp`
    (`form_data=context if context else None`), a module-wide `name = {…}`
    binding, and ONE level out through an enclosing function's parameter — which
    is the only way `duplicate_index`/`duplicate_total` are reached, since they
    are built as `duplicate_context` and threaded through
    `_add_item_with_logging(context=…)`.

    The two resolutions are UNIONed rather than short-circuited: `context` is
    also bound to a dict literal inside `_process_item_creation`, so stopping at
    the module-wide binding would silently drop the caller-supplied keys.

    Anything that yields no keys is handed back as an unresolved node for
    `_classify_builder` to account for; it is never quietly dropped.

    A Name is handed back ALWAYS, even when a dict literal was bound to it. A
    name is not a variable — `changes` in `app/main/routes.py` is bound to two
    unrelated literals AND to `_detect_item_changes(...)` — so treating "some
    literal somewhere used this name" as "resolved" MASKED every other binding
    of it, and the builder behind them was accounted for by nothing at all.
    That is the promise directly above this line, and it was not being kept.
    """
    if isinstance(node, ast.Dict):
        # The strict reader: this literal IS the payload, so a key the scan
        # cannot enumerate really does mean it can no longer say what is logged.
        # Mapping-building values NESTED in it are handed on for classification:
        # a `{'snap': product.to_dict()}` puts a builder one level down, where
        # neither the literal reader nor the receiver pin could see it.
        return (_literal_dict_keys(node),
                [(value, module) for value in _nested_payload_expressions(node)])
    if isinstance(node, ast.IfExp):
        body_keys, body_rest = _resolve_payload_arg(
            node.body, module, modules, through_parameter)
        else_keys, else_rest = _resolve_payload_arg(
            node.orelse, module, modules, through_parameter)
        return body_keys | else_keys, body_rest + else_rest
    if isinstance(node, ast.Name):
        keys = set(module.dict_bindings.get(node.id, ()))

        func = module.enclosing.get(node)
        if (through_parameter and func is not None
                and node.id in _parameter_names(func)):
            for caller_module, call in _calls_to(modules, func.name):
                argument = _argument_for_parameter(call, func, node.id)
                if argument is None:
                    continue
                # One level only: a caller's argument is resolved as an
                # ordinary expression, not traced out through ITS callers too.
                caller_keys, _ = _resolve_payload_arg(
                    argument, caller_module, modules, through_parameter=False)
                keys |= caller_keys

        return keys, [(node, module)]
    return set(), [(node, module)]


def _classify_builder(node, module, modules, seen=(), receivers=None):
    """`None` if an unresolved payload argument traces to a covered builder.

    Otherwise a string saying what it is instead — the scan must fail rather
    than report success on a key set that quietly excludes whatever this is.

    `receivers` collects the `X.to_dict()` receivers actually met, so the
    reviewed pin can be checked for staleness as well as for growth.
    """
    if isinstance(node, _UnreadableBinding):
        return (f'{node.lineno}: bound by a {node.shape}, a shape the scan '
                f'cannot attribute a value to — what reaches the payload is '
                f'invisible to it')
    if isinstance(node, ast.Constant) and node.value is None:
        # `form_data=context if context else None` — the falsy branch logs
        # nothing at all.
        return None
    if isinstance(node, ast.Dict):
        # Its keys were collected by the resolution pass above.
        return None
    if isinstance(node, ast.IfExp):
        return (_classify_builder(node.body, module, modules, seen, receivers)
                or _classify_builder(node.orelse, module, modules, seen,
                                     receivers))
    if isinstance(node, ast.DictComp):
        # A filtered copy of another payload dict, so its keys are a SUBSET of
        # that dict's — covered as long as the thing it iterates is
        # (`{k: v for k, v in form_data.items() if k != 'duplicate_of'}`).
        for generator in node.generators:
            source = generator.iter
            if (isinstance(source, ast.Call)
                    and isinstance(source.func, ast.Attribute)
                    and source.func.attr in ('items', 'keys')):
                source = source.func.value
            why = _classify_builder(source, module, modules, seen, receivers)
            if why:
                return why
        return None
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in RECOGNISED_BUILDERS:
            return None
        if isinstance(func, ast.Attribute) and func.attr == 'to_dict':
            # `product.to_dict()` (prong 2), `request.form.to_dict()` (the
            # form-field prong) — but only the receivers a prong has actually
            # been shown to cover. See `REVIEWED_TO_DICT_RECEIVERS`.
            receiver = ast.unparse(func.value)
            if receivers is not None:
                receivers.add(receiver)
            if receiver in REVIEWED_TO_DICT_RECEIVERS:
                return None
            return (f'{node.lineno}: payload built by `{receiver}.to_dict()`, '
                    f'which no prong has been shown to cover — `to_dict` is not '
                    f'an ORM-only name; add it to REVIEWED_TO_DICT_RECEIVERS '
                    f'naming the prong that enumerates its keys')
        return (f'{node.lineno}: payload built by an unrecognised call '
                f'`{ast.unparse(node)[:60]}`')
    if isinstance(node, ast.Name):
        marker = (module.path, node.id)
        if marker in seen:
            # Already being classified further up the chain (a name reassigned
            # from a filtered copy of itself); not a second, unaccounted source.
            return None
        seen = seen + (marker,)

        # Checked BEFORE the bindings, and regardless of whether there are any
        # others: a name whose literal the scan could only half-read is not
        # accounted for by the resolution pass, however many other bindings it
        # also has. See `_dict_literal_is_opaque`.
        if node.id in module.opaque_bindings:
            return (f'{node.lineno}: `{node.id}` is filled from something the '
                    f'scan cannot enumerate (a `**` unpack, a computed key, or '
                    f'an `.update()` from a non-literal), so what reaches the '
                    f'payload is only partly visible')

        candidates = [(value, module)
                      for value in module.bindings_visible_from(node, node.id)]
        func = module.enclosing.get(node)
        if func is not None and node.id in _parameter_names(func):
            candidates += [(_argument_for_parameter(call, func, node.id),
                            caller_module)
                           for caller_module, call in _calls_to(modules, func.name)
                           if _argument_for_parameter(call, func, node.id) is not None]
        if not candidates:
            # A dict-literal binding and nothing else: fully accounted for by
            # the resolution pass, which collected its keys. Checked HERE and
            # not before the candidates are gathered, because a name with a
            # literal binding may ALSO be bound to a builder — and short
            # -circuiting on the literal is precisely what used to hide it.
            if node.id in module.dict_bindings:
                return None
            return (f'{node.lineno}: `{node.id}` is neither bound nor passed '
                    f'anywhere the scan can see')
        for value, value_module in candidates:
            why = _classify_builder(value, value_module, modules, seen,
                                    receivers)
            if why:
                return why
        return None
    return f'{node.lineno}: payload is a bare {type(node).__name__}'


def _module_label(path):
    try:
        return str(path.relative_to(APP_DIR.parent))
    except ValueError:  # a synthetic module, from the scan's own tests
        return path.name


def _scan_audit_payload_keys(modules=None):
    """`(call site count, literal keys, unaccounted args, to_dict receivers)`.

    Enumerates every dict literal that reaches a payload parameter of the two
    audit helpers anywhere under `app/`. Positional arguments are mapped through
    the helpers' LIVE signatures rather than a copy of them, so renaming a
    parameter cannot leave the scan matching a name nothing passes.

    `modules` is for `TestTheAuditScanFailsLoudlyOnWhatItCannotRead`, which
    feeds it synthetic ones: a scan whose job is to fail on code shapes it
    cannot read needs those shapes written down somewhere, and `app/` is not
    the place to keep them.
    """
    parameter_order = {name: list(inspect.signature(helper).parameters)
                       for name, helper in AUDIT_HELPERS.items()}

    if modules is None:
        modules = [_ModuleIndex(path) for path in sorted(APP_DIR.rglob('*.py'))]

    sites = 0
    keys = set()
    unaccounted = []
    receivers = set()
    for module in modules:
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Call):
                continue
            called = _called_name(node, module)
            if called not in parameter_order:
                continue

            sites += 1

            # `f(**payloads)` / `f(*args)` at an audit call site: the positional
            # mapping below is offset by a starred arg and `kw.arg is None` for
            # a `**` unpack, so such a site would be COUNTED (propping up the
            # floor) while contributing no keys and failing nothing — a scan
            # reporting success on a payload it never saw. Flag it instead.
            starred = [kw for kw in node.keywords if kw.arg is None]
            starred += [a for a in node.args if isinstance(a, ast.Starred)]
            if starred:
                unaccounted.append(
                    f'{_module_label(module.path)}:{node.lineno}: '
                    f'audit call site unpacks its arguments (`*`/`**`), so the '
                    f'scan cannot see what payload reaches it')
                continue

            arguments = {parameter_order[called][i]: arg
                         for i, arg in enumerate(node.args)}
            arguments.update({kw.arg: kw.value for kw in node.keywords if kw.arg})

            for param in PAYLOAD_PARAMS & set(arguments):
                found, unresolved = _resolve_payload_arg(
                    arguments[param], module, modules)
                keys |= found
                for unresolved_node, unresolved_module in unresolved:
                    why = _classify_builder(
                        unresolved_node, unresolved_module, modules,
                        receivers=receivers)
                    if why:
                        unaccounted.append(
                            f'{_module_label(unresolved_module.path)}'
                            f':{why}')

    return sites, keys, sorted(set(unaccounted)), receivers


@pytest.mark.unit
class TestAuditRedaction:
    """Direct helper-level coverage of the redaction choke point."""

    def setup_method(self):
        """Capture the dedicated logger through the real JSON formatter."""
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.handler.setFormatter(JSONFormatter())

        self.logger = logging.getLogger(LOGGER_NAME)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        self.logger.addHandler(self.handler)
        # Keep these records off the root handlers: whether a secret was
        # redacted must not depend on what another test left configured there.
        self.logger.propagate = False

    def teardown_method(self):
        self.logger.handlers.clear()

    def _logged(self):
        """The single emitted record, parsed back out of its JSON form."""
        output = self.log_capture.getvalue().strip()
        assert output, 'nothing was logged'
        lines = output.splitlines()
        # Asserted rather than left to json.loads, which would fail with an
        # opaque JSONDecodeError if a second record ever landed in the buffer.
        assert len(lines) == 1, f'expected one record, got {len(lines)}: {lines}'
        return json.loads(lines[0])

    def test_csrf_token_in_form_data_is_redacted(self):
        log_audit_operation('add_item', 'input',
                            item_id='JA000123',
                            form_data={'ja_id': 'JA1', 'csrf_token': 'abc'},
                            logger_name=LOGGER_NAME)

        form_data = self._logged()['audit_data']['form_data']
        assert form_data == {'ja_id': 'JA1', 'csrf_token': REDACTED_VALUE}

    @pytest.mark.parametrize('field_name', [
        'csrf_token',
        'CSRF_Token',
        'X_CSRFToken',
        'password',
        'PASSWORD',
        'passwd',
        'client_secret',
        'api_key',
        'apikey',
        'Authorization',
        'aws_credentials',
        'private_key',
        'session_id',
    ])
    def test_secret_field_name_variants_are_all_redacted(self, field_name):
        """Case-insensitive substring matching, not exact names."""
        log_audit_operation('add_item', 'input',
                            form_data={field_name: 'super-secret'},
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['form_data'] == {
            field_name: REDACTED_VALUE}

    @pytest.mark.parametrize('field_name', [
        'ja_id', 'material', 'length', 'notes', 'request_key', 'photo_id',
    ])
    def test_benign_fields_are_logged_verbatim(self, field_name):
        """The audit log exists for reconstruction; `request_key` in particular
        is why the denylist carries `api_key`/`private_key` and not a bare
        `key`."""
        log_audit_operation('add_item', 'input',
                            form_data={field_name: 'real-value'},
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['form_data'] == {
            field_name: 'real-value'}

    def test_nested_dicts_and_lists_are_redacted_with_structure_preserved(self):
        log_audit_operation('edit_item', 'success',
                            item_after={
                                'meta': {'csrf_token': 'x', 'material': 'Steel'},
                                'rows': [{'token': 'y'}, {'ja_id': 'JA2'}],
                            },
                            logger_name=LOGGER_NAME)

        item_after = self._logged()['audit_data']['item_after']
        assert item_after == {
            'meta': {'csrf_token': REDACTED_VALUE, 'material': 'Steel'},
            'rows': [{'token': REDACTED_VALUE}, {'ja_id': 'JA2'}],
        }

    def test_every_dict_payload_of_log_audit_operation_is_redacted(self):
        """form_data, item_before, item_after and changes — not just the one
        the routes happen to pass today."""
        secret = {'csrf_token': 'abc', 'material': 'Steel'}

        log_audit_operation('edit_item', 'success',
                            item_id='JA000456',
                            form_data=dict(secret),
                            item_before=dict(secret),
                            item_after=dict(secret),
                            changes={'csrf_token': {'before': 'a', 'after': 'b'},
                                     'material': {'before': 'Steel',
                                                  'after': 'Aluminum'}},
                            logger_name=LOGGER_NAME)

        audit_data = self._logged()['audit_data']
        for section in ('form_data', 'item_before', 'item_after'):
            assert audit_data[section] == {'csrf_token': REDACTED_VALUE,
                                           'material': 'Steel'}, section
        assert audit_data['changes'] == {
            'csrf_token': REDACTED_VALUE,
            'material': {'before': 'Steel', 'after': 'Aluminum'},
        }

    def test_callers_dict_is_never_mutated(self):
        """Routes reuse the dict they log — `_render_product_add(form_data, ...)`
        re-renders the very dict handed to the audit helper."""
        form_data = {'ja_id': 'JA1', 'csrf_token': 'abc',
                     'nested': {'token': 'xyz'}}

        log_audit_operation('add_item', 'input',
                            form_data=form_data,
                            logger_name=LOGGER_NAME)

        assert form_data == {'ja_id': 'JA1', 'csrf_token': 'abc',
                             'nested': {'token': 'xyz'}}

    @pytest.mark.parametrize('payload', [None, {}, '', 0])
    def test_falsy_payloads_are_still_dropped(self, payload):
        """Pre-existing behaviour: falsy payloads produce no audit_data section."""
        log_audit_operation('add_item', 'input',
                            form_data=payload,
                            logger_name=LOGGER_NAME)

        assert 'audit_data' not in self._logged()

    @pytest.mark.parametrize('payload', ['a raw string', 42, ['a', 'b']])
    def test_non_dict_payloads_pass_through_without_raising(self, payload):
        log_audit_operation('add_item', 'input',
                            form_data=payload,
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['form_data'] == payload

    def test_batch_payloads_are_redacted_too(self):
        """`log_audit_batch_operation` hardcodes the `inventory` logger, so the
        capture is pointed at that name for this one case."""
        inventory_logger = logging.getLogger('inventory')
        previous_handlers = inventory_logger.handlers[:]
        previous_level = inventory_logger.level
        inventory_logger.handlers = [self.handler]
        inventory_logger.setLevel(logging.INFO)
        try:
            log_audit_batch_operation(
                'batch_move_items', 'success',
                batch_data={'csrf_token': 'abc',
                            'items': [{'ja_id': 'JA1', 'token': 'x'}]},
                results={'successful_count': 1, 'session_id': 'sid'})
        finally:
            inventory_logger.handlers = previous_handlers
            inventory_logger.setLevel(previous_level)

        audit_data = self._logged()['audit_data']
        assert audit_data['batch_input'] == {
            'csrf_token': REDACTED_VALUE,
            'items': [{'ja_id': 'JA1', 'token': REDACTED_VALUE}],
        }
        assert audit_data['batch_results'] == {'successful_count': 1,
                                               'session_id': REDACTED_VALUE}

    @pytest.mark.parametrize('results', [
        ['not', 'a', 'mapping'],
        SimpleNamespace(successful_count=1),
    ], ids=['list', 'object'])
    def test_a_non_mapping_batch_results_cannot_raise_out_of_the_message(
            self, results):
        """The same hazard `log_performance`'s message lookup is guarded against.

        `results` is annotated `dict` and nothing enforces it: `in` raises
        `TypeError` on a plain object and the subscript on a list. A sibling
        left with the unguarded version is exactly the asymmetry this whole
        change exists to remove.
        """
        inventory_logger = logging.getLogger('inventory')
        previous_handlers = inventory_logger.handlers[:]
        previous_level = inventory_logger.level
        inventory_logger.handlers = [self.handler]
        inventory_logger.setLevel(logging.INFO)
        try:
            log_audit_batch_operation('batch_move_items', 'success',
                                      results=results)
        finally:
            inventory_logger.handlers = previous_handlers
            inventory_logger.setLevel(previous_level)

        assert (self._logged()['message']
                == 'AUDIT: batch_move_items batch_phase=success')

    def test_error_details_is_redacted_too(self):
        """Annotated `str`, but nothing enforces that. If a caller ever passes a
        dict, it must not become the one payload that escapes the choke point."""
        log_audit_operation('add_item', 'error',
                            error_details={'csrf_token': 'abc',
                                           'message': 'boom'},
                            logger_name=LOGGER_NAME)

        assert self._logged()['audit_data']['error_details'] == {
            'csrf_token': REDACTED_VALUE, 'message': 'boom'}

    def test_error_details_strings_are_unchanged(self):
        """Every real caller passes `str(e)`; that must survive intact."""
        log_audit_operation('add_item', 'error',
                            error_details='Service update_item returned False',
                            logger_name=LOGGER_NAME)

        assert (self._logged()['audit_data']['error_details']
                == 'Service update_item returned False')

    def test_a_payload_deeper_than_the_walk_fails_closed(self):
        """The depth cap must drop the subtree, not hand it over unfiltered.

        A guard on a security control that returns the raw value once it gives
        up is worse than no guard: it is a documented, predictable bypass.
        """
        deep = {'csrf_token': 'LEAK'}
        for _ in range(MAX_REDACTION_DEPTH + 2):
            deep = {'wrapper': deep}

        log_audit_operation('add_item', 'input',
                            form_data=deep,
                            logger_name=LOGGER_NAME)

        assert 'LEAK' not in self.log_capture.getvalue()

    def test_a_payload_within_the_walk_is_fully_redacted_not_truncated(self):
        """The complement: nesting the app actually produces stays legible."""
        deep = {'csrf_token': 'LEAK', 'material': 'Steel'}
        for _ in range(MAX_REDACTION_DEPTH - 2):
            deep = {'wrapper': deep}

        log_audit_operation('add_item', 'input',
                            form_data=deep,
                            logger_name=LOGGER_NAME)

        output = self.log_capture.getvalue()
        assert 'LEAK' not in output
        assert 'Steel' in output, 'benign data was truncated by the depth guard'

    @pytest.mark.parametrize('depth,benign_survives', [
        (MAX_REDACTION_DEPTH, True),
        (MAX_REDACTION_DEPTH + 1, False),
    ])
    def test_the_depth_cliff_sits_exactly_at_max_redaction_depth(
            self, depth, benign_survives):
        """Pins both sides of the boundary, not just far from it.

        The two tests above sample MAX-2 and MAX+2, which an off-by-one in
        either direction would slip through. The secret must be gone on both
        sides; what changes at the cliff is whether the benign sibling is still
        walked or the whole subtree is dropped.
        """
        deep = {'csrf_token': 'LEAK', 'material': 'Steel'}
        for _ in range(depth):
            deep = {'wrapper': deep}

        log_audit_operation('add_item', 'input',
                            form_data=deep,
                            logger_name=LOGGER_NAME)

        output = self.log_capture.getvalue()
        assert 'LEAK' not in output
        assert ('Steel' in output) is benign_survives


@pytest.mark.unit
class TestRedactionContainerTypes:
    """The walk must not fail *open* on a container it does not recognise.

    `JSONFormatter` serializes with `default=str`, so anything the walk returns
    untouched is `str()`-ed into the record with its secret intact — which is
    why the type check has to be as fail-closed as the depth guard beside it.
    """

    def test_a_mapping_that_is_not_a_dict_is_walked(self):
        """SQLAlchemy's `RowMapping` is exactly this shape."""
        class ReadOnlyMapping(Mapping):
            def __init__(self, data):
                self._data = data

            def __getitem__(self, key):
                return self._data[key]

            def __iter__(self):
                return iter(self._data)

            def __len__(self):
                return len(self._data)

        redacted = _redact_sensitive(
            ReadOnlyMapping({'csrf_token': 'LEAK', 'material': 'Steel'}))

        assert redacted == {'csrf_token': REDACTED_VALUE, 'material': 'Steel'}
        assert 'LEAK' not in json.dumps(redacted, default=str)

    def test_a_multidict_is_walked(self):
        """Nothing stops a caller handing over `request.form` itself rather
        than a `to_dict()` copy — it is a `Mapping`, and the walk must treat it
        as one instead of `str()`-ing the whole thing into the record."""
        redacted = _redact_sensitive(
            ImmutableMultiDict([('csrf_token', 'LEAK'), ('ja_id', 'JA1')]))

        assert redacted == {'csrf_token': REDACTED_VALUE, 'ja_id': 'JA1'}

    @pytest.mark.parametrize('factory,expected', [
        (lambda: deque([{'csrf_token': 'LEAK'}]), [{'csrf_token': REDACTED_VALUE}]),
        (lambda: {'row': {'csrf_token': 'LEAK'}}.values(),
         [{'csrf_token': REDACTED_VALUE}]),
        (lambda: frozenset(['plain']), ['plain']),
    ], ids=['deque', 'dict_values', 'frozenset'])
    def test_a_sequence_that_is_not_a_list_or_tuple_is_walked(
            self, factory, expected):
        """The mirror of the `Mapping` case, and the same fail-open shape.

        `deque`, a `dict_values` view and a `frozenset` are none of
        `list`/`tuple`; recognising containers by concrete type rather than by
        ABC would hand each straight to `default=str` with its nested secret
        intact.
        """
        redacted = _redact_sensitive(factory())

        assert redacted == expected
        assert 'LEAK' not in json.dumps(redacted, default=str)

    def test_a_one_shot_iterator_fails_closed(self):
        """Walking a generator would consume the caller's object, which the
        "never mutate the caller" contract forbids; passing it through would be
        a bypass. Neither is acceptable, so the payload is dropped."""
        payload = (item for item in [{'csrf_token': 'LEAK'}])

        assert _redact_sensitive(payload) == REDACTED_VALUE

    def test_non_string_keys_do_not_bypass_the_denylist(self):
        """A `bytes` or Enum key names the same secret a `str` key would."""
        assert _redact_sensitive({b'csrf_token': 'LEAK'}) == {
            'csrf_token': REDACTED_VALUE}
        assert _is_sensitive_name(b'csrf_token')
        assert not _is_sensitive_name(b'ja_id')

    def test_a_redacted_payload_is_always_json_serializable(self):
        """Redacting the value but keeping an unserializable KEY loses the
        whole record, which is worse than the leak it prevents.

        `json.dumps(..., default=str)` applies to values only: a `bytes` key
        raises `TypeError` out of `JSONFormatter.format`, logging swallows it,
        and nothing at all is emitted. The keys must be coerced too.
        """
        redacted = _redact_sensitive(
            {b'csrf_token': 'LEAK', 'ja_id': 'JA1', 3: 'int key',
             None: 'none key', ('tuple', 'key'): 'tuple key'})

        # Would raise TypeError if any key came back unserializable.
        round_tripped = json.loads(json.dumps(redacted, default=str))
        assert round_tripped['csrf_token'] == REDACTED_VALUE
        assert round_tripped['ja_id'] == 'JA1'
        assert 'LEAK' not in json.dumps(redacted, default=str)

    def test_a_payload_that_raises_never_breaks_the_caller(self):
        """`log_audit_operation` is called from inside request handlers. A walk
        that raises would turn a logging call into a failed request — so the
        payload collapses to the marker instead."""
        class ExplodingMapping(dict):
            def items(self):
                raise RuntimeError('payload blew up mid-walk')

        # Raises unguarded...
        with pytest.raises(RuntimeError):
            _redact_sensitive(ExplodingMapping({'csrf_token': 'LEAK'}))

        # ...but the helper the audit functions actually call fails closed.
        assert _redact_payload(ExplodingMapping({'csrf_token': 'LEAK'})) == \
            REDACTED_VALUE

    def test_a_namedtuple_is_redacted_by_field_name(self):
        """Walked positionally, its named secret would survive."""
        Row = namedtuple('Row', ['ja_id', 'csrf_token'])

        redacted = _redact_sensitive(Row(ja_id='JA1', csrf_token='LEAK'))

        assert redacted == {'ja_id': 'JA1', 'csrf_token': REDACTED_VALUE}

    def test_a_tuple_is_copied_not_coerced_into_a_list(self):
        """The docstring promises a copy; a silent type change is not one."""
        redacted = _redact_sensitive(({'csrf_token': 'LEAK'}, {'ja_id': 'JA1'}))

        assert isinstance(redacted, tuple)
        assert redacted == ({'csrf_token': REDACTED_VALUE}, {'ja_id': 'JA1'})

    def test_strings_and_bytes_are_not_walked_as_sequences(self):
        """Both are `Sequence`s; walking them would shred every audit value."""
        assert _redact_sensitive('Service returned False') == \
            'Service returned False'
        assert _redact_sensitive(b'raw') == b'raw'

    def test_an_arbitrary_object_is_documented_as_a_scalar(self):
        """Pins the deliberate boundary rather than leaving it to be
        rediscovered: the walk does not reflect over `__dict__`, because doing
        so on a logging path risks dragging in ORM instrumentation state. A
        caller with an object must convert it (`_item_to_audit_dict`) first —
        which is what every caller in this app already does."""
        obj = SimpleNamespace(csrf_token='LEAK')

        assert _redact_sensitive(obj) is obj


class _RecordCapture(logging.Handler):
    """Keeps the emitted `LogRecord` objects themselves.

    The sibling helpers merge the caller's dict FLAT into the record, and
    `JSONFormatter` serialises a fixed attribute allowlist — so a leaked
    `csrf_token` never reaches the JSON at all and an assertion on formatter
    output would pass whether or not the value was redacted. The record is
    where the merge actually lands, so that is what these tests read.
    """

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


# Everything `logging` itself puts on a record, so a test can name the
# attributes the helper ADDED rather than enumerating the built-ins.
# `message`/`asctime` are not on a fresh record but are stamped onto one by any
# `Formatter` that runs — pytest's own capture handler being one — so they
# belong to logging just as much as the rest.
_BUILTIN_RECORD_ATTRS = frozenset(
    logging.LogRecord('n', logging.INFO, 'p', 1, 'm', None, None).__dict__
) | {'message', 'asctime'}

# The helpers' OWN record fields. A caller key shadowing one of these is a
# pre-existing behaviour deliberately left alone (see the choke-point comment in
# `log_audit_operation`), so they are excluded from the pin below rather than
# being expected in `_MODULE_RECORD_ATTRS`.
HELPER_OWN_RECORD_FIELDS = frozenset({'operation', 'duration', 'item_id'})


def _module_record_attr_names():
    """Every record attribute `AuditLogFilter`/`JSONFormatter` stamp or read.

    `_RESERVED_RECORD_ATTRS` is derived from a probe `LogRecord`, which cannot
    see either of these: the filter sets its five attributes AFTER the record is
    built, and the formatter's `hasattr` gates are just as much a claim on a
    name. Read out of the source so the pin fails when the filter or the
    formatter grows a field, rather than the day a caller happens to send one.

    Scanned across the WHOLE module rather than two named class bodies. A third
    filter or formatter, a `setattr(record, …)`, or a `%(name)s` in the
    `stderr_handler`'s format string (`setup_logging` builds one, and `%`-style
    formatting reads `record.__dict__` exactly like an attribute access) each
    claims a name just as much — and a pin that reads only two class bodies
    would go on passing while the merge guard under-covered.
    """
    tree = ast.parse((APP_DIR / 'logging_config.py').read_text(encoding='utf-8'))
    classes = {node.name for node in ast.walk(tree)
               if isinstance(node, ast.ClassDef)}
    assert {'AuditLogFilter', 'JSONFormatter'} <= classes, (
        'the record-attribute scan has rotted: it no longer finds the filter '
        f'and formatter it reads ({sorted(classes)})')

    names = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == 'record'):
            names.add(node.attr)
        elif (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ('hasattr', 'getattr', 'setattr')
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == 'record'
                and isinstance(node.args[1], ast.Constant)):
            names.add(node.args[1].value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names |= set(re.findall(r'%\((\w+)\)', node.value))

    assert names, 'the record-attribute scan found nothing; it has rotted'
    # Both halves of "belongs to logging": the probe's instance attributes
    # (`levelname`, `lineno`, `module`, …, which the formatter reads for its
    # fixed fields) and the class ones (`getMessage`, a method it calls).
    return names - _BUILTIN_RECORD_ATTRS - set(dir(logging.LogRecord))


@pytest.mark.unit
class TestSiblingHelperRedaction:
    """`log_operation(details=…)` and `log_performance(context=…)`.

    Both merged the caller's dict straight into the log record, which is the
    same asymmetry that let a `csrf_token` into the audit trail in the first
    place: one helper guarded, its sibling beside it not. They now share the one
    choke point, through `_redact_merge`.
    """

    PERFORMANCE_LOGGER = 'performance'

    def setup_method(self):
        self.capture = _RecordCapture()

        self.logger = logging.getLogger(LOGGER_NAME)
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        self.logger.addHandler(self.capture)
        # As above: whether a secret was redacted must not depend on what
        # another test left on the root handlers.
        self.logger.propagate = False

        # `log_performance` hardcodes its logger name, so that one is borrowed
        # and put back rather than configured.
        self.performance_logger = logging.getLogger(self.PERFORMANCE_LOGGER)
        self._saved = (self.performance_logger.handlers[:],
                       self.performance_logger.level,
                       self.performance_logger.propagate)
        self.performance_logger.handlers = [self.capture]
        self.performance_logger.setLevel(logging.INFO)
        self.performance_logger.propagate = False

    def teardown_method(self):
        self.logger.handlers.clear()
        (self.performance_logger.handlers,
         self.performance_logger.level,
         self.performance_logger.propagate) = self._saved

    def _record(self):
        assert len(self.capture.records) == 1, (
            f'expected one record, got {len(self.capture.records)}')
        return self.capture.records[0]

    def _added_attrs(self):
        """The attribute names the helper merged onto the record."""
        return set(self._record().__dict__) - _BUILTIN_RECORD_ATTRS

    def test_a_secret_in_log_operation_details_is_redacted(self):
        log_operation('add_item', details={'csrf_token': 'LEAK', 'ja_id': 'JA1'},
                      logger_name=LOGGER_NAME)

        record = self._record()
        assert record.csrf_token == REDACTED_VALUE
        assert record.ja_id == 'JA1'
        assert 'LEAK' not in json.dumps(record.__dict__, default=str)

    def test_a_nested_secret_in_log_performance_context_is_redacted(self):
        log_performance('search', 0.0, 1.0, context={'req': {'password': 'p'}})

        assert self._record().req == {'password': REDACTED_VALUE}

    def test_benign_details_pass_through_verbatim(self):
        """`request_key` again: the field the denylist omits a bare `key` for."""
        log_operation('add_item', details={'item_count': 3,
                                           'request_key': 'abc'},
                      logger_name=LOGGER_NAME)

        record = self._record()
        assert record.item_count == 3
        assert record.request_key == 'abc'

    def test_the_callers_dict_is_never_mutated(self):
        details = {'ja_id': 'JA1', 'csrf_token': 'abc',
                   'nested': {'token': 'xyz'}}

        log_operation('add_item', details=details, logger_name=LOGGER_NAME)

        assert details == {'ja_id': 'JA1', 'csrf_token': 'abc',
                           'nested': {'token': 'xyz'}}

    def test_a_payload_that_fails_the_walk_is_nested_under_its_parameter_name(self):
        """The reason a bare `_redact_payload` will not do here.

        Its fail-closed return is a `str`, and `dict.update('[REDACTED]')`
        raises `ValueError` — out of a logging call, from the very path that
        exists so a bad payload never breaks its caller. So the marker is
        nested under the parameter name and the record still gets emitted.
        """
        class ExplodingMapping(dict):
            def items(self):
                raise RuntimeError('payload blew up mid-walk')

        log_operation('add_item', details=ExplodingMapping({'csrf_token': 'LEAK'}),
                      logger_name=LOGGER_NAME)

        record = self._record()
        assert record.details == REDACTED_VALUE
        assert 'LEAK' not in json.dumps(record.__dict__, default=str)

    @pytest.mark.parametrize('payload', [
        ['a', 'list'],
        SimpleNamespace(item_count=1),
    ], ids=['list', 'object'])
    def test_a_non_mapping_payload_is_nested_rather_than_merged(self, payload):
        """`dict.update` on either would raise; neither is a caller's problem."""
        log_performance('search', 0.0, 1.0, context=payload)

        record = self._record()
        assert record.context == payload
        assert record.operation == 'search'

    @pytest.mark.parametrize('payload', [None, {}], ids=['none', 'empty'])
    def test_a_falsy_payload_adds_nothing_to_the_record(self, payload):
        """Unchanged from before the redaction went in."""
        log_operation('add_item', details=payload, logger_name=LOGGER_NAME)

        assert self._added_attrs() == {'operation'}

    @pytest.mark.parametrize('colliding', ['name', 'module', 'filename', 'args',
                                           'lineno', 'levelname', 'message'])
    def test_a_key_the_log_record_reserves_is_nested_rather_than_merged(
            self, colliding):
        """A flat merge cannot put every key on a record, and must not try.

        `logging.Logger.makeRecord` raises `KeyError("Attempt to overwrite …")`
        for any `extra` key that is `message`/`asctime` or already a
        `LogRecord` attribute — so `details={'name': …}`, with `name` one of the
        commonest form-field names there is, used to take down the request the
        logging call only meant to describe. The colliding key moves under the
        parameter name instead: nothing raises, nothing is lost, and the keys
        beside it still merge flat exactly as before.
        """
        log_operation('add_item', details={colliding: 'x', 'ja_id': 'JA1'},
                      logger_name=LOGGER_NAME)

        record = self._record()
        assert record.details == {colliding: 'x'}
        assert record.ja_id == 'JA1', 'a benign sibling stopped merging flat'
        assert record.name == LOGGER_NAME, "the record's own attribute was lost"

    def test_a_coerced_key_the_log_record_reserves_is_nested_too(self):
        """`b'name'` was harmless until keys started being coerced.

        `_serializable_key` turns it into the `str` `'name'` — necessary, since
        a `bytes` key would cost the whole record at `json.dumps` — which means
        the collision guard has to run on the redacted keys, not the caller's.
        """
        log_operation('add_item', details={b'name': 'x', 'ja_id': 'JA1'},
                      logger_name=LOGGER_NAME)

        record = self._record()
        assert record.details == {'name': 'x'}
        assert record.ja_id == 'JA1'

    def test_no_name_logging_reserves_can_raise_out_of_the_helper(self):
        """The exhaustive version of the two above.

        Parametrizing a hand-picked few would leave the rest to be found in
        production, and the attribute set grows between Python releases
        (`taskName` arrived in 3.12) — so every name this Python's `logging`
        refuses is exercised.

        Each name is first proved to be one `makeRecord` really does reject,
        by calling it. `_BUILTIN_RECORD_ATTRS` and the module's own
        `_RESERVED_RECORD_ATTRS` are the same expression, so a test that only
        compared them would move in lockstep with a derivation that had gone
        wrong; `logging` itself is the only independent authority on what it
        refuses.
        """
        logger = logging.getLogger(LOGGER_NAME)

        for reserved in sorted(_BUILTIN_RECORD_ATTRS):
            with pytest.raises(KeyError):
                logger.makeRecord(LOGGER_NAME, logging.INFO, 'p', 1, 'm', None,
                                  None, extra={reserved: 'x'})

            self.capture.records.clear()

            log_operation('add_item', details={reserved: 'x'},
                          logger_name=LOGGER_NAME)

            assert self._record().details == {reserved: 'x'}, reserved

    def test_a_caller_key_named_after_the_parameter_is_not_clobbered(self):
        """The nesting has to go somewhere, and `details` is a legal form field.

        Folding the caller's own `details` value into the nested dict keeps the
        merge lossless; overwriting it with the nest would silently drop data
        the record is supposed to preserve.
        """
        log_operation('add_item', details={'details': 'mine', 'name': 'x'},
                      logger_name=LOGGER_NAME)

        assert self._record().details == {'name': 'x', 'details': 'mine'}

    def test_a_context_whose_lookup_raises_does_not_escape_the_message(self):
        """The payload path already fails closed against this; the message did not.

        `isinstance(context, Mapping)` says nothing about whether the mapping's
        `__contains__`/`__getitem__` behaves — a lazily-populated or
        remotely-backed mapping can raise from either — and a message decoration
        must not be the one line that propagates out of a logging call.
        """
        class ExplodingLookup(dict):
            def __contains__(self, key):
                raise RuntimeError('lookup blew up')

        log_performance('search', 0.0, 1.0,
                        context=ExplodingLookup({'item_count': 3,
                                                 'ja_id': 'JA1'}))

        record = self._record()
        assert record.getMessage() == 'Performance metric'
        # ...and the payload itself still merged, since only the lookup failed.
        assert record.ja_id == 'JA1'

    def test_log_performance_still_reports_item_count_in_its_message(self):
        """The message reads the caller's ORIGINAL context: it is a count, not
        the audit trail, and reading the redacted copy would only add a way for
        the two to disagree."""
        log_performance('search', 0.0, 0.5, context={'item_count': 7,
                                                     'csrf_token': 'LEAK'})

        record = self._record()
        assert record.getMessage() == 'Performance metric (processed 7 items)'
        assert record.item_count == 7
        assert record.csrf_token == REDACTED_VALUE

    def test_no_helper_merges_a_caller_dict_without_redacting_it(self):
        """The structural version of the three tests above.

        A fifth helper — or a new branch in one of these two — that reaches for
        a bare `extra_data.update(caller_dict)` reintroduces exactly the leak
        this class exists for, and would not be caught by any behavioural test
        written today.

        Matched on the SHAPE (`<some dict>.update(<something>)`, and `|=`, the
        other in-place merge Python has) rather than on the identifier
        `extra_data`: a helper that happened to name its record dict `extra`,
        `payload` or `log_data` — or to reach it as `self.extra` — was invisible
        to a guard keyed on one spelling, and the leak does not care what the
        variable is called.

        Shape matching alone still only covers the mergers it knows, so the
        second half of this test comes at the same invariant from the other
        end: whatever the syntax, a caller PAYLOAD PARAMETER may only ever be
        handed to one of the guard helpers.
        """
        tree = ast.parse((APP_DIR / 'logging_config.py').read_text(
            encoding='utf-8'))
        merges = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'update'
                    and isinstance(node.func.value, (ast.Name, ast.Attribute))):
                merges.append((node.lineno,
                               node.args[0] if len(node.args) == 1 else None))
            elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.BitOr):
                merges.append((node.lineno, node.value))
        assert len(merges) >= 2, 'the merge scan has rotted; it found nothing'

        for lineno, merged in merges:
            # A dict LITERAL is fine: it is the helper's own data, not a
            # caller's — `extra_data.update({'schema_version': 1})` carries
            # nothing to redact, and failing it would make a safe addition look
            # like a leak. What must never appear is a caller-supplied name
            # going in unwalked.
            if isinstance(merged, ast.Dict):
                continue
            assert (isinstance(merged, ast.Call)
                    and isinstance(merged.func, ast.Name)
                    and merged.func.id == '_redact_merge'), (
                f'app/logging_config.py:{lineno} merges a caller dict '
                f'into a log record without the redaction choke point')

        # The same invariant read off the PARAMETERS instead of the mergers,
        # so a shape the scan above does not know (`{**extra_data, **details}`,
        # `dict(extra_data, **details)`, a subscript assignment) cannot carry a
        # caller payload into a record behind its back. This is the acceptance
        # criterion almost verbatim: no helper merges a caller dict without
        # passing it through the choke point first.
        guards = {'_redact_payload', '_redact_merge', '_has_payload',
                  '_message_field'}
        functions = {node.name: node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef)}
        helpers = ('log_operation', 'log_performance', *AUDIT_HELPERS)
        assert set(helpers) <= set(functions), (
            f'the payload-parameter scan has rotted; it no longer finds the '
            f'helpers it reads ({sorted(set(helpers) - set(functions))})')

        for helper_name in helpers:
            func = functions[helper_name]
            payloads = CALLER_PAYLOAD_PARAMS & set(_parameter_names(func))
            assert payloads, (
                f'{helper_name} has no parameter in CALLER_PAYLOAD_PARAMS; '
                f'either it stopped taking a caller dict or the list is stale')
            # Node identity, not the name: "`details` reaches a guard SOMEWHERE
            # in this function" would be satisfied by the `_has_payload` gate
            # and leave the merge one line below it free to do anything. What
            # must hold is that EVERY read of the payload is a read by a guard.
            guarded = {id(argument)
                       for call in ast.walk(func)
                       if isinstance(call, ast.Call)
                       and isinstance(call.func, ast.Name)
                       and call.func.id in guards
                       for argument in call.args}
            for use in ast.walk(func):
                if not (isinstance(use, ast.Name) and use.id in payloads
                        and isinstance(use.ctx, ast.Load)):
                    continue
                assert id(use) in guarded, (
                    f'app/logging_config.py:{use.lineno} reads the caller '
                    f'payload `{use.id}` in {helper_name} somewhere other than '
                    f'as a direct argument to one of {sorted(guards)}')

    # -- The record attributes this module itself owns ---------------------

    def test_the_module_record_attrs_match_what_the_module_uses(self):
        """`_MODULE_RECORD_ATTRS` against the filter and formatter themselves.

        The probe-derived `_RESERVED_RECORD_ATTRS` covers what `makeRecord`
        refuses; it is blind to the names this module stamps on afterwards. A
        hardcoded second list is exactly the drift the probe was chosen to
        avoid, so it is pinned against the source instead: add a field to
        `AuditLogFilter` or a `hasattr` gate to `JSONFormatter` and this fails
        until the merge guard hears about it.
        """
        owned = _module_record_attr_names() - HELPER_OWN_RECORD_FIELDS

        assert owned == set(_MODULE_RECORD_ATTRS), (
            'the filter/formatter record contract and `_MODULE_RECORD_ATTRS` '
            f'have diverged: source has {sorted(owned)}, the guard has '
            f'{sorted(_MODULE_RECORD_ATTRS)}')

    def test_a_caller_url_key_does_not_cost_the_whole_record(self):
        """The worst of the collisions, and the one no `KeyError` announces.

        `JSONFormatter` reads `record.url` as the sentinel meaning the filter
        has run and `method`/`remote_addr`/`user_agent`/`user_id` are all
        present. A flat-merged `url` from a caller makes that true without them,
        so `format` raises `AttributeError` on `record.method` — and `logging`
        answers by discarding the record. Nesting it keeps both the line and the
        value.
        """
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        self.logger.handlers = [handler, self.capture]

        log_operation('add_item', details={'url': 'http://x/y', 'ja_id': 'JA1'},
                      logger_name=LOGGER_NAME)

        emitted = stream.getvalue()
        assert emitted.strip(), 'the record was dropped instead of emitted'
        assert json.loads(emitted)['message'] == "Operation 'add_item'"
        # Emitted is only half of it: DROPPING the colliding key would satisfy
        # the assertions above just as well, and "lossless" is what the merge
        # docstring claims. The value has to still be on the record.
        assert self._record().details == {'url': 'http://x/y'}

    def test_a_caller_cannot_forge_an_audit_block_through_log_operation(self):
        """`JSONFormatter`'s audit block is `hasattr` gated, so a flat-merged
        `audit_data` made a helper that writes no audit trail emit one."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        self.logger.handlers = [handler, self.capture]

        log_operation('add_item', details={'audit_data': {'forged': True}},
                      logger_name=LOGGER_NAME)

        assert 'audit_data' not in json.loads(stream.getvalue())
        # Nested, not discarded — see the `url` test above for why absence from
        # the JSON is not on its own the behaviour being pinned here.
        assert self._record().details == {'audit_data': {'forged': True}}

    def test_a_filter_stamped_key_is_kept_rather_than_overwritten(self):
        """`AuditLogFilter` sets `user_id` on every record it sees, so a merged
        caller `user_id` was silently replaced — the one case where the merge
        was not the lossless thing its docstring claims."""
        log_operation('add_item', details={'user_id': 'caller-value',
                                           'ja_id': 'JA1'},
                      logger_name=LOGGER_NAME)

        record = self._record()
        assert record.details == {'user_id': 'caller-value'}
        assert record.ja_id == 'JA1'

    # -- The message is the one field that is always emitted ---------------

    def test_a_non_scalar_count_never_reaches_the_message(self):
        """The leak the payload redaction alone does not close.

        `message` is emitted unconditionally by `JSONFormatter` while
        `details`/`context` are not in its allowlist at all — so interpolating a
        caller's dict into it printed verbatim exactly what the redacted copy
        beside it had just protected.
        """
        log_performance('search', 0.0, 1.0,
                        context={'item_count': {'csrf_token': 'LEAK'}})

        record = self._record()
        assert record.getMessage() == 'Performance metric'
        assert 'LEAK' not in json.dumps(record.__dict__, default=str)

    def test_a_count_that_cannot_be_rendered_does_not_escape_the_helper(self):
        """The lookup was guarded; the f-string that formatted the result was
        not, so `__format__` — caller code like any other — still propagated out
        of a logging call."""
        class Unrenderable:
            def __format__(self, spec):
                raise RuntimeError('format blew up')

            def __str__(self):
                raise RuntimeError('str blew up')

        log_performance('search', 0.0, 1.0,
                        context={'item_count': Unrenderable(), 'ja_id': 'JA1'})

        record = self._record()
        assert record.getMessage() == 'Performance metric'
        assert record.ja_id == 'JA1'

    def test_a_payload_whose_truth_test_raises_does_not_escape_the_helper(self):
        """`if details:` runs the caller's `__len__` in FRONT of every guard.

        The redaction walk, the merge and the message lookup all fail closed;
        the gate that decides whether to reach them at all did not, so the
        first caller code these helpers execute was also the only unguarded
        line left.
        """
        class ExplodingLen(dict):
            def __len__(self):
                raise RuntimeError('len blew up')

        log_operation('add_item', details=ExplodingLen({'csrf_token': 'LEAK'}),
                      logger_name=LOGGER_NAME)

        record = self._record()
        assert record.csrf_token == REDACTED_VALUE
        assert 'LEAK' not in json.dumps(record.__dict__, default=str)


@pytest.mark.unit
class TestDenylistDoesNotSwallowRealFields:
    """The spec's "Block If": a denylist substring colliding with a real field
    name would silently delete data the audit trail exists to preserve. Checked
    against the actual schema and the actual forms, not against a constant.

    The first two tests below check the *sources* of audit data — `database.py`
    column names, static template `name=` attributes — and neither is what the
    redaction walk receives. The walk is handed `_item_to_audit_dict` output,
    ORM `to_dict()` snapshots, the `changes` maps and `batch_results`; a key
    that only ever exists in one of those (`Dimensions.to_dict()`'s
    `wall_thickness`, a hand-built `bulk_index`) is invisible to a column scan.
    So three further prongs enumerate the key sets the walk actually sees:

      1. `_item_to_audit_dict` exercised on a populated item, walked recursively
         — the only way to reach the nested `Dimensions`/`Thread` key sets.
      2. the five ORM `to_dict()` builders, on bare unsaved instances.
      3. an AST scan of every dict literal reaching a payload argument of the
         two audit helpers anywhere under `app/`.

    A prong that fires is NOT a licence to trim the denylist: it means a real
    audit key now collides with a secret's name, and which of the two gives way
    is a decision to take deliberately.
    """

    def test_no_database_column_name_is_redacted(self):
        source = (Path(app_package.__file__).parent / 'database.py').read_text()
        columns = set(re.findall(r'^\s+(\w+)\s*=\s*(?:Column|mapped_column)\(',
                                 source, re.MULTILINE))
        assert columns, 'column scan found nothing; the pattern has rotted'

        swallowed = sorted(c for c in columns if _is_sensitive_name(c))
        assert not swallowed, (
            f'denylist would redact real audit data: {swallowed}')

    @staticmethod
    def _template_field_names():
        """Every `name=` attribute in the templates, split literal vs computed.

        A Jinja-computed attribute is captured VERBATIM — `{{ name }}` — so the
        field it actually renders is invisible to a scan of the markup, and a
        colliding name arriving that way would sail past the check below. The
        two sets are therefore kept apart rather than pooled.
        """
        templates = APP_DIR / 'templates'
        fields = set()
        for path in templates.rglob('*.html'):
            # `[^"\']+` rather than `\w+`: a hyphenated field name is a real
            # HTML name, and skipping those would leave the collision check
            # blind to exactly the fields it exists to protect.
            fields.update(re.findall(r'<(?:input|select|textarea)\b[^>]*'
                                     r'(?<![-\w])name\s*=\s*["\']([^"\']+)["\']',
                                     path.read_text(encoding='utf-8'),
                                     re.IGNORECASE))
        computed = {f for f in fields if '{{' in f or '{%' in f}
        return fields - computed, computed

    def test_csrf_token_is_the_only_redacted_form_field(self):
        literal, _ = self._template_field_names()
        assert 'csrf_token' in literal, 'field scan has rotted'

        redacted = sorted(f for f in literal if _is_sensitive_name(f))
        assert redacted == ['csrf_token'], (
            f'denylist redacts form fields beyond the CSRF token: {redacted}')

    def test_every_dynamically_named_form_field_has_a_reviewed_source(self):
        """The blind spot in the scan above, pinned rather than left open.

        A `name="{{ … }}"` renders a field name the markup does not state, so
        the only way to check it is to name every such input and check the
        Python that supplies its keys. There is exactly one, and this assertion
        is what forces a second to be reviewed rather than silently skipped.
        """
        _, computed = self._template_field_names()

        assert computed == {'{{ name }}'}, (
            f'a template renders a form field under a computed name this test '
            f'has not reviewed: {sorted(computed)}')

    def test_the_computed_form_field_names_are_not_redacted(self):
        """`product/search.html` renders one hidden input per `prefill_args`
        entry, so its field names are that dict's KEYS.

        Those keys are whitelisted by `_PRODUCT_PREFILL_ARGS` on the way in, and
        originate in `_scan_prefill_args` / `_ecia_prefill` — so both sets are
        checked: the whitelist bounds what can ever be rendered, and the two
        builders are where a new pre-fill name would actually be introduced.
        """
        prefill_keys = set(_PRODUCT_PREFILL_ARGS)
        assert {'description', 'mpn', 'quantity'} <= prefill_keys, (
            'the prefill whitelist has rotted')

        # Exercised rather than read: the ECIA builder assembles its keys
        # conditionally, so only running it enumerates them all.
        ecia = ScanClassification(
            kind=ScanKind.ECIA, raw='[)>\x1e06', normalized_value=None,
            ecia_fields={'1P': 'SUP-1', 'P': 'CUST-1', 'Q': '5',
                         'K': 'PO-1', '1K': 'PO-2'})
        builder_keys = set(_ecia_prefill(ecia))
        for classification in (
                ecia,
                ScanClassification(kind=ScanKind.GTIN, raw='012345678905',
                                   normalized_value='00012345678905',
                                   ecia_fields=None),
                ScanClassification(kind=ScanKind.INTERNAL, raw='JA000001',
                                   normalized_value='JA000001',
                                   ecia_fields=None),
                ScanClassification(kind=ScanKind.FREE_TEXT, raw='widget',
                                   normalized_value=None, ecia_fields=None)):
            builder_keys |= set(_scan_prefill_args(classification))
        assert {'identifier_type', 'identifier_value', 'description',
                'mpn', 'vendor_sku', 'quantity', 'order_number'} <= builder_keys, (
            'the scan pre-fill builders have rotted')

        swallowed = sorted(k for k in (prefill_keys | builder_keys)
                           if _is_sensitive_name(k))
        assert not swallowed, (
            f'denylist would redact a scan pre-fill field: {swallowed}')

    def test_denylist_excludes_a_bare_key_substring(self):
        """Guards the deliberate omission: `key` would swallow `request_key`."""
        assert 'key' not in SENSITIVE_FIELD_SUBSTRINGS

    # -- Prong 1: the hand-built item audit payload -----------------------

    def test_no_key_of_the_item_audit_payload_is_redacted(self):
        """`_item_to_audit_dict` is what every inventory route logs.

        Exercised rather than pattern-matched, and on a populated item: `thread`
        is `None` on a bare instance, so its nested `Thread.to_dict()` key set —
        which the walk absolutely does reach — would otherwise never appear.
        """
        item = InventoryItem()
        item.ja_id = 'JA000001'
        item.material = 'Steel'
        item.thread_series = 'UNC'
        item.thread_handedness = 'RH'
        item.thread_size = '1/4-20'

        keys = _every_key(_item_to_audit_dict(item))

        assert {'ja_id', 'material', 'location', 'dimensions', 'thread'} <= keys, (
            f'the item audit payload has rotted: {sorted(keys)}')
        # The nested builders, which are the whole reason this is exercised.
        assert {'series', 'handedness', 'size'} <= keys, (
            'Thread.to_dict() did not materialise; the thread columns above no '
            'longer make `item.thread` truthy')
        assert {'length', 'width', 'thickness', 'wall_thickness',
                'weight'} <= keys, 'Dimensions.to_dict() has rotted'

        swallowed = sorted(k for k in keys if _is_sensitive_name(k))
        assert not swallowed, (
            f'denylist would redact real item audit data: {swallowed}')

    # -- Prong 2: the ORM snapshots ---------------------------------------

    @pytest.mark.parametrize('model', _orm_models_with_to_dict(),
                             ids=lambda m: m.__name__)
    def test_no_key_of_an_orm_audit_snapshot_is_redacted(self, model):
        """The `item_before`/`item_after` payloads the service layer logs.

        Every `to_dict()` works on a bare, unsaved instance, so no database is
        needed to enumerate what they emit — which is what lets this prong be
        parametrized over the models `Base` actually has rather than a list.
        """
        keys = _every_key(model().to_dict())
        assert keys, f'{model.__name__}.to_dict() returned nothing; it has rotted'

        swallowed = sorted(k for k in keys if _is_sensitive_name(k))
        assert not swallowed, (
            f'denylist would redact {model.__name__} audit data: {swallowed}')

    def test_the_orm_snapshot_discovery_finds_the_known_models(self):
        """Rot detection for the discovery itself.

        The parametrization above is only a guard if it finds something; a
        `Base` swapped for a different declarative base, or a `to_dict` moved
        onto a mixin, would leave it silently checking a shorter list. These
        five are the `item_before`/`item_after` snapshots named in the spec, so
        their absence means the discovery — not the schema — has broken.
        """
        discovered = set(_orm_models_with_to_dict())

        assert {InventoryItem, Product, Purchase, Attachment,
                ProductIdentifier} <= discovered, (
            f'ORM snapshot discovery has rotted; it found '
            f'{sorted(m.__name__ for m in discovered)}')

    def test_the_purchase_request_key_survives_the_denylist(self):
        """The field the denylist comment cites as the reason it carries
        `api_key`/`private_key` rather than a bare `key`. Named explicitly so
        the reason survives even if `Purchase` is one day parametrized away."""
        assert 'request_key' in Purchase().to_dict()
        assert not _is_sensitive_name('request_key')

    # -- Prong 3: the dict literals at the audit call sites ----------------

    def test_no_literal_key_at_an_audit_call_site_is_redacted(self):
        """Every `changes={…}` / `results={…}` the routes and services build.

        These never pass through a column or a form field, so nothing above
        sees them: `bulk_index`, `photos_copied` and `overall_success` exist
        only as literals at a `log_audit_operation` call.

        The floors are rot detection, not a target. A scan that stops
        recognising the code it walks reports a SMALLER set, and a guard that
        silently checks nothing is worse than no guard — so a legitimate
        removal of audit call sites means lowering these deliberately.
        """
        sites, keys, unaccounted, receivers = _scan_audit_payload_keys()

        assert PAYLOAD_PARAMS <= {
            name for helper in AUDIT_HELPERS.values()
            for name in inspect.signature(helper).parameters}, (
            'a payload parameter was renamed; the scan is matching names that '
            'no call site passes')
        assert sites >= 72, f'audit call-site scan found only {sites} calls'
        assert len(keys) >= 60, (
            f'audit payload scan resolved only {len(keys)} literal keys')
        # One key from each resolution path, so a path that breaks is named
        # rather than merely shrinking the count above.
        assert {'ja_id',                    # a literal argument, directly
                'bulk_index',               # a module-wide `context = {…}`
                'duplicate_index',          # threaded through a parameter
                'successful_count',         # a literal at a batch call site
                # `changes[key] = {'before': …, 'after': …}` — a subscript
                # assignment, the only way an incrementally built payload is
                # visible. These are the real keys of every `edit_item` changes
                # map, and until the subscript indexing went in they were
                # collected by nothing while the scan reported success.
                'before', 'after'} <= keys, (
            f'a payload resolution path has rotted: {sorted(keys)}')

        assert not unaccounted, (
            'an audit payload argument is built by something no prong covers, '
            'so its keys are unchecked:\n  ' + '\n  '.join(unaccounted))

        # The pin cannot only be checked for GROWTH: a reviewed receiver that no
        # audit call site reaches any more is a stale entry silently standing
        # ready to wave through the next thing that reuses the name.
        assert receivers == set(REVIEWED_TO_DICT_RECEIVERS), (
            'REVIEWED_TO_DICT_RECEIVERS no longer describes the `.to_dict()` '
            f'receivers at audit call sites: reached {sorted(receivers)}, '
            f'reviewed {sorted(REVIEWED_TO_DICT_RECEIVERS)}')

        swallowed = sorted(k for k in keys if _is_sensitive_name(k))
        assert not swallowed, (
            f'denylist would redact real audit data: {swallowed}')

    def test_the_json_item_payload_fields_are_not_redacted(self):
        """The coverage that makes `_normalize_json_item_payload` recognisable.

        `POST /api/inventory/items` normalizes its JSON body and hands the
        result to `_process_item_creation`, which logs it as `form_data` — so
        the scan meets it as a payload builder. Its output keys cannot be read
        off a literal (it copies whatever the caller sent), but they ARE
        bounded: anything outside `_JSON_ITEM_FIELDS` is rejected with a
        `ValueError` before the dict is built, so checking the constant checks
        every key that can ever reach the walk from there.

        Without this, recognising that builder would be an unchecked hole
        rather than a cross-reference.
        """
        assert {'material', 'location', 'notes'} <= _JSON_ITEM_FIELDS, (
            'the JSON item field whitelist has rotted')

        swallowed = sorted(f for f in _JSON_ITEM_FIELDS if _is_sensitive_name(f))
        assert not swallowed, (
            f'denylist would redact a JSON API item field: {swallowed}')

    def test_the_json_normalizer_emits_no_key_outside_the_whitelist(self):
        """...and the bound above is real, not just documented.

        Exercised, because "it rejects unknown keys" is the entire reason the
        constant is allowed to stand in for the builder's output.
        """
        assert set(_normalize_json_item_payload(
            {'material': 'Steel', 'active': True})) <= _JSON_ITEM_FIELDS

        with pytest.raises(ValueError):
            _normalize_json_item_payload({'csrf_token': 'LEAK'})


@pytest.mark.unit
class TestRedactionThroughARealRoute:
    """Proof the choke point covers real callers, not only direct helper calls.

    `POST /products/add` passes `request.form.to_dict()` verbatim into
    `log_audit_operation` (app/main/routes.py), which is exactly the leak this
    change closes.
    """

    def test_posted_csrf_token_is_redacted_in_the_emitted_record(self, client):
        inventory_logger = logging.getLogger('inventory')
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(JSONFormatter())

        previous_handlers = inventory_logger.handlers[:]
        previous_level = inventory_logger.level
        # TestConfig pins LOG_LEVEL='WARNING', so the audit INFO record would
        # otherwise be dropped before it reached any handler.
        inventory_logger.handlers = [handler]
        inventory_logger.setLevel(logging.INFO)
        try:
            client.post('/products/add', data={
                'csrf_token': 'a-real-looking-token',
                'description': 'Widget',
                'manufacturer': 'Acme',
                'mpn': 'W-1',
            })
        finally:
            inventory_logger.handlers = previous_handlers
            inventory_logger.setLevel(previous_level)

        records = [json.loads(line)
                   for line in log_capture.getvalue().splitlines() if line]
        inputs = [r for r in records
                  if r.get('audit_operation') == 'product_add'
                  and r.get('audit_phase') == 'input']
        assert inputs, 'the route emitted no product_add input audit record'

        form_data = inputs[0]['audit_data']['form_data']
        assert form_data['csrf_token'] == REDACTED_VALUE
        # ...and nothing else was touched.
        assert form_data['description'] == 'Widget'
        assert form_data['manufacturer'] == 'Acme'
        assert form_data['mpn'] == 'W-1'
        assert 'a-real-looking-token' not in log_capture.getvalue()


@pytest.mark.unit
class TestTheAuditScanFailsLoudlyOnWhatItCannotRead:
    """Rot detection for prong 3 itself, on synthetic modules.

    The prong-3 test above can only assert that the scan is happy with `app/`
    as it stands today. It cannot show that the scan would COMPLAIN about
    anything, and a tripwire that reports success on a payload it never saw is
    worse than no tripwire — so every shape the resolution is known to be
    unable to read gets a module of its own here, and has to be named in
    `unaccounted` rather than waved through.

    Each case is written the way it actually bit: with a decoy module-level
    `changes = {…}` literal present, because `_classify_builder`'s
    "a dict-literal binding and nothing else is fully accounted for" fallback is
    module-wide, and it was that fallback — not the absence of a binding — that
    made these shapes pass.
    """

    DECOY = "changes = {'decoy': 1}\n"

    def _scan(self, tmp_path, source):
        path = tmp_path / 'scan_probe.py'
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return _scan_audit_payload_keys([_ModuleIndex(path)])

    @pytest.mark.parametrize('binding', [
        'changes, _rest = svc.compute()',
        'changes: dict = svc.compute()',
        '(changes) = svc.compute()',
    ], ids=['tuple-unpack', 'annotated', 'parenthesised'])
    def test_a_binding_the_scan_cannot_attribute_is_reported(self, tmp_path,
                                                             binding):
        sites, _keys, unaccounted, _receivers = self._scan(tmp_path, f'''
            {self.DECOY}
            def leaky(svc):
                {binding}
                log_audit_operation('probe', 'input', changes=changes)
            ''')

        assert sites == 1
        assert unaccounted, (
            f'`{binding}` was waved through on the decoy literal alone')

    @pytest.mark.parametrize('statement', [
        'for changes in svc.compute():',
        'with svc.compute() as changes:',
    ], ids=['loop-target', 'with-as'])
    def test_a_statement_bound_name_is_reported(self, tmp_path, statement):
        _sites, _keys, unaccounted, _receivers = self._scan(tmp_path, f'''
            {self.DECOY}
            def leaky(svc):
                {statement}
                    log_audit_operation('probe', 'input', changes=changes)
            ''')

        assert unaccounted, f'`{statement}` was waved through'

    def test_an_aliased_import_is_still_a_call_site(self, tmp_path):
        """One `import … as` used to make a whole site invisible: not counted,
        payload never resolved, nothing flagged."""
        sites, _keys, unaccounted, _receivers = self._scan(tmp_path, '''
            from app.logging_config import log_audit_operation as _audit

            def leaky(supplied):
                _audit('probe', 'input', changes=supplied)
            ''')

        assert sites == 1, 'the aliased call site was not recognised'
        assert unaccounted, 'the aliased site contributed nothing and said so'

    def test_an_attribute_call_traces_out_to_its_callers(self, tmp_path):
        """`_calls_to` matched bare names only, so a payload parameter reached
        through `self.helper(…)` was resolved against the wrong bindings."""
        _sites, keys, _unaccounted, _receivers = self._scan(tmp_path, '''
            class Service:
                def _emit(self, payload):
                    log_audit_operation('probe', 'input', changes=payload)

                def run(self):
                    self._emit({'threaded_through_a_method': 1})
            ''')

        assert 'threaded_through_a_method' in keys

    def test_a_dict_filled_by_subscript_contributes_its_keys(self, tmp_path):
        """`payload = {}` then `payload['x'] = …` resolved to an EMPTY key set
        that the scan then reported as success."""
        _sites, keys, unaccounted, _receivers = self._scan(tmp_path, '''
            def leaky(value):
                payload = {}
                payload['access_token'] = value
                log_audit_operation('probe', 'input', changes=payload)
            ''')

        assert not unaccounted
        assert 'access_token' in keys, (
            'an incrementally filled payload was scanned as empty')

    def test_a_builder_assigned_in_by_subscript_is_still_pinned(self, tmp_path):
        """The subscript path collects the KEY; the value can still be a
        builder whose own keys no prong has seen."""
        _sites, _keys, unaccounted, receivers = self._scan(tmp_path, '''
            def leaky(thing):
                payload = {}
                payload['snap'] = thing.to_dict()
                log_audit_operation('probe', 'input', changes=payload)
            ''')

        assert receivers == {'thing'}
        assert unaccounted, 'a builder assigned in by subscript was unchecked'

    def test_an_update_from_a_non_literal_is_not_read_as_complete(self, tmp_path):
        _sites, _keys, unaccounted, _receivers = self._scan(tmp_path, '''
            def leaky(svc):
                payload = {'ja_id': 1}
                payload.update(svc.extra())
                log_audit_operation('probe', 'input', changes=payload)
            ''')

        assert unaccounted, 'a payload topped up from an opaque source passed'

    def test_a_nested_literal_contributes_its_keys(self, tmp_path):
        """The walk recurses, so the scan has to: a collision one level down
        deletes audit data just as silently as one at the top."""
        _sites, keys, unaccounted, _receivers = self._scan(tmp_path, '''
            def leaky():
                log_audit_operation('probe', 'input',
                                    changes={'location': {'session_id': 1}})
            ''')

        assert not unaccounted
        assert 'session_id' in keys

    def test_a_nested_unpack_fails_the_strict_reader(self, tmp_path):
        with pytest.raises(AssertionError, match='non-literal key'):
            self._scan(tmp_path, '''
                def leaky(other):
                    log_audit_operation('probe', 'input',
                                        changes={'location': {**other}})
                ''')

    def test_a_to_dict_nested_in_a_payload_literal_is_still_pinned(self, tmp_path):
        """`{'snap': thing.to_dict()}` put a builder one level down, where
        neither the literal reader nor `REVIEWED_TO_DICT_RECEIVERS` saw it."""
        _sites, _keys, unaccounted, receivers = self._scan(tmp_path, '''
            def leaky(thing):
                log_audit_operation('probe', 'input',
                                    item_after={'snap': thing.to_dict()})
            ''')

        assert receivers == {'thing'}
        assert unaccounted and 'no prong has been shown to cover' in unaccounted[0]

    def test_a_payload_the_scan_can_read_is_not_reported(self, tmp_path):
        """The control. Every case above asserts a COMPLAINT, which a scan that
        complained about everything would also satisfy."""
        sites, keys, unaccounted, receivers = self._scan(tmp_path, '''
            def fine(item):
                log_audit_operation('probe', 'input',
                                    changes={'ja_id': 1, 'length': 2})
            ''')

        assert (sites, unaccounted, receivers) == (1, [], set())
        assert keys == {'ja_id', 'length'}
