import logging
import logging.handlers
import os
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence, Set
from datetime import datetime
from flask import request, session, g

# Field-name substrings whose VALUES must never reach the audit log. Matched
# case-insensitively as substrings, so `csrf_token`, `CSRF_Token` and
# `X_CSRFToken` are all caught by `csrf`/`token` alike.
#
# Deliberately no bare `key`: it would swallow the legitimate `request_key`
# field (app/database.py) that the audit trail needs for reconstruction, hence
# `api_key` / `private_key` instead.
SENSITIVE_FIELD_SUBSTRINGS = (
    'csrf',
    'token',
    'password',
    'passwd',
    'secret',
    'api_key',
    'apikey',
    'authorization',
    'credential',
    'private_key',
    'session',
)

# What a redacted value is replaced with. The key itself is kept, so the audit
# record still shows that the field was submitted.
REDACTED_VALUE = '[REDACTED]'

# How deep the redaction walk goes before it gives up. Beyond this the subtree
# is replaced wholesale rather than passed through: an audit payload nested this
# deeply is not something this app produces, and a depth guard on a security
# control must fail closed, not emit unfiltered caller data.
MAX_REDACTION_DEPTH = 8

def _is_sensitive_name(name) -> bool:
    """True if a mapping key names a secret that must not be logged."""
    if not isinstance(name, str):
        # A non-`str` key is coerced rather than skipped: `b'csrf_token'` or an
        # Enum member must not be a way around the denylist. An object whose
        # repr blows up is treated as sensitive -- fail closed, as everywhere
        # else in this helper.
        try:
            name = str(name)
        except Exception:
            return True
    lowered = name.lower()
    return any(marker in lowered for marker in SENSITIVE_FIELD_SUBSTRINGS)

def _serializable_key(key):
    """A mapping key `json.dumps` will accept.

    `JSONFormatter` passes `default=str`, which applies to VALUES only -- a
    non-`str`/`int`/`float`/`bool`/`None` key raises `TypeError` out of
    `json.dumps`, the handler swallows it, and the ENTIRE audit record is lost.
    Redacting a `b'csrf_token'` value and then dropping the record it lived in
    trades a leak for a hole in the audit trail, so the key is coerced too.
    """
    if key is None or isinstance(key, (str, int, float, bool)):
        return key
    if isinstance(key, (bytes, bytearray)):
        return key.decode('utf-8', 'replace')
    try:
        return str(key)
    except Exception:
        # Same fail-closed posture as `_is_sensitive_name`: an unrenderable key
        # becomes the marker rather than taking the record down with it.
        return REDACTED_VALUE

def _redact_payload(value):
    """Fail-closed entry point for the audit helpers.

    `_redact_sensitive` walks caller-supplied objects, and a payload whose
    `items()` or iteration raises would otherwise propagate out of a *logging*
    call and fail the request it was only meant to describe. A logging helper
    must never be the thing that breaks its caller, so the whole payload
    collapses to the marker instead -- fail closed, never fail open.
    """
    try:
        return _redact_sensitive(value)
    except Exception:
        return REDACTED_VALUE

def _redact_sensitive(value, _depth: int = 0):
    """
    Return a redacted COPY of a log payload.

    Recurses into nested mappings and lists/tuples of mappings; any key
    matching SENSITIVE_FIELD_SUBSTRINGS has its value replaced with
    REDACTED_VALUE. The caller's object is never mutated, and scalar values are
    passed through untouched.

    Container recognition is by ABC, not by concrete type, in BOTH directions:
    any `collections.abc.Mapping` (a `MultiDict`, a SQLAlchemy `RowMapping`)
    and any non-string `Sequence`/`Set`/re-iterable `Iterable` (a `deque`, a
    `dict_values` view, a `frozenset`) is walked. Anything handed back
    untouched is `str()`-ed into the record by `JSONFormatter`'s `default=str`
    with its secret intact, so an unrecognised container is a silent bypass.
    Namedtuples are walked by field name for the same reason. Mapping keys are
    coerced to a JSON-serializable form, since a key `json.dumps` rejects would
    cost the whole record.

    Two boundaries this deliberately does NOT cover, so that callers are not
    misled about what the choke point guarantees:
      * redaction is key-based -- a secret sitting in a *value* under a benign
        key (an exception message quoting a token, say) is not detectable here;
      * an arbitrary object is treated as a scalar. Reflecting over `__dict__`
        on a logging path risks dragging in ORM instrumentation state, which is
        a worse failure than the one it would prevent. Pass a dict.

    Past MAX_REDACTION_DEPTH the container is replaced with REDACTED_VALUE
    rather than returned as-is, so a payload too deep to walk cannot smuggle a
    secret through the gap.
    """
    # `str`/`bytes` are sequences; they must not be walked character by byte.
    if isinstance(value, (str, bytes, bytearray)):
        return value

    # A namedtuple carries field names, so it is redacted as a mapping rather
    # than positionally -- otherwise a named secret survives the walk.
    as_dict = getattr(value, '_asdict', None)
    if isinstance(value, tuple) and callable(as_dict):
        return _redact_sensitive(as_dict(), _depth)

    is_mapping = isinstance(value, Mapping)
    # By ABC, not by concrete type: `deque`, `dict_values` and `frozenset` are
    # none of `list`/`tuple`, and each would otherwise be handed to
    # `JSONFormatter` to be `str()`-ed out with any nested secret intact.
    is_iterable = not is_mapping and isinstance(value, Iterable)
    if not (is_mapping or is_iterable):
        return value

    if _depth > MAX_REDACTION_DEPTH:
        return REDACTED_VALUE

    if is_mapping:
        return {
            _serializable_key(key): (
                REDACTED_VALUE if _is_sensitive_name(key)
                else _redact_sensitive(item, _depth + 1))
            for key, item in value.items()
        }

    if isinstance(value, Iterator):
        # A one-shot iterator cannot be walked without consuming the caller's
        # object, which "never mutate the caller" forbids -- and passing it
        # through would be a bypass. Neither, so: fail closed.
        return REDACTED_VALUE
    if not isinstance(value, (Sequence, Set)):
        # A re-iterable that is neither (a `dict_values` view, say). Safe to
        # walk; there is no meaningful container type to reconstruct.
        return [_redact_sensitive(item, _depth + 1) for item in value]

    redacted = [_redact_sensitive(item, _depth + 1) for item in value]
    # A copy, not a coercion: a tuple in must not silently become a list out.
    # A `Set` still becomes a list -- redacted members are not hashable, and
    # JSON has no set anyway.
    return tuple(redacted) if isinstance(value, tuple) else redacted

class AuditLogFilter(logging.Filter):
    """Filter to add audit trail information to log records"""
    
    def filter(self, record):
        # Add request context if available
        if request:
            record.url = request.url
            record.method = request.method
            record.remote_addr = request.remote_addr
            record.user_agent = request.headers.get('User-Agent', 'Unknown')
            record.user_id = session.get('user_id', 'anonymous')
        else:
            record.url = 'N/A'
            record.method = 'N/A'
            record.remote_addr = 'N/A'
            record.user_agent = 'N/A'
            record.user_id = 'system'
        
        return True

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add request context if available
        if hasattr(record, 'url'):
            log_entry['request'] = {
                'url': record.url,
                'method': record.method,
                'remote_addr': record.remote_addr,
                'user_agent': record.user_agent,
                'user_id': record.user_id
            }
        
        # Add extra fields from record
        if hasattr(record, 'error_id'):
            log_entry['error_id'] = record.error_id
        if hasattr(record, 'error_code'):
            log_entry['error_code'] = record.error_code
        if hasattr(record, 'error_details'):
            log_entry['error_details'] = record.error_details
        if hasattr(record, 'operation'):
            log_entry['operation'] = record.operation
        if hasattr(record, 'item_id'):
            log_entry['item_id'] = record.item_id
        if hasattr(record, 'duration'):
            log_entry['duration_ms'] = record.duration
        
        # Add audit-specific fields for comprehensive audit logging
        if hasattr(record, 'audit_operation'):
            log_entry['audit_operation'] = record.audit_operation
        if hasattr(record, 'audit_phase'):
            log_entry['audit_phase'] = record.audit_phase
        if hasattr(record, 'audit_timestamp'):
            log_entry['audit_timestamp'] = record.audit_timestamp
        if hasattr(record, 'audit_data'):
            log_entry['audit_data'] = record.audit_data
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, default=str)

def setup_logging(app):
    """Configure comprehensive logging for the application using STDOUT/STDERR"""
    
    # Configure root logger
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JSONFormatter())
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # Create audit filter
    audit_filter = AuditLogFilter()
    
    # STDOUT handler for general logs
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(JSONFormatter())
    stdout_handler.addFilter(audit_filter)
    stdout_handler.setLevel(log_level)
    
    # STDERR handler for errors
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(logging.Formatter(
        '%(asctime)s ERROR [%(user_id)s@%(remote_addr)s] %(message)s\nURL: %(url)s\nMethod: %(method)s\nUser-Agent: %(user_agent)s\n%(pathname)s:%(lineno)d\n'
    ))
    stderr_handler.addFilter(audit_filter)
    stderr_handler.setLevel(logging.ERROR)
    
    # Configure Flask app logger
    app.logger.handlers.clear()  # Clear default handlers
    app.logger.addHandler(stdout_handler)
    app.logger.addHandler(stderr_handler)
    app.logger.setLevel(log_level)
    
    # Create specialized loggers - all using STDOUT with structured JSON
    app.logger.info('Setting up specialized loggers')
    
    # Performance logger
    perf_logger = logging.getLogger('performance')
    perf_logger.addHandler(stdout_handler)
    perf_logger.setLevel(logging.INFO)
    
    # API access logger
    api_logger = logging.getLogger('api_access')
    api_logger.addHandler(stdout_handler)
    api_logger.setLevel(logging.INFO)
    
    # Google Sheets API logger
    sheets_logger = logging.getLogger('google_sheets')
    sheets_logger.addHandler(stdout_handler)
    sheets_logger.setLevel(log_level)
    
    # Inventory operations logger
    inventory_logger = logging.getLogger('inventory')
    inventory_logger.addHandler(stdout_handler)
    inventory_logger.setLevel(log_level)

    # Catalog service operations logger (Products/Purchases)
    catalog_logger = logging.getLogger('mariadb_catalog_service')
    catalog_logger.addHandler(stdout_handler)
    catalog_logger.setLevel(log_level)
    
    # Log startup information
    app.logger.info(f'Workshop Inventory Tracking started - Debug: {app.debug}, Log Level: {logging.getLevelName(log_level)}')
    
    # Configure werkzeug logger to reduce noise in development
    if app.debug:
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # Log configuration details
    app.logger.info('Logging configuration complete - using STDOUT/STDERR')
    
    return app.logger

def log_operation(operation_name: str, duration_ms: int = None, item_id: str = None, 
                 details: dict = None, logger_name: str = 'inventory'):
    """
    Log an inventory operation with structured data
    
    Args:
        operation_name: Name of the operation (e.g., 'add_item', 'move_item')
        duration_ms: Operation duration in milliseconds
        item_id: ID of the item being operated on
        details: Additional operation details
        logger_name: Which logger to use
    """
    logger = logging.getLogger(logger_name)
    
    extra_data = {
        'operation': operation_name
    }
    
    if duration_ms is not None:
        extra_data['duration'] = duration_ms
    if item_id:
        extra_data['item_id'] = item_id
    if details:
        extra_data.update(details)
    
    message = f"Operation '{operation_name}'"
    if item_id:
        message += f" on item {item_id}"
    if duration_ms:
        message += f" completed in {duration_ms}ms"
    
    logger.info(message, extra=extra_data)

def log_api_access(endpoint: str, status_code: int, response_time_ms: int = None, 
                   result_count: int = None):
    """
    Log API access with performance metrics
    
    Args:
        endpoint: The API endpoint accessed
        status_code: HTTP status code returned
        response_time_ms: Response time in milliseconds
        result_count: Number of results returned (for list operations)
    """
    logger = logging.getLogger('api_access')
    
    message = f"Status {status_code}"
    if response_time_ms:
        message += f" in {response_time_ms}ms"
    if result_count is not None:
        message += f" ({result_count} results)"
    
    extra_data = {
        'endpoint': endpoint,
        'status_code': status_code
    }
    
    if response_time_ms:
        extra_data['response_time_ms'] = response_time_ms
    if result_count is not None:
        extra_data['result_count'] = result_count
    
    logger.info(message, extra=extra_data)

def log_performance(operation: str, start_time: float, end_time: float, 
                   context: dict = None):
    """
    Log performance metrics for operations
    
    Args:
        operation: Name of the operation
        start_time: Start timestamp (from time.time())
        end_time: End timestamp (from time.time())
        context: Additional context information
    """
    duration_ms = int((end_time - start_time) * 1000)
    logger = logging.getLogger('performance')
    
    extra_data = {
        'operation': operation,
        'duration': duration_ms
    }
    
    if context:
        extra_data.update(context)
    
    message = f"Performance metric"
    if context and 'item_count' in context:
        message += f" (processed {context['item_count']} items)"
    
    logger.info(message, extra=extra_data)

def log_audit_operation(operation_name: str, phase: str, item_id: str = None, 
                       form_data: dict = None, item_before: dict = None, 
                       item_after: dict = None, changes: dict = None, 
                       error_details: str = None, logger_name: str = 'inventory'):
    """
    Log comprehensive audit trail for inventory operations to enable data reconstruction
    
    Args:
        operation_name: Name of the operation (add_item, edit_item, move_items, shorten_item)
        phase: Phase of operation (input, success, error)
        item_id: JA ID of item being operated on
        form_data: Complete form data submitted by user
        item_before: InventoryItem state before operation (for edits/updates)
        item_after: InventoryItem state after operation
        changes: Dictionary of changed fields (for edits)
        error_details: Error information if operation failed
        logger_name: Logger to use (defaults to 'inventory')
    """
    logger = logging.getLogger(logger_name)
    
    # Build audit data structure
    audit_data = {
        'audit_operation': operation_name,
        'audit_phase': phase,
        'audit_timestamp': datetime.now().isoformat()
    }
    
    if item_id:
        audit_data['item_id'] = item_id
    
    # Add data based on phase and available information
    data_section = {}
    
    # Every payload of this helper goes through the redaction choke point, so a
    # caller cannot leak a submitted csrf_token (or any other field whose NAME
    # matches SENSITIVE_FIELD_SUBSTRINGS) into the audit trail, and no future
    # caller has to remember to strip one. See `_redact_sensitive` for what
    # that does and does not cover -- notably it is key-based, so a secret in a
    # value is not caught. (Sibling helpers `log_operation` / `log_performance`
    # take free-form dicts that are NOT redacted -- they are not audit trail.)
    if form_data:
        data_section['form_data'] = _redact_payload(form_data)

    if item_before:
        data_section['item_before'] = _redact_payload(item_before)

    if item_after:
        data_section['item_after'] = _redact_payload(item_after)

    if changes:
        data_section['changes'] = _redact_payload(changes)

    # Annotated `str`, but Python does not enforce that; routing it through the
    # same helper is a no-op for strings and closes the hole if a caller ever
    # hands over a dict.
    if error_details:
        data_section['error_details'] = _redact_payload(error_details)

    if data_section:
        audit_data['audit_data'] = data_section

    # Create human-readable message
    message_parts = [f"AUDIT: {operation_name}"]
    if item_id:
        message_parts.append(f"item={item_id}")
    message_parts.append(f"phase={phase}")
    
    if phase == 'input':
        message_parts.append("capturing user input for reconstruction")
    elif phase == 'success':
        message_parts.append("operation completed successfully")
    elif phase == 'error':
        message_parts.append("operation failed")
    
    message = " ".join(message_parts)
    
    # Log with audit data as extra fields for JSON formatter
    logger.info(message, extra=audit_data)

def log_audit_batch_operation(operation_name: str, phase: str, batch_data: dict = None,
                             results: dict = None, error_details: str = None):
    """
    Log audit trail for batch operations (like batch move)
    
    Args:
        operation_name: Name of batch operation
        phase: Phase of operation (input, success, error)
        batch_data: Complete batch input data
        results: Batch operation results
        error_details: Error information if operation failed
    """
    logger = logging.getLogger('inventory')
    
    audit_data = {
        'audit_operation': operation_name,
        'audit_phase': phase,
        'audit_timestamp': datetime.now().isoformat(),
        'audit_batch': True
    }
    
    data_section = {}
    if batch_data:
        data_section['batch_input'] = _redact_payload(batch_data)
    if results:
        data_section['batch_results'] = _redact_payload(results)
    if error_details:
        data_section['error_details'] = _redact_payload(error_details)

    if data_section:
        audit_data['audit_data'] = data_section
    
    message = f"AUDIT: {operation_name} batch_phase={phase}"
    if results and 'successful_count' in results:
        message += f" processed={results['successful_count']}"
    
    logger.info(message, extra=audit_data)