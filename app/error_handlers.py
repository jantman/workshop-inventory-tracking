"""
Error handlers and recovery mechanisms for Workshop Inventory Tracking application.

This module provides centralized error handling, recovery strategies,
and error reporting functionality.
"""

import logging
import traceback
import time
from typing import Dict, Any, Optional, Callable, Tuple
from functools import wraps
from flask import (current_app, jsonify, flash, redirect, render_template,
                   url_for, request, session)
from werkzeug.exceptions import RequestEntityTooLarge

# The LEAF configuration error, defined in config.py so that module stays free
# of `app` imports. `app.exceptions.ConfigurationError` subclasses it, but a
# leaf instance -- which `config._bytes_from_env` and `validate_limits` can both
# produce -- is NOT an instance of the app-side class, so registering only the
# app-side handler left the leaf as an unhandled 500 inside a request context.
# Both are registered below.
from config import ConfigurationError as BootConfigurationError

from app.exceptions import (
    WorkshopInventoryError, ValidationError, StorageError, GoogleSheetsError,
    AuthenticationError, ConfigurationError, ItemNotFoundError, 
    DuplicateItemError, BusinessLogicError, RateLimitError, 
    TemporaryError, DataIntegrityError
)

class ErrorHandler:
    """Centralized error handling and recovery"""
    
    @staticmethod
    def handle_error(error: Exception, context: str = None, 
                    user_message: str = None, recovery_action: str = None) -> Dict[str, Any]:
        """
        Handle any error with appropriate logging and user feedback
        
        Args:
            error: The exception that occurred
            context: Additional context about where the error occurred
            user_message: Custom message to display to user
            recovery_action: Suggested recovery action
            
        Returns:
            Dict with error information and recovery suggestions
        """
        error_id = int(time.time() * 1000)  # Simple error ID
        
        # Log the error
        ErrorHandler._log_error(error, context, error_id)
        
        # Determine error type and create response
        if isinstance(error, WorkshopInventoryError):
            return ErrorHandler._handle_custom_error(error, error_id, user_message, recovery_action)
        else:
            return ErrorHandler._handle_generic_error(error, error_id, context, user_message, recovery_action)
    
    @staticmethod
    def _log_error(error: Exception, context: str, error_id: int):
        """Log error with full details"""
        log_data = {
            'error_id': error_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context,
            'traceback': traceback.format_exc(),
            'user_id': session.get('user_id', 'anonymous'),
            'request_url': request.url if request else None,
            'request_method': request.method if request else None
        }
        
        if isinstance(error, WorkshopInventoryError):
            log_data.update({
                'error_code': error.code,
                'error_details': error.details
            })
        
        current_app.logger.error(f"Error {error_id}: {error}", extra=log_data)
    
    @staticmethod
    def _handle_custom_error(error: WorkshopInventoryError, error_id: int, 
                           user_message: str, recovery_action: str) -> Dict[str, Any]:
        """Handle custom application errors"""
        response = {
            'success': False,
            'error_id': error_id,
            'error_code': error.code,
            'error_type': type(error).__name__,
            'message': user_message or error.message,
            'details': error.details,
            'recovery_suggestions': []
        }
        
        # Add type-specific recovery suggestions
        if isinstance(error, ValidationError):
            response['recovery_suggestions'] = [
                f"Please check the {error.field} field",
                "Ensure all required fields are filled correctly",
                "Refer to the field help text for format requirements"
            ]
        elif isinstance(error, StorageError):
            response['recovery_suggestions'] = [
                "Check your internet connection",
                "Verify Google Sheets access permissions",
                "Try refreshing the page and attempting the operation again"
            ]
        elif isinstance(error, ItemNotFoundError):
            response['recovery_suggestions'] = [
                "Verify the item ID is correct",
                "Check if the item was recently moved or deleted",
                "Try searching for the item using different criteria"
            ]
        elif isinstance(error, DuplicateItemError):
            response['recovery_suggestions'] = [
                "Check if an item with this ID already exists",
                "Consider using a different ID",
                "Update the existing item instead of creating a new one"
            ]
        
        if recovery_action:
            response['recovery_suggestions'].insert(0, recovery_action)
        
        return response
    
    @staticmethod
    def _handle_generic_error(error: Exception, error_id: int, context: str,
                            user_message: str, recovery_action: str) -> Dict[str, Any]:
        """Handle generic Python exceptions"""
        response = {
            'success': False,
            'error_id': error_id,
            'error_type': type(error).__name__,
            'message': user_message or "An unexpected error occurred",
            'context': context,
            'recovery_suggestions': [
                "Try refreshing the page",
                "Check your internet connection",
                "If the problem persists, please contact support"
            ]
        }
        
        if recovery_action:
            response['recovery_suggestions'].insert(0, recovery_action)
        
        return response

