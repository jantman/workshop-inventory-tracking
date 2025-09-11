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