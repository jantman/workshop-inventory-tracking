import logging
import logging.handlers
import os
import json
from datetime import datetime
from flask import request, session, g

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
    
    if form_data:
        data_section['form_data'] = form_data
    
    if item_before:
        data_section['item_before'] = item_before
    
    if item_after:
        data_section['item_after'] = item_after
        
    if changes:
        data_section['changes'] = changes
        
    if error_details:
        data_section['error_details'] = error_details
    
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
        data_section['batch_input'] = batch_data
    if results:
        data_section['batch_results'] = results
    if error_details:
        data_section['error_details'] = error_details
        
    if data_section:
        audit_data['audit_data'] = data_section
    
    message = f"AUDIT: {operation_name} batch_phase={phase}"
    if results and 'successful_count' in results:
        message += f" processed={results['successful_count']}"
    
    logger.info(message, extra=audit_data)