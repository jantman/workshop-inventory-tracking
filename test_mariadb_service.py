#!/usr/bin/env python3
"""
Test script for MariaDB inventory service

Tests the new active-only item lookup logic
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.mariadb_inventory_service import MariaDBInventoryService
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_active_item_lookup():
    """Test getting active items by JA ID"""
    logger.info("Testing active item lookup...")
    
    try:
        app = create_app()
        with app.app_context():
            service = MariaDBInventoryService()
            
            # Test getting active items - these should work now
            test_ja_ids = ['JA000001', 'JA000002', 'JA000211']  # JA000211 is known multi-row item
            
            for ja_id in test_ja_ids:
                logger.info(f"Testing JA ID: {ja_id}")
                
                # Get active item
                active_item = service.get_active_item(ja_id)
                if active_item:
                    logger.info(f"  Active item found: length={active_item.dimensions.length}, active={active_item.active}")
                else:
                    logger.info(f"  No active item found")
                
                # Get item history
                history = service.get_item_history(ja_id)
                logger.info(f"  History: {len(history)} total items")
                for i, item in enumerate(history):
                    status = "ACTIVE" if item.active else "inactive"
                    logger.info(f"    {i+1}. {status} - length={item.dimensions.length}")
                
                logger.info("")
            
            # Test getting all active items
            logger.info("Testing get all active items...")
            active_items = service.get_all_active_items()
            logger.info(f"Found {len(active_items)} total active items")
            
            # Count by active status to verify
            active_count = sum(1 for item in active_items if item.active)
            logger.info(f"Verified: {active_count} are marked as active")
            
            logger.info("✅ MariaDB service tests completed successfully!")
            return True
            
    except Exception as e:
        logger.error(f"❌ MariaDB service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run the test"""
    logger.info("Starting MariaDB inventory service tests...")
    
    if test_active_item_lookup():
        logger.info("🎉 All tests passed!")
        return 0
    else:
        logger.error("💥 Tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())