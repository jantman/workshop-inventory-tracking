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
from flask import current_app, jsonify, flash, redirect, url_for, request, session

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