#!/usr/bin/env python3
"""
Material Migration Tool with Rate Limit Handling

Migrates existing Material column values in the Metal sheet to use hierarchical taxonomy.
Automatically handles Google Sheets API rate limits by waiting for quota reset.
Maps 73 existing material names to appropriate taxonomy entries at flexible specificity levels.
"""

import os
import sys
import time
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app import create_app


def create_material_mapping() -> Dict[str, str]:
    """
    Create mapping from existing material names to taxonomy entries.
    Based on analysis of 505 inventory items with 73 unique materials.
    """
    
    # Direct mappings to specific materials (Level 3)
    specific_mappings = {
        # Carbon Steel - Specific grades
        '4140': '4140',
        '4140 ?': '4140',  # Remove uncertainty
        '4140 Pre-Hard': '4140 Pre-Hard',
        '4140 Steel': '4140',  # Map to canonical name
        '12L14': '12L14',
        '1215': '1215',
        '1018': '1018',
        '1020': '1020',
        'A36': 'A36',
        'A36 ?': 'A36',  # Remove uncertainty
        'A36 HRS': 'A36',  # Remove condition reference
        'HR A36': 'A36',  # Remove hot rolled reference
        'A53': 'A36',  # Map pipe steel to structural steel
        'A108': 'CRS',  # Map to cold rolled steel
        'B7 Steel': 'A36',  # Map to structural steel
        'CRS': 'CRS',
        'HRS': 'HRS',
        '300M Alloy Steel': '300M',
        'A500': 'A500',
        'A513': 'A513',
        'RDS Steel': 'CRS',  # Map to cold rolled steel
        
        # Stainless Steel - Specific grades
        '304': '304',
        '304L': '304L',
        '304 Stainless': '304',  # Map to canonical name
        '304/304L Stainless': '304',  # Map to more common grade
        '316': '316',
        '316L': '316L',
        '316L Sch. 40': '316L',  # Remove schedule reference
        '321': '321',
        '321 Stainless': '321',  # Map to canonical name
        'RA330': 'RA330',
        'RA330 Stainless': 'RA330',  # Map to canonical name
        '410': '410',
        '410 Stainless': '410',  # Map to canonical name
        '440': '440',
        '440 Stainless': '440',  # Map to canonical name
        '15-5': '15-5',
        '15-5 Stainless': '15-5',  # Map to canonical name
        '17-4': '17-4',
        '17-4 PH': '17-4',  # Map to canonical name
        'A269': 'A269',
        'A269 Stainless': 'A269',  # Map to canonical name
        'T-304': 'T-304',
        'T-304 Stainless': 'T-304',  # Map to canonical name
        'T-304L': 'T-304',  # Map to T-304 (close enough)
        'T-316': 'T-316',
        'T-316 Stainless': 'T-316',  # Map to canonical name
        'T-304 Annealed': 'T-304 Annealed',
        'T-316 Annealed': 'T-316 Annealed',
        
        # Aluminum - Specific grades
        '6061-T6': '6061-T6',
        '6061 T6': '6061-T6',  # Normalize spacing
        '6061-T6511': '6061-T6511',
        '6063-T52': '6063-T52',
        
        # Brass - Specific grades
        'Brass 360': '360 Brass',
        'Brass 360-H02': '360 Brass',  # Map to canonical name
        'C23000 red brass': 'C23000',
        'Brass H58': 'H58 Brass',
        'Brass H58-330': 'H58 Brass',  # Map to canonical name
        'Brass C272': 'C272 Brass',
        'Brass C385-H02': 'C385 Brass',
        'Brass C693': 'C693 Brass',
        '353 Brass': '353 Brass',
        'Naval Brass': 'Naval Brass',
        
        # Copper - Specific grades
        'C10100 Copper': 'C10100',
        'Beryllium Copper TPE3': 'Beryllium Copper',
        
        # Tool Steel - Specific grades
        'O1 Tool Steel': 'O1',
        'A-2': 'A-2',
        'H11 Tool Steel': 'H11',
        'L6 Tool Steel': 'L6',
        
        # Other Metals
        '96% Nickel': '96% Nickel',
        
        # Additional materials that need specific classification
        'EMT': 'CRS',  # Electrical conduit, likely cold rolled steel
        'Zinc': 'Other Metals',  # Map to Other Metals category
        'Lead (99.9%)': 'Other Metals',  # Map to Other Metals category  
        'Hasteloy': 'Other Metals',  # Nickel-based superalloy
        'Inconel': 'Other Metals',  # Nickel-based superalloy
        'Vasco Max 350': 'Tool Steel',  # Map to Tool Steel category
        'Dura Bar Cast Iron': 'Other Metals',  # Map to Other Metals category
    }
    
    # Family-level mappings (Level 2) - when we know the subfamily but not exact grade
    family_mappings = {
        # These don't exist in current taxonomy but included for completeness
    }
    
    # Category-level mappings (Level 1) - when we only know general type
    category_mappings = {
        'Steel': 'Carbon Steel',
        'Stainless': 'Stainless Steel',
        'Stainless?': 'Stainless Steel',  # Remove uncertainty
        'Stainless??': 'Stainless Steel',  # Remove uncertainty  
        'Stainless Steel': 'Stainless Steel',
        'Stainless non-magnetic': 'Stainless Steel',  # Likely austenitic
        'Aluminum': 'Aluminum',
        'Brass': 'Brass',
        'Copper': 'Copper',
        'Bronze??': 'Bronze',  # Map to family level in Copper category
        'Tool Steel RC 35-40': 'Tool Steel',  # Generic tool steel
        'Mystery Steel': 'Carbon Steel',  # Most likely carbon steel
        'CRS mystery?': 'Carbon Steel',  # Remove uncertainty from CRS
    }
    
    # Handle Unknown materials - these need manual review
    unknown_mappings = {
        'Unknown': 'Unknown',  # Will need manual categorization
    }
    
    # Combine all mappings
    full_mapping = {}
    full_mapping.update(specific_mappings)
    full_mapping.update(family_mappings)
    full_mapping.update(category_mappings)
    full_mapping.update(unknown_mappings)
    
    return full_mapping


def is_rate_limit_error(exception):
    """Check if the exception is a rate limit error."""
    error_str = str(exception).lower()
    return ('rate limit' in error_str or 
            'quota exceeded' in error_str or 
            'requests per minute' in error_str or
            'httperror 429' in error_str)


def wait_for_rate_limit_reset(wait_time=65):
    """Wait for Google Sheets API rate limit to reset."""
    print(f"\n⏳ Rate limit reached. Waiting {wait_time} seconds for quota to reset...")
    for remaining in range(wait_time, 0, -1):
        print(f"\r   ⏱️  {remaining} seconds remaining...", end="", flush=True)
        time.sleep(1)
    print("\n✅ Quota reset! Continuing migration...")


def execute_migration_with_retry():
    """Execute the material migration with automatic rate limit handling."""
    
    print("🚀 Executing material migration with rate limit handling...")
    
    mapping = create_material_mapping()
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        from app.google_sheets_storage import GoogleSheetsStorage
        from app.inventory_service import InventoryService
        from config import Config
        
        storage = GoogleSheetsStorage(Config.GOOGLE_SHEET_ID)
        service = InventoryService(storage)
        
        # Track overall progress
        total_updated = 0
        total_unchanged = 0
        total_errors = 0
        total_processed = 0
        
        # Track rate limit cycles
        rate_limit_cycles = 0
        
        while True:
            try:
                # Get all items
                print(f"📊 Loading all inventory items...")
                items = service.get_all_items()
                
                if not items:
                    print("ℹ️  No items found or all items processed.")
                    break
                
                print(f"🔄 Processing {len(items)} items...")
                
                # Track changes for this cycle
                cycle_updated = 0
                cycle_unchanged = 0 
                cycle_errors = 0
                
                for i, item in enumerate(items):
                    original_material = item.material
                    
                    # Show progress every 10 items
                    if i % 10 == 0:
                        print(f"   Progress: {i+1}/{len(items)} items processed")
                    
                    if original_material in mapping:
                        new_material = mapping[original_material]
                        
                        if original_material != new_material:
                            # Update the item
                            item.material = new_material
                            
                            try:
                                result = service.update_item(item)
                                if result:
                                    cycle_updated += 1
                                    print(f"   ✅ {item.ja_id}: {original_material} → {new_material}")
                                else:
                                    cycle_errors += 1
                                    print(f"   ❌ Failed to update {item.ja_id}: {original_material}")
                            except Exception as e:
                                if is_rate_limit_error(e):
                                    print(f"\n🛑 Rate limit hit after processing {i+1} items")
                                    
                                    # Update totals for this cycle
                                    total_updated += cycle_updated
                                    total_unchanged += cycle_unchanged
                                    total_errors += cycle_errors
                                    total_processed += i + 1
                                    rate_limit_cycles += 1
                                    
                                    print(f"📊 Cycle {rate_limit_cycles} Results:")
                                    print(f"   Updated: {cycle_updated}")
                                    print(f"   Unchanged: {cycle_unchanged}")
                                    print(f"   Errors: {cycle_errors}")
                                    print(f"   Processed: {i + 1}")
                                    
                                    print(f"📈 Cumulative Results:")
                                    print(f"   Total Updated: {total_updated}")
                                    print(f"   Total Unchanged: {total_unchanged}")
                                    print(f"   Total Errors: {total_errors}")
                                    print(f"   Total Processed: {total_processed}")
                                    
                                    # Wait for rate limit to reset
                                    wait_for_rate_limit_reset()
                                    
                                    # Break inner loop to restart with fresh data
                                    raise Exception("Rate limit - restart cycle")
                                else:
                                    cycle_errors += 1
                                    print(f"   ❌ Error updating {item.ja_id}: {e}")
                        else:
                            cycle_unchanged += 1
                    else:
                        # Material not in mapping - skip
                        cycle_unchanged += 1
                
                # If we get here, we processed all items without hitting rate limit
                total_updated += cycle_updated
                total_unchanged += cycle_unchanged
                total_errors += cycle_errors
                total_processed += len(items)
                
                print(f"\n📊 Final Migration Results:")
                print(f"   Updated items: {total_updated}")
                print(f"   Unchanged items: {total_unchanged}")
                print(f"   Errors: {total_errors}")
                print(f"   Total processed: {total_processed}")
                print(f"   Rate limit cycles: {rate_limit_cycles}")
                
                # Successfully completed
                break
                
            except Exception as e:
                if "Rate limit - restart cycle" in str(e):
                    # This is expected - continue the outer loop
                    continue
                elif is_rate_limit_error(e):
                    print(f"\n🛑 Rate limit hit during setup")
                    wait_for_rate_limit_reset()
                    continue
                else:
                    print(f"❌ Unexpected error: {e}")
                    break
        
        if total_updated > 0:
            print("\n🎉 Migration completed successfully!")
            print("   Material column values now reference hierarchical taxonomy")
            print("   Users can select materials at appropriate specificity levels")
        
        return total_updated, total_unchanged, total_errors


def main():
    """Main migration workflow."""
    
    print("🔧 Material Migration Tool with Rate Limit Handling")
    print("=" * 60)
    print()
    print("This tool migrates existing Material column values to use")
    print("the new hierarchical taxonomy structure.")
    print("It automatically handles Google Sheets API rate limits.")
    print()
    
    # Execute migration with retry logic
    updated, unchanged, errors = execute_migration_with_retry()
    
    if errors > 0:
        print(f"\n⚠️  Migration completed with {errors} errors.")
        return False
    
    print(f"\n✅ Migration completed successfully!")
    print(f"   {updated} items updated to use hierarchical taxonomy")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)