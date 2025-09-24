#!/usr/bin/env python3
"""
Management script to regenerate PDF thumbnails for existing photos

This script is useful when upgrading from a version without PDF thumbnail generation
to one with PDF thumbnail generation. It will process all existing PDF photos and
generate proper JPEG thumbnails for them.

Usage:
    python3 regenerate_pdf_thumbnails.py [--dry-run]
    
Options:
    --dry-run    Show what would be processed without making changes
"""

import sys
import os
import argparse
from datetime import datetime

# Add the app directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser(description='Regenerate PDF thumbnails for existing photos')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be processed without making changes')
    args = parser.parse_args()
    
    try:
        from app.photo_service import PhotoService
        from app.database import ItemPhoto
        from config import Config
        
        print("PDF Thumbnail Regeneration Tool")
        print("=" * 40)
        print(f"Started at: {datetime.now()}")
        print()
        
        # Initialize PhotoService
        with PhotoService() as photo_service:
            if args.dry_run:
                print("DRY RUN MODE - No changes will be made")
                print()
                
                # Find PDFs that need thumbnail regeneration
                pdf_photos = photo_service.session.query(ItemPhoto).filter(
                    ItemPhoto.content_type == 'application/pdf'
                ).all()
                
                needs_update = []
                for photo in pdf_photos:
                    if photo.thumbnail_data and photo.thumbnail_data.startswith(b'%PDF'):
                        needs_update.append(photo)
                
                print(f"Found {len(pdf_photos)} total PDF photos")
                print(f"Found {len(needs_update)} PDF photos that need thumbnail regeneration")
                print()
                
                if needs_update:
                    print("Photos that would be processed:")
                    for photo in needs_update[:10]:  # Show first 10
                        print(f"  - {photo.filename} (ID: {photo.id}, JA ID: {photo.ja_id})")
                    if len(needs_update) > 10:
                        print(f"  ... and {len(needs_update) - 10} more")
                    print()
                    print("To actually regenerate thumbnails, run without --dry-run")
                else:
                    print("No PDF photos need thumbnail regeneration.")
                
            else:
                print("PROCESSING MODE - Making changes")
                print()
                
                updated_count = photo_service.regenerate_pdf_thumbnails()
                
                print()
                print(f"Successfully regenerated thumbnails for {updated_count} PDF photos")
        
        print()
        print(f"Completed at: {datetime.now()}")
        
    except ImportError as e:
        print(f"Error importing required modules: {e}")
        print("Make sure you're running this from the application root directory")
        return 1
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())