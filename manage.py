#!/usr/bin/env python
"""
Management script for Workshop Inventory Tracking application

Provides command-line interface for database migrations and other administrative tasks.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the application to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import click
from alembic import command
from alembic.config import Config
from config import Config as AppConfig


def get_alembic_config():
    """Get Alembic configuration"""
    alembic_cfg = Config("alembic.ini")
    database_url = os.environ.get('SQLALCHEMY_DATABASE_URI') or AppConfig.SQLALCHEMY_DATABASE_URI
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    return alembic_cfg


@click.group()
def cli():
    """Workshop Inventory Management Commands"""
    pass


@cli.group()
def db():
    """Database management commands"""
    pass


@db.command()
def init():
    """Initialize the database with all tables"""
    click.echo("Initializing database...")
    alembic_cfg = get_alembic_config()
    command.upgrade(alembic_cfg, "head")
    click.echo("Database initialized successfully!")


@db.command()
def upgrade():
    """Upgrade database to latest migration"""
    click.echo("Upgrading database...")
    alembic_cfg = get_alembic_config()
    command.upgrade(alembic_cfg, "head")
    click.echo("Database upgraded successfully!")


@db.command()
@click.argument('revision', default='head')
def downgrade(revision):
    """Downgrade database to specific revision"""
    click.echo(f"Downgrading database to {revision}...")
    alembic_cfg = get_alembic_config()
    command.downgrade(alembic_cfg, revision)
    click.echo("Database downgraded successfully!")


@db.command()
@click.option('-m', '--message', required=True, help='Migration message')
@click.option('--autogenerate/--no-autogenerate', default=True, help='Autogenerate migration from models')
def migrate(message, autogenerate):
    """Create a new migration"""
    click.echo(f"Creating new migration: {message}")
    alembic_cfg = get_alembic_config()
    if autogenerate:
        command.revision(alembic_cfg, message=message, autogenerate=True)
    else:
        command.revision(alembic_cfg, message=message)
    click.echo("Migration created successfully!")


@db.command()
def current():
    """Show current database revision"""
    alembic_cfg = get_alembic_config()
    command.current(alembic_cfg)


@db.command()
def history():
    """Show migration history"""
    alembic_cfg = get_alembic_config()
    command.history(alembic_cfg)


@db.command()
@click.confirmation_option(prompt='Are you sure you want to reset the database?')
def reset():
    """Reset database (downgrade to base then upgrade to head)"""
    click.echo("Resetting database...")
    alembic_cfg = get_alembic_config()
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    click.echo("Database reset successfully!")


@cli.group()
def photos():
    """Photo management commands"""
    pass


@photos.command()
@click.option('--dry-run', is_flag=True, help='Show what would be processed without making changes')
def regenerate_pdf_thumbnails(dry_run):
    """Regenerate thumbnails for existing PDF photos"""
    from datetime import datetime
    
    click.echo("PDF Thumbnail Regeneration")
    click.echo("=" * 40)
    click.echo(f"Started at: {datetime.now()}")
    click.echo()
    
    try:
        from app.photo_service import PhotoService
        from app.database import ItemPhoto
        
        # Initialize PhotoService
        with PhotoService() as photo_service:
            if dry_run:
                click.echo("DRY RUN MODE - No changes will be made")
                click.echo()
                
                # Find PDFs that need thumbnail regeneration
                pdf_photos = photo_service.session.query(ItemPhoto).filter(
                    ItemPhoto.content_type == 'application/pdf'
                ).all()
                
                needs_update = []
                for photo in pdf_photos:
                    if photo.thumbnail_data and photo.thumbnail_data.startswith(b'%PDF'):
                        needs_update.append(photo)
                
                click.echo(f"Found {len(pdf_photos)} total PDF photos")
                click.echo(f"Found {len(needs_update)} PDF photos that need thumbnail regeneration")
                click.echo()
                
                if needs_update:
                    click.echo("Photos that would be processed:")
                    for photo in needs_update[:10]:  # Show first 10
                        click.echo(f"  - {photo.filename} (ID: {photo.id}, JA ID: {photo.ja_id})")
                    if len(needs_update) > 10:
                        click.echo(f"  ... and {len(needs_update) - 10} more")
                    click.echo()
                    click.echo("To actually regenerate thumbnails, run without --dry-run")
                else:
                    click.echo("No PDF photos need thumbnail regeneration.")
                    
            else:
                click.echo("PROCESSING MODE - Making changes")
                click.echo()
                
                updated_count = photo_service.regenerate_pdf_thumbnails()
                
                click.echo()
                click.echo(f"Successfully regenerated thumbnails for {updated_count} PDF photos")
        
        click.echo()
        click.echo(f"Completed at: {datetime.now()}")
        
    except ImportError as e:
        click.echo(f"Error importing required modules: {e}")
        click.echo("Make sure all dependencies are installed")
        sys.exit(1)
        
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.group()
def audit():
    """Data integrity audit commands"""
    pass


@audit.command()
def materials():
    """Audit items with materials not in the taxonomy"""
    click.echo("Auditing materials...")

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.database import InventoryItem, MaterialTaxonomy

        # Get database connection
        database_url = os.environ.get('SQLALCHEMY_DATABASE_URI') or AppConfig.SQLALCHEMY_DATABASE_URI
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # Get all valid materials from taxonomy (level 3)
            valid_materials = set()
            taxonomy_materials = session.query(MaterialTaxonomy).filter(
                MaterialTaxonomy.level == 3,
                MaterialTaxonomy.active == True
            ).all()

            for material in taxonomy_materials:
                valid_materials.add(material.name)
                # Add aliases if they exist
                if material.aliases:
                    aliases = [alias.strip() for alias in material.aliases.split(',') if alias.strip()]
                    valid_materials.update(aliases)

            # Get all unique materials from inventory items
            used_materials = session.query(InventoryItem.material).filter(
                InventoryItem.active == True
            ).distinct().all()

            # Find materials not in taxonomy
            invalid_materials = []
            for (material,) in used_materials:
                if material and material not in valid_materials:
                    # Count how many items use this material
                    count = session.query(InventoryItem).filter(
                        InventoryItem.active == True,
                        InventoryItem.material == material
                    ).count()
                    invalid_materials.append((material, count))

            # Display results
            if invalid_materials:
                click.echo(f"\nFound {len(invalid_materials)} materials not in taxonomy:")
                click.echo("=" * 60)

                # Sort by count (descending) then by name
                invalid_materials.sort(key=lambda x: (-x[1], x[0]))

                for material, count in invalid_materials:
                    click.echo(f"  {material:<40} ({count} items)")

                click.echo("=" * 60)
                click.echo(f"Total items with invalid materials: {sum(count for _, count in invalid_materials)}")
            else:
                click.echo("✓ All materials in inventory are present in the taxonomy")

        finally:
            session.close()

    except ImportError as e:
        click.echo(f"Error importing required modules: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error during audit: {e}")
        sys.exit(1)


@audit.command()
def locations():
    """Generate a report of all locations and sub-locations with their items"""
    click.echo("Generating locations report...")

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.database import InventoryItem
        from collections import defaultdict, OrderedDict

        # Get database connection
        database_url = os.environ.get('SQLALCHEMY_DATABASE_URI') or AppConfig.SQLALCHEMY_DATABASE_URI
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        session = Session()

        try:
            # Get all active inventory items with location information
            items = session.query(InventoryItem).filter(
                InventoryItem.active == True
            ).order_by(
                InventoryItem.location.asc(),
                InventoryItem.sub_location.asc(),
                InventoryItem.ja_id.asc()
            ).all()

            # Group items by location and sub-location
            locations = defaultdict(lambda: defaultdict(list))

            for item in items:
                location = item.location or "No Location"
                sub_location = item.sub_location or "No Sub-location"
                locations[location][sub_location].append(item)

            # Display results
            total_locations = len(locations)
            total_items = len(items)

            click.echo(f"\nLocation Report")
            click.echo("=" * 80)
            click.echo(f"Total locations: {total_locations}")
            click.echo(f"Total items: {total_items}")
            click.echo("=" * 80)

            # Sort locations alphabetically, but put "No Location" last
            sorted_locations = sorted(locations.keys())
            if "No Location" in sorted_locations:
                sorted_locations.remove("No Location")
                sorted_locations.append("No Location")

            for location in sorted_locations:
                sub_locations = locations[location]
                location_item_count = sum(len(items) for items in sub_locations.values())

                click.echo(f"\n📍 {location} ({location_item_count} items)")
                click.echo("-" * 60)

                # Sort sub-locations alphabetically, but put "No Sub-location" last
                sorted_sub_locations = sorted(sub_locations.keys())
                if "No Sub-location" in sorted_sub_locations:
                    sorted_sub_locations.remove("No Sub-location")
                    sorted_sub_locations.append("No Sub-location")

                for sub_location in sorted_sub_locations:
                    items_in_subloc = sub_locations[sub_location]
                    click.echo(f"  📂 {sub_location} ({len(items_in_subloc)} items)")

                    for item in items_in_subloc:
                        # Format item description
                        desc_parts = [item.material]
                        if item.item_type:
                            desc_parts.append(item.item_type)
                        if item.shape:
                            desc_parts.append(item.shape)

                        # Add dimensions if available
                        dims = []
                        if item.length:
                            dims.append(f"L:{item.length}")
                        if item.width:
                            dims.append(f"W:{item.width}")
                        if item.thickness:
                            dims.append(f"T:{item.thickness}")
                        if item.wall_thickness:
                            dims.append(f"WT:{item.wall_thickness}")

                        if dims:
                            desc_parts.append(f"({', '.join(dims)})")

                        description = " ".join(desc_parts)

                        # Truncate description if too long
                        if len(description) > 60:
                            description = description[:57] + "..."

                        click.echo(f"    {item.ja_id:<10} {description}")

            click.echo("\n" + "=" * 80)
            click.echo("Report complete")

        finally:
            session.close()

    except ImportError as e:
        click.echo(f"Error importing required modules: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error during audit: {e}")
        sys.exit(1)


@cli.command()
def config_check():
    """Check application configuration"""
    click.echo("Checking configuration...")

    errors = AppConfig.validate_config()
    if errors:
        click.echo("Configuration errors found:")
        for error in errors:
            click.echo(f"  - {error}")
        sys.exit(1)
    else:
        click.echo("Configuration is valid!")

    # Test database connection
    try:
        from sqlalchemy import create_engine
        database_url = os.environ.get('SQLALCHEMY_DATABASE_URI') or AppConfig.SQLALCHEMY_DATABASE_URI
        engine = create_engine(database_url)

        # Test connection
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        click.echo("Database connection: OK")

    except Exception as e:
        click.echo(f"Database connection failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    cli()