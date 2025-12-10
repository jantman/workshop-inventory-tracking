"""refactor_photo_schema_for_many_to_many

Revision ID: 8213852b0b94
Revises: 56dc95692b79
Create Date: 2025-12-09 14:30:00.000000

"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.sql import table, column, select, insert, func

# revision identifiers, used by Alembic.
revision: str = '8213852b0b94'
down_revision: Union[str, None] = '56dc95692b79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Refactor photo schema from one-to-many to many-to-many relationship.

    This migration:
    1. Creates new `photos` table (stores photo data once)
    2. Creates new `item_photo_associations` table (many-to-many relationships)
    3. Migrates data from `item_photos` to new schema
    4. Verifies data integrity
    5. Drops old `item_photos` table
    """
    connection = op.get_bind()

    # Step 1: Create new `photos` table
    op.create_table(
        'photos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('thumbnail_data', sa.LargeBinary(), nullable=False),
        sa.Column('medium_data', sa.LargeBinary().with_variant(mysql.MEDIUMBLOB, 'mysql'), nullable=False),
        sa.Column('original_data', sa.LargeBinary().with_variant(mysql.MEDIUMBLOB, 'mysql'), nullable=False),
        sa.Column('sha256_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('file_size > 0', name='ck_photo_positive_file_size'),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')",
            name='ck_photo_valid_content_type'
        ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_photos_sha256_hash', 'photos', ['sha256_hash'], unique=False)

    # Step 2: Create new `item_photo_associations` table
    op.create_table(
        'item_photo_associations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ja_id', sa.String(length=10), nullable=False),
        sa.Column('photo_id', sa.Integer(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("ja_id REGEXP '^JA[0-9]{6}$'", name='ck_assoc_valid_ja_id'),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ja_id', 'photo_id', 'display_order', name='uk_ja_photo_order')
    )
    op.create_index('ix_item_photo_associations_ja_id', 'item_photo_associations', ['ja_id'], unique=False)
    op.create_index('ix_item_photo_associations_photo_id', 'item_photo_associations', ['photo_id'], unique=False)
    op.create_index('ix_item_photo_associations_ja_id_order', 'item_photo_associations', ['ja_id', 'display_order'], unique=False)

    # Step 3: Migrate existing data from item_photos to new schema
    print("Migrating existing photo data...")

    # Define table references for data migration
    item_photos = table(
        'item_photos',
        column('id', sa.Integer),
        column('ja_id', sa.String),
        column('filename', sa.String),
        column('content_type', sa.String),
        column('file_size', sa.Integer),
        column('thumbnail_data', sa.LargeBinary),
        column('medium_data', sa.LargeBinary),
        column('original_data', sa.LargeBinary),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    # Get all existing photos ordered by ja_id and created_at to preserve order
    existing_photos = connection.execute(
        select(item_photos).order_by(item_photos.c.ja_id, item_photos.c.created_at)
    ).fetchall()

    print(f"Found {len(existing_photos)} photos to migrate")

    # Migrate each photo
    for photo in existing_photos:
        # Insert into photos table
        result = connection.execute(
            insert(table('photos',
                column('filename', sa.String),
                column('content_type', sa.String),
                column('file_size', sa.Integer),
                column('thumbnail_data', sa.LargeBinary),
                column('medium_data', sa.LargeBinary),
                column('original_data', sa.LargeBinary),
                column('sha256_hash', sa.String),
                column('created_at', sa.DateTime),
                column('updated_at', sa.DateTime)
            )).values(
                filename=photo.filename,
                content_type=photo.content_type,
                file_size=photo.file_size,
                thumbnail_data=photo.thumbnail_data,
                medium_data=photo.medium_data,
                original_data=photo.original_data,
                sha256_hash=None,  # Will be populated on future uploads
                created_at=photo.created_at,
                updated_at=photo.updated_at
            )
        )

        # Get the new photo_id
        photo_id = result.inserted_primary_key[0]

        # Create association for this item
        # Calculate display_order based on position within this ja_id's photos
        display_order_query = select(func.count()).select_from(
            table('item_photo_associations')
        ).where(
            column('ja_id') == photo.ja_id
        )
        display_order = connection.execute(display_order_query).scalar()

        connection.execute(
            insert(table('item_photo_associations',
                column('ja_id', sa.String),
                column('photo_id', sa.Integer),
                column('display_order', sa.Integer),
                column('created_at', sa.DateTime)
            )).values(
                ja_id=photo.ja_id,
                photo_id=photo_id,
                display_order=display_order,
                created_at=photo.created_at
            )
        )

    # Step 4: Verify data integrity
    print("Verifying data migration...")

    old_count = connection.execute(select(func.count()).select_from(item_photos)).scalar()
    new_photos_count = connection.execute(
        select(func.count()).select_from(table('photos'))
    ).scalar()
    new_assoc_count = connection.execute(
        select(func.count()).select_from(table('item_photo_associations'))
    ).scalar()

    print(f"Old item_photos count: {old_count}")
    print(f"New photos count: {new_photos_count}")
    print(f"New associations count: {new_assoc_count}")

    if old_count != new_photos_count:
        raise Exception(f"Data migration failed: {old_count} photos in old table but {new_photos_count} in new table")

    if old_count != new_assoc_count:
        raise Exception(f"Data migration failed: {old_count} photos in old table but {new_assoc_count} associations created")

    print("Data integrity verified successfully!")

    # Step 5: Drop old item_photos table
    print("Dropping old item_photos table...")
    op.drop_index('ix_item_photos_created_at', table_name='item_photos')
    op.drop_index('ix_item_photos_ja_id', table_name='item_photos')
    op.drop_table('item_photos')

    print("Migration completed successfully!")


def downgrade() -> None:
    """
    Rollback the photo schema refactoring.

    This recreates the old item_photos table and migrates data back.
    WARNING: This will lose any photo sharing relationships created after the upgrade.
    """
    connection = op.get_bind()

    # Step 1: Recreate old item_photos table
    op.create_table(
        'item_photos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ja_id', sa.String(length=10), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('thumbnail_data', sa.LargeBinary(), nullable=False),
        sa.Column('medium_data', sa.LargeBinary().with_variant(mysql.MEDIUMBLOB, 'mysql'), nullable=False),
        sa.Column('original_data', sa.LargeBinary().with_variant(mysql.MEDIUMBLOB, 'mysql'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("ja_id REGEXP '^JA[0-9]{6}$'", name='ck_photo_valid_ja_id_format'),
        sa.CheckConstraint('file_size > 0', name='ck_photo_positive_file_size'),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')",
            name='ck_photo_valid_content_type'
        ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_item_photos_ja_id', 'item_photos', ['ja_id'], unique=False)
    op.create_index('ix_item_photos_created_at', 'item_photos', ['created_at'], unique=False)

    # Step 2: Migrate data back from new schema to old schema
    print("Rolling back photo data migration...")

    # Join associations with photos to get all data
    assoc_table = table('item_photo_associations',
        column('ja_id', sa.String),
        column('photo_id', sa.Integer),
        column('created_at', sa.DateTime)
    )
    photos_table = table('photos',
        column('id', sa.Integer),
        column('filename', sa.String),
        column('content_type', sa.String),
        column('file_size', sa.Integer),
        column('thumbnail_data', sa.LargeBinary),
        column('medium_data', sa.LargeBinary),
        column('original_data', sa.LargeBinary),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    # Get all associations with their photo data
    query = select(
        assoc_table.c.ja_id,
        photos_table.c.filename,
        photos_table.c.content_type,
        photos_table.c.file_size,
        photos_table.c.thumbnail_data,
        photos_table.c.medium_data,
        photos_table.c.original_data,
        assoc_table.c.created_at,
        photos_table.c.updated_at
    ).select_from(
        assoc_table.join(photos_table, assoc_table.c.photo_id == photos_table.c.id)
    ).order_by(assoc_table.c.ja_id, assoc_table.c.created_at)

    associations = connection.execute(query).fetchall()

    print(f"Found {len(associations)} associations to migrate back")

    # Insert each association as a separate photo record
    for assoc in associations:
        connection.execute(
            insert(table('item_photos',
                column('ja_id', sa.String),
                column('filename', sa.String),
                column('content_type', sa.String),
                column('file_size', sa.Integer),
                column('thumbnail_data', sa.LargeBinary),
                column('medium_data', sa.LargeBinary),
                column('original_data', sa.LargeBinary),
                column('created_at', sa.DateTime),
                column('updated_at', sa.DateTime)
            )).values(
                ja_id=assoc.ja_id,
                filename=assoc.filename,
                content_type=assoc.content_type,
                file_size=assoc.file_size,
                thumbnail_data=assoc.thumbnail_data,
                medium_data=assoc.medium_data,
                original_data=assoc.original_data,
                created_at=assoc.created_at,
                updated_at=assoc.updated_at
            )
        )

    print("Data rolled back successfully!")

    # Step 3: Drop new tables
    op.drop_index('ix_item_photo_associations_ja_id_order', table_name='item_photo_associations')
    op.drop_index('ix_item_photo_associations_photo_id', table_name='item_photo_associations')
    op.drop_index('ix_item_photo_associations_ja_id', table_name='item_photo_associations')
    op.drop_table('item_photo_associations')

    op.drop_index('ix_photos_sha256_hash', table_name='photos')
    op.drop_table('photos')

    print("Rollback completed successfully!")