def with_error_handling(context: str = None, user_message: str = None, 
                       recovery_action: str = None, return_json: bool = False):
    """
    Decorator for automatic error handling
    
    Args:
        context: Description of the operation being performed
        user_message: Custom message to show to user on error
        recovery_action: Suggested recovery action
        return_json: Whether to return JSON response or redirect
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_info = ErrorHandler.handle_error(
                    e, context or func.__name__, user_message, recovery_action
                )
                
                if return_json or request.is_json:
                    return jsonify(error_info), 500
                else:
                    flash(error_info['message'], 'error')
                    # Try to redirect to a sensible page
                    if 'inventory' in request.endpoint:
                        return redirect(url_for('main.inventory_list'))
                    else:
                        return redirect(url_for('main.index'))
        
        return wrapper
    return decorator

def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0, 
                      max_delay: float = 60.0, exponential_base: float = 2.0):
    """
    Decorator for automatic retry with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff calculation
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):  # +1 for initial attempt
                try:
                    return func(*args, **kwargs)
                except TemporaryError as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        current_app.logger.warning(
                            f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        current_app.logger.error(f"All {max_retries + 1} attempts failed")
                        raise
                except (RateLimitError, GoogleSheetsError) as e:
                    last_exception = e
                    if attempt < max_retries and hasattr(e, 'http_status') and e.http_status == 429:
                        # Rate limit - wait longer
                        delay = min(base_delay * (exponential_base ** (attempt + 1)), max_delay)
                        current_app.logger.warning(
                            f"Rate limited, waiting {delay:.2f}s before retry {attempt + 1}"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        raise
                except Exception as e:
                    # Don't retry non-temporary errors
                    raise
            
            # If we get here, all retries were exhausted
            raise last_exception
        
        return wrapper
    return decorator

class CircuitBreaker:
    """
    Circuit breaker pattern implementation for external service calls
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0,
                 expected_exception: type = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        
        if self.state == 'OPEN':
            if self._should_attempt_reset():
                self.state = 'HALF_OPEN'
            else:
                raise TemporaryError(
                    f"Circuit breaker OPEN - service unavailable for {self.recovery_timeout}s"
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt to reset"""
        return (time.time() - self.last_failure_time) > self.recovery_timeout
    
    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        self.state = 'CLOSED'
    
    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            current_app.logger.warning(
                f"Circuit breaker OPEN after {self.failure_count} failures"
            )

# The app has TWO JSON error conventions and there is no single correct shape.
# `app/static/js/scan-capture.js:457` reads `data.error.message` (the AD-13
# OBJECT envelope built by `_catalog_json_error`); `inventory-move.js:704`
# interpolates `${result.error}` and four other clients do `data.error ||
# fallback`, all of which render "[object Object]" if handed the object shape.
# So the 413 envelope is selected BY ENDPOINT. This set is the routes that call
# `_catalog_json_error`; tests/unit/test_request_limits.py pins it structurally
# to those views, so a new catalog route that forgets to appear here is caught.
CATALOG_JSON_ENDPOINTS = frozenset({
    'main.api_scan',
    'main.api_record_purchase',
})

# Endpoints that serve BOTH a browser form navigation and a fetch() JSON client
# on the same rule, where the rule carries no `/api/` to select on.
# `main.inventory_add` renders a page for a normal submit, but for quantity > 1
# `app/static/js/inventory-add.js:702` posts the same form by `fetch()` and
# calls `response.json()` on the result. It is the only such endpoint in the app
# (tests/unit/test_request_limits.py pins that structurally).
#
# These cannot be settled by an XHR marker: that `fetch()` passes NO headers at
# all, so there is no `X-Requested-With` and the browser sends `Accept: */*`.
# What DOES separate the two callers is exactly that Accept header — a browser
# navigation sends `text/html,...,*/*;q=0.8`, which prefers HTML, while
# `fetch()`'s `*/*` does not prefer either. So for these endpoints only, answer
# JSON unless the client explicitly prefers HTML. Restricted to this set on
# purpose: applied globally the same rule would hand JSON to every `curl`
# (`Accept: */*`) hitting an ordinary HTML page.
JSON_HTML_HYBRID_ENDPOINTS = frozenset({
    'main.inventory_add',
})

# Deliberately limit-agnostic. RequestEntityTooLarge is raised by the transport
# cap in app/request_limits.py, but ALSO by Flask's untouched 500 KB
# MAX_FORM_MEMORY_SIZE and by MAX_FORM_PARTS, so naming a specific limit here
# would be wrong for two of the three causes. No byte count from the request is
# echoed back either.
#
# A FILE IS NOT THE ONLY CAUSE, and the wording must not imply it is: the
# 500 KB MAX_FORM_MEMORY_SIZE limit above is reached by a long text field with
# no file involved at all (measured: a 600 KB urlencoded POST is a 413), and the
# transport cap is reached by an over-large batch. All three remedies are named.
REQUEST_TOO_LARGE_MESSAGE = (
    'The submitted data was too large to accept. Try again with a smaller file, '
    'less text in a single field, or fewer items at once.'
)

# How much of a caller-controlled value reaches the log line. BOTH the declared
# Content-Length and the request path are attacker-chosen and effectively
# unbounded -- a 5000-digit Content-Length and a multi-kilobyte path both fit
# inside every default header budget -- so both are bounded, and both have CR/LF
# stripped: the deployment guide tells operators to aggregate the JSON log, and
# a newline in either value forges whole records in it.
LOGGED_CONTENT_LENGTH_CHARS = 32
LOGGED_PATH_CHARS = 128
LOGGED_METHOD_CHARS = 16
# Appended when a value was clipped, so a truncated value can never be read as a
# genuine short one.
LOG_TRUNCATION_MARKER = '...'


def _for_log(value, max_chars):
    """Bound `value` to `max_chars` and make it safe to put in one log record.

    CR and LF are escaped rather than dropped, so an injection attempt is
    visible in the log rather than silently normalised away, and truncation is
    marked so a clipped value cannot masquerade as a short one.
    """
    text = str(value).replace('\r', '\\r').replace('\n', '\\n')
    if len(text) > max_chars:
        return text[:max_chars] + LOG_TRUNCATION_MARKER
    return text

# Global circuit breakers for external services
google_sheets_circuit_breaker = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=30.0,
    expected_exception=GoogleSheetsError
)

def create_error_handlers(app):
    """Register error handlers with Flask application"""
    
    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        error_info = ErrorHandler.handle_error(error, "Validation")
        if request.is_json:
            return jsonify(error_info), 400
        else:
            flash(error_info['message'], 'error')
            return redirect(request.referrer or url_for('main.index'))
    
    @app.errorhandler(StorageError)
    def handle_storage_error(error):
        error_info = ErrorHandler.handle_error(error, "Storage Operation")
        if request.is_json:
            return jsonify(error_info), 500
        else:
            flash(error_info['message'], 'error')
            return redirect(url_for('main.index'))
    
    @app.errorhandler(ItemNotFoundError)
    def handle_item_not_found(error):
        error_info = ErrorHandler.handle_error(error, "Item Lookup")
        if request.is_json:
            return jsonify(error_info), 404
        else:
            flash(error_info['message'], 'warning')
            return redirect(url_for('main.inventory_list'))
    
    @app.errorhandler(AuthenticationError)
    def handle_auth_error(error):
        error_info = ErrorHandler.handle_error(error, "Authentication")
        if request.is_json:
            return jsonify(error_info), 401
        else:
            flash("Authentication required. Please sign in.", 'warning')
            return redirect(url_for('main.index'))
    
    # Registered for BOTH classes. Flask dispatches on the exception's own MRO
    # and picks the most specific registered class, so the app-side subclass
    # still lands here; without the leaf registration a bare
    # `config.ConfigurationError` raised in a request context was an unhandled
    # 500 -- a catchable configuration-error class sitting outside the dispatch
    # its own docstring documents.
    @app.errorhandler(BootConfigurationError)
    @app.errorhandler(ConfigurationError)
    def handle_config_error(error):
        error_info = ErrorHandler.handle_error(error, "Configuration")
        if request.is_json:
            return jsonify(error_info), 500
        else:
            flash("Application configuration error. Please check setup.", 'error')
            return redirect(url_for('main.index'))
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        error_info = ErrorHandler.handle_error(error, "Internal Server Error")
        if request.is_json:
            return jsonify(error_info), 500
        else:
            flash("An internal error occurred. Please try again.", 'error')
            return redirect(url_for('main.index'))
    
    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(error):
        """413 for a body over the transport cap (app/request_limits.py) or over
        Flask's form-field limits.

        Two deliberate divergences from the sibling handlers above:

        1. The HTML branch RENDERS a page instead of flash-and-redirect. A
           redirect answering a rejected POST throws away the error context, and
           an earlier iteration derived the redirect target from `Referer` —
           which produced an open redirect, a `javascript://` scheme bypass, a
           `urlsplit` ValueError 500 on `Referer: http://[::1`, and a
           self-redirect loop under a non-root SCRIPT_NAME. No response target
           here is derived from any request header, so no header can steer it.
        2. The JSON envelope is chosen by endpoint; see CATALOG_JSON_ENDPOINTS.

        This handler must not raise for ANY request shape: it runs ahead of
        every view, so an exception escaping it is a 500 with nothing left to
        catch it. Hence the raw environ read below rather than
        `request.content_length`, whose Werkzeug parse can itself raise on a
        hostile value.
        """
        # EVERY value below is caller-controlled, so every one of them is
        # bounded and CR/LF-escaped -- not just the header. `request.path` is
        # attacker-chosen, effectively unbounded, and can carry an encoded
        # newline; echoing it raw next to a carefully truncated Content-Length
        # was a defect, not a difference in kind.
        declared_length = request.environ.get('CONTENT_LENGTH')
        if declared_length is None or not str(declared_length).strip():
            declared_length = 'unknown'
        else:
            declared_length = _for_log(declared_length, LOGGED_CONTENT_LENGTH_CHARS)
        current_app.logger.warning(
            'Request body rejected as too large: %s %s (Content-Length: %s)',
            _for_log(request.method, LOGGED_METHOD_CHARS),
            _for_log(request.path, LOGGED_PATH_CHARS),
            declared_length)

        # The JSON branch is chosen from EVIDENCE THAT IS NOT CALLER-CHOSEN
        # TEXT. `request.is_json` reads the declared content type, and
        # `request.url_rule.rule` is the *registered* rule string -- written in
        # this repo, not by the caller. An earlier iteration used
        # `'/api/' in request.path`: `startswith` misses
        # `/admin/api/materials/validate`, but a bare `in` is a substring test
        # on a URL the caller picks, so an HTML route carrying that substring
        # anywhere (a product slug, `/products/edit/api/x`) was answered with
        # JSON instead of the rendered page. Testing the rule keeps
        # `/admin/api/...` covered without that.
        #
        # If the endpoint is unresolved -- the rejection happened before routing
        # -- `url_rule` is None and this falls through to `is_json` and then to
        # the HTML branch, which is the right default for a browser.
        # Not every JSON consumer lives under `/api/`. `main.inventory_add`
        # posts a FormData by fetch() and calls `response.json()` on the result
        # (app/static/js/inventory-add.js:702), and its rule is `/inventory/add`
        # -- so rule-matching alone hands that caller an HTML page and its
        # `response.json()` throws, losing the message entirely. Selecting on
        # the RESOLVED ENDPOINT is what settles it.
        #
        # TWO EARLIER LIMBS ARE DELIBERATELY ABSENT, and both were live in this
        # expression while the comment above already described them as retired:
        #
        # * `X-Requested-With: XMLHttpRequest` -- dead code for every caller in
        #   this repo (`grep -rn X-Requested-With app/static/js/` is empty, and
        #   test_no_client_in_this_repo_sends_the_xhr_marker pins that), but NOT
        #   dead for an arbitrary caller: it is a request header, so keeping it
        #   let anyone choose the response format of an HTML page. Measured: an
        #   oversize `POST /products/edit/1` carrying it returned
        #   `application/json` instead of the rendered 413.
        # * an unscoped `accept_mimetypes.best == 'application/json'` -- this is
        #   exactly the global Accept rule that JSON_HTML_HYBRID_ENDPOINTS' own
        #   comment says was rejected on purpose. Measured: the same oversize
        #   POST to that HTML route with axios' default
        #   `Accept: application/json, text/plain, */*` returned JSON.
        #
        # So Accept gets a vote ONLY for the hybrid endpoints, and only to hand
        # the HTML branch back to a real browser navigation, which prefers
        # `text/html` explicitly -- see JSON_HTML_HYBRID_ENDPOINTS.
        rule = request.url_rule.rule if request.url_rule is not None else ''
        wants_json = (
            request.endpoint in JSON_HTML_HYBRID_ENDPOINTS
            and (request.accept_mimetypes['application/json']
                 >= request.accept_mimetypes['text/html'])
        )
        if request.is_json or '/api/' in rule or wants_json:
            if request.endpoint in CATALOG_JSON_ENDPOINTS:
                error_body = {'code': 'request_too_large',
                              'message': REQUEST_TOO_LARGE_MESSAGE}
            else:
                error_body = REQUEST_TOO_LARGE_MESSAGE
            return jsonify({
                'success': False,
                'error': error_body,
                # Top level as well, for photo-manager.js:338, which reads
                # `errorData.message`.
                'message': REQUEST_TOO_LARGE_MESSAGE,
            }), 413

        try:
            return render_template('errors/413.html'), 413
        except Exception:
            # The render is the last thing here that can raise, and this handler
            # exists to prevent 500s -- so a Jinja error, a missing template, or
            # an endpoint `base.html` cannot resolve must degrade to a plain but
            # correct 413 rather than to the unhandled 500 the handler was
            # written to stop. Logged as an exception because a broken error
            # page is a real defect, just not one the caller should pay for.
            current_app.logger.exception(
                'errors/413.html could not be rendered; falling back to plain '
                'text so the rejection is still a 413')
            return REQUEST_TOO_LARGE_MESSAGE, 413, {'Content-Type':
                                                    'text/plain; charset=utf-8'}

    @app.errorhandler(404)
    def handle_not_found(error):
        if request.is_json:
            return jsonify({
                'success': False,
                'error': 'Resource not found',
                'message': 'The requested resource was not found'
            }), 404
        else:
            flash("Page not found", 'warning')
            return redirect(url_for('main.index'))