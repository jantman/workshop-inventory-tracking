"""
Custom exceptions for Workshop Inventory Tracking application.

This module defines custom exception classes for better error handling
and recovery throughout the application.
"""

class WorkshopInventoryError(Exception):
    """Base exception class for workshop inventory application"""
    
    def __init__(self, message: str, code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

class ValidationError(WorkshopInventoryError):
    """Raised when data validation fails"""
    
    def __init__(self, message: str, field: str = None, value: str = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field
        self.value = value
        self.details = {
            "field": field,
            "value": value,
            "type": "validation_error"
        }

class StorageError(WorkshopInventoryError):
    """Raised when storage operations fail"""
    
    def __init__(self, message: str, operation: str = None, original_error: Exception = None):
        super().__init__(message, code="STORAGE_ERROR")
        self.operation = operation
        self.original_error = original_error
        self.details = {
            "operation": operation,
            "original_error": str(original_error) if original_error else None,
            "type": "storage_error"
        }

class GoogleSheetsError(StorageError):
    """Raised when Google Sheets API operations fail"""
    
    def __init__(self, message: str, operation: str = None, http_status: int = None, 
                 original_error: Exception = None):
        super().__init__(message, operation, original_error)
        self.code = "GOOGLE_SHEETS_ERROR"
        self.http_status = http_status
        self.details.update({
            "http_status": http_status,
            "type": "google_sheets_error"
        })

class AuthenticationError(WorkshopInventoryError):
    """Raised when authentication/authorization fails"""
    
    def __init__(self, message: str, auth_type: str = None):
        super().__init__(message, code="AUTHENTICATION_ERROR")
        self.auth_type = auth_type
        self.details = {
            "auth_type": auth_type,
            "type": "authentication_error"
        }

class ConfigurationError(WorkshopInventoryError):
    """Raised when configuration is invalid or missing"""
    
    def __init__(self, message: str, config_key: str = None):
        super().__init__(message, code="CONFIGURATION_ERROR")
        self.config_key = config_key
        self.details = {
            "config_key": config_key,
            "type": "configuration_error"
        }

class ItemNotFoundError(WorkshopInventoryError):
    """Raised when an inventory item cannot be found"""
    
    def __init__(self, message: str, item_id: str = None, search_criteria: dict = None):
        super().__init__(message, code="ITEM_NOT_FOUND")
        self.item_id = item_id
        self.search_criteria = search_criteria
        self.details = {
            "item_id": item_id,
            "search_criteria": search_criteria,
            "type": "item_not_found"
        }

class DuplicateItemError(WorkshopInventoryError):
    """Raised when attempting to create a duplicate item"""
    
    def __init__(self, message: str, item_id: str = None, duplicate_field: str = None):
        super().__init__(message, code="DUPLICATE_ITEM")
        self.item_id = item_id
        self.duplicate_field = duplicate_field
        self.details = {
            "item_id": item_id,
            "duplicate_field": duplicate_field,
            "type": "duplicate_item"
        }

class BusinessLogicError(WorkshopInventoryError):
    """Raised when business logic rules are violated"""
    
    def __init__(self, message: str, rule: str = None, context: dict = None):
        super().__init__(message, code="BUSINESS_LOGIC_ERROR")
        self.rule = rule
        self.context = context or {}
        self.details = {
            "rule": rule,
            "context": context,
            "type": "business_logic_error"
        }

class RateLimitError(WorkshopInventoryError):
    """Raised when API rate limits are exceeded"""
    
    def __init__(self, message: str, retry_after: int = None, service: str = None):
        super().__init__(message, code="RATE_LIMIT_ERROR")
        self.retry_after = retry_after
        self.service = service
        self.details = {
            "retry_after": retry_after,
            "service": service,
            "type": "rate_limit_error"
        }

class TemporaryError(WorkshopInventoryError):
    """Raised for temporary errors that may resolve with retry"""
    
    def __init__(self, message: str, retry_count: int = 0, max_retries: int = 3):
        super().__init__(message, code="TEMPORARY_ERROR")
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.details = {
            "retry_count": retry_count,
            "max_retries": max_retries,
            "type": "temporary_error"
        }

class DataIntegrityError(WorkshopInventoryError):
    """Raised when data integrity checks fail"""
    
    def __init__(self, message: str, check_type: str = None, affected_items: list = None):
        super().__init__(message, code="DATA_INTEGRITY_ERROR")
        self.check_type = check_type
        self.affected_items = affected_items or []
        self.details = {
            "check_type": check_type,
            "affected_items": affected_items,
            "type": "data_integrity_error"
        }