"""
Performance optimization utilities for Workshop Inventory Tracking application.

This module provides caching, batch operations, and performance monitoring
to optimize Google Sheets API usage and overall application performance.
"""

import time
import functools
from typing import Dict, Any, List, Optional, Callable, Tuple
from threading import Lock
from datetime import datetime, timedelta
import json
import hashlib
import logging

from app.logging_config import log_performance

logger = logging.getLogger(__name__)

# Simple in-memory cache for Google Sheets data
class SimpleCache:
    """Thread-safe in-memory cache with TTL support"""
    
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if datetime.now() < entry['expires']:
                    logger.debug(f"Cache HIT for key: {key}")
                    return entry['value']
                else:
                    # Expired, remove it
                    del self._cache[key]
                    logger.debug(f"Cache EXPIRED for key: {key}")
            
            logger.debug(f"Cache MISS for key: {key}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """Set value in cache with TTL"""
        ttl = ttl or self.default_ttl
        expires = datetime.now() + timedelta(seconds=ttl)
        
        with self._lock:
            self._cache[key] = {
                'value': value,
                'expires': expires,
                'created': datetime.now()
            }
            logger.debug(f"Cache SET for key: {key}, TTL: {ttl}s")
    
    def delete(self, key: str) -> None:
        """Remove key from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache DELETE for key: {key}")
    
    def clear(self) -> None:
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
            logger.info("Cache cleared")
    
    def cleanup_expired(self) -> int:
        """Remove expired entries and return count of removed items"""
        now = datetime.now()
        expired_keys = []
        
        with self._lock:
            for key, entry in self._cache.items():
                if now >= entry['expires']:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            now = datetime.now()
            active_count = sum(1 for entry in self._cache.values() if now < entry['expires'])
            expired_count = len(self._cache) - active_count
            
            return {
                'total_entries': len(self._cache),
                'active_entries': active_count,
                'expired_entries': expired_count,
                'memory_usage_estimate': sum(
                    len(str(entry['value'])) for entry in self._cache.values()
                )
            }

# Global cache instance
cache = SimpleCache(default_ttl=300)  # 5 minutes

def cache_key(*args, **kwargs) -> str:
    """Generate cache key from function arguments"""
    key_data = {
        'args': args,
        'kwargs': sorted(kwargs.items())
    }
    key_json = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.md5(key_json.encode()).hexdigest()

def cached(ttl: int = 300, cache_instance: SimpleCache = None):
    """
    Decorator to cache function results
    
    Args:
        ttl: Time to live in seconds
        cache_instance: Cache instance to use (defaults to global cache)
    """
    def decorator(func: Callable) -> Callable:
        nonlocal cache_instance
        if cache_instance is None:
            cache_instance = cache
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key = f"{func.__name__}:{cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            result = cache_instance.get(key)
            if result is not None:
                return result
            
            # Execute function and cache result
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            
            # Cache the result
            cache_instance.set(key, result, ttl)
            
            # Log performance
            log_performance(
                f"cached_{func.__name__}",
                start_time,
                end_time,
                {'cache_miss': True, 'ttl': ttl}
            )
            
            return result
        
        # Add cache management methods to wrapper
        wrapper.cache_clear = lambda: cache_instance.clear()
        wrapper.cache_delete = lambda *args, **kwargs: cache_instance.delete(
            f"{func.__name__}:{cache_key(*args, **kwargs)}"
        )
        
        return wrapper
    return decorator

def timed(operation_name: str = None):
    """
    Decorator to time function execution and log performance metrics
    
    Args:
        operation_name: Custom name for the operation (defaults to function name)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                end_time = time.time()
                
                # Log successful operation
                log_performance(op_name, start_time, end_time, {
                    'success': True,
                    'args_count': len(args),
                    'kwargs_count': len(kwargs)
                })
                
                return result
            
            except Exception as e:
                end_time = time.time()
                
                # Log failed operation
                log_performance(op_name, start_time, end_time, {
                    'success': False,
                    'error': str(e),
                    'args_count': len(args),
                    'kwargs_count': len(kwargs)
                })
                
                raise
        
        return wrapper
    return decorator

class BatchOperationManager:
    """Manages batch operations to minimize API calls"""
    
    def __init__(self, max_batch_size: int = 100, flush_interval: float = 5.0):
        self.max_batch_size = max_batch_size
        self.flush_interval = flush_interval
        self._batches: Dict[str, List[Any]] = {}
        self._last_flush: Dict[str, float] = {}
        self._lock = Lock()
    
    def add_to_batch(self, batch_name: str, item: Any) -> bool:
        """
        Add item to batch. Returns True if batch should be flushed.
        
        Args:
            batch_name: Name of the batch
            item: Item to add to batch
            
        Returns:
            True if batch is ready to flush
        """
        with self._lock:
            if batch_name not in self._batches:
                self._batches[batch_name] = []
                self._last_flush[batch_name] = time.time()
            
            self._batches[batch_name].append(item)
            
            # Check if we should flush
            current_time = time.time()
            should_flush = (
                len(self._batches[batch_name]) >= self.max_batch_size or
                (current_time - self._last_flush[batch_name]) >= self.flush_interval
            )
            
            return should_flush
    
    def get_batch(self, batch_name: str) -> List[Any]:
        """Get and clear batch"""
        with self._lock:
            batch = self._batches.get(batch_name, [])
            self._batches[batch_name] = []
            self._last_flush[batch_name] = time.time()
            return batch
    
    def flush_all(self) -> Dict[str, List[Any]]:
        """Get and clear all batches"""
        with self._lock:
            result = dict(self._batches)
            self._batches.clear()
            current_time = time.time()
            for batch_name in result:
                self._last_flush[batch_name] = current_time
            return result

# Global batch manager
batch_manager = BatchOperationManager()

class PerformanceMonitor:
    """Monitor and report on application performance"""
    
    def __init__(self):
        self._metrics: Dict[str, List[float]] = {}
        self._lock = Lock()
    
    def record_timing(self, operation: str, duration_ms: float):
        """Record timing for an operation"""
        with self._lock:
            if operation not in self._metrics:
                self._metrics[operation] = []
            
            self._metrics[operation].append(duration_ms)
            
            # Keep only last 1000 measurements per operation
            if len(self._metrics[operation]) > 1000:
                self._metrics[operation] = self._metrics[operation][-1000:]
    
    def get_stats(self, operation: str = None) -> Dict[str, Any]:
        """Get performance statistics"""
        with self._lock:
            if operation:
                # Stats for specific operation
                if operation not in self._metrics or not self._metrics[operation]:
                    return {'operation': operation, 'count': 0}
                
                timings = self._metrics[operation]
                return {
                    'operation': operation,
                    'count': len(timings),
                    'avg_ms': sum(timings) / len(timings),
                    'min_ms': min(timings),
                    'max_ms': max(timings),
                    'p95_ms': sorted(timings)[int(len(timings) * 0.95)] if len(timings) > 1 else timings[0]
                }
            else:
                # Stats for all operations
                return {
                    op: self.get_stats(op)
                    for op in self._metrics.keys()
                }
    
    def clear_stats(self, operation: str = None):
        """Clear performance statistics"""
        with self._lock:
            if operation:
                if operation in self._metrics:
                    del self._metrics[operation]
            else:
                self._metrics.clear()

# Global performance monitor
performance_monitor = PerformanceMonitor()

def optimize_sheets_query(sheet_name: str, filters: Dict[str, Any] = None, 
                         limit: int = None, offset: int = 0) -> str:
    """
    Optimize Google Sheets query by constructing efficient range specifications
    
    Args:
        sheet_name: Name of the sheet
        filters: Filters to apply (for future optimization)
        limit: Maximum number of rows to return
        offset: Number of rows to skip
        
    Returns:
        Optimized range specification
    """
    if limit is not None:
        start_row = offset + 1  # Google Sheets is 1-indexed
        end_row = start_row + limit - 1
        range_spec = f"{sheet_name}!{start_row}:{end_row}"
    else:
        range_spec = sheet_name
    
    logger.debug(f"Optimized query range: {range_spec}")
    return range_spec

def batch_sheets_operations(operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Combine multiple Google Sheets operations into batch requests
    
    Args:
        operations: List of operation dictionaries
        
    Returns:
        List of batch request dictionaries
    """
    # Group operations by type for batching
    reads = []
    writes = []
    updates = []
    
    for op in operations:
        if op['type'] == 'read':
            reads.append(op)
        elif op['type'] == 'write':
            writes.append(op)
        elif op['type'] == 'update':
            updates.append(op)
    
    batches = []
    
    # Batch read operations
    if reads:
        batches.append({
            'type': 'batch_read',
            'operations': reads
        })
    
    # Batch write operations (append)
    if writes:
        batches.append({
            'type': 'batch_write',
            'operations': writes
        })
    
    # Batch update operations
    if updates:
        batches.append({
            'type': 'batch_update',
            'operations': updates
        })
    
    logger.info(f"Optimized {len(operations)} operations into {len(batches)} batches")
    return batches

def cleanup_performance_data():
    """Periodic cleanup of performance data and cache"""
    try:
        # Clean expired cache entries
        expired_count = cache.cleanup_expired()
        
        # Get cache stats
        cache_stats = cache.stats()
        
        # Log cleanup results
        logger.info(f"Performance cleanup: {expired_count} expired cache entries removed")
        logger.info(f"Cache stats: {cache_stats}")
        
        # Clear old performance metrics (keep only recent data)
        performance_monitor.clear_stats()
        
        return {
            'expired_cache_entries': expired_count,
            'cache_stats': cache_stats,
            'cleanup_time': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error during performance cleanup: {e}")
        return {'error': str(e)}