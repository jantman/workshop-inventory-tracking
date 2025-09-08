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
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, default=str)

def setup_logging(app):
    """Configure comprehensive logging for the application using STDOUT/STDERR"""
    
    # Configure root logger
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())
    
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