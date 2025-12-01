"""Remove quantity field and split multi-quantity items

Revision ID: 56dc95692b79
Revises: e4f344204264
Create Date: 2025-12-01 17:50:05.511853

"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.sql import table, column, select, insert, update

# revision identifiers, used by Alembic.
revision: str = '56dc95692b79'
down_revision: Union[str, None] = 'e4f344204264'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade database schema:
    1. Split items with quantity > 1 into individual items
    2. Drop the quantity column
    """

    # Get database connection
    conn = op.get_bind()

    # Define table structure for querying
    inventory_items = table('inventory_items',
        column('id', sa.Integer),
        column('ja_id', sa.String),
        column('active', sa.Boolean),
        column('length', sa.Numeric),
        column('width', sa.Numeric),
        column('thickness', sa.Numeric),
        column('wall_thickness', sa.Numeric),
        column('weight', sa.Numeric),
        column('item_type', sa.String),
        column('shape', sa.String),
        column('material', sa.String),
        column('thread_series', sa.String),
        column('thread_handedness', sa.String),
        column('thread_size', sa.String),
        column('quantity', sa.Integer),
        column('location', sa.String),
        column('sub_location', sa.String),
        column('purchase_date', sa.DateTime),
        column('purchase_price', sa.Numeric),
        column('purchase_location', sa.String),
        column('notes', sa.Text),
        column('vendor', sa.String),
        column('vendor_part', sa.String),
        column('original_material', sa.String),
        column('original_thread', sa.String),
        column('precision', sa.Boolean),
        column('date_added', sa.DateTime),
        column('last_modified', sa.DateTime),
    )

    print("\n" + "="*80)
    print("MIGRATION: Remove quantity field and split multi-quantity items")
    print("="*80)

    # Step 1: Find items with quantity > 1
    items_to_split = conn.execute(
        select(inventory_items).where(inventory_items.c.quantity > 1).order_by(inventory_items.c.ja_id)
    ).fetchall()

    if not items_to_split:
        print("No items with quantity > 1 found. Skipping split operation.")
    else:
        print(f"\nFound {len(items_to_split)} items with quantity > 1:")
        for item in items_to_split:
            print(f"  - {item.ja_id}: quantity={item.quantity}, material={item.material}")

        # Step 2: Get current max JA ID to generate new sequential IDs
        max_ja_id_result = conn.execute(
            sa.text("SELECT ja_id FROM inventory_items ORDER BY ja_id DESC LIMIT 1")
        ).fetchone()

        if max_ja_id_result:
            max_ja_id = max_ja_id_result[0]
            # Extract numeric part (e.g., "JA000123" -> 123)
            max_num = int(max_ja_id[2:])
        else:
            max_num = 0

        next_num = max_num + 1

        print(f"\nStarting JA ID generation from: JA{next_num:06d}")
        print("\nSplitting items:")

        total_new_items = 0

        # Step 3: For each item with quantity > 1, create duplicates
        for item in items_to_split:
            original_ja_id = item.ja_id
            original_quantity = item.quantity
            duplicates_needed = original_quantity - 1  # Keep original, create N-1 copies

            print(f"\n  Processing {original_ja_id} (quantity={original_quantity}):")

            # Create duplicates
            new_ja_ids = []
            for i in range(duplicates_needed):
                new_ja_id = f"JA{next_num:06d}"
                new_ja_ids.append(new_ja_id)
                next_num += 1

                # Prepare notes with migration information
                original_notes = item.notes or ""
                migration_note = f"This item was created via database migration as a duplicate of {original_ja_id} with an original quantity of {original_quantity}."
                new_notes = f"{original_notes}\n\n{migration_note}" if original_notes else migration_note

                # Insert new item
                conn.execute(
                    insert(inventory_items).values(
                        ja_id=new_ja_id,
                        active=item.active,
                        length=item.length,
                        width=item.width,
                        thickness=item.thickness,
                        wall_thickness=item.wall_thickness,
                        weight=item.weight,
                        item_type=item.item_type,
                        shape=item.shape,
                        material=item.material,
                        thread_series=item.thread_series,
                        thread_handedness=item.thread_handedness,
                        thread_size=item.thread_size,
                        quantity=1,  # Each duplicate has quantity=1
                        location=item.location,
                        sub_location=item.sub_location,
                        purchase_date=item.purchase_date,
                        purchase_price=item.purchase_price,
                        purchase_location=item.purchase_location,
                        notes=new_notes,
                        vendor=item.vendor,
                        vendor_part=item.vendor_part,
                        original_material=item.original_material,
                        original_thread=item.original_thread,
                        precision=item.precision,
                        date_added=datetime.now(timezone.utc),
                        last_modified=datetime.now(timezone.utc),
                    )
                )

                total_new_items += 1

            print(f"    Created {duplicates_needed} duplicates: {', '.join(new_ja_ids)}")

            # Update original item to quantity=1
            conn.execute(
                update(inventory_items).
                where(inventory_items.c.id == item.id).
                values(quantity=1)
            )
            print(f"    Updated {original_ja_id} to quantity=1")

        print(f"\n{'='*80}")
        print(f"SUMMARY: Created {total_new_items} new items from {len(items_to_split)} multi-quantity items")
        print(f"{'='*80}\n")

    # Step 4: Now drop the quantity column (auto-generated code)
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('inventory_items', 'quantity')
    op.alter_column('item_photos', 'thumbnail_data',
               existing_type=mysql.MEDIUMBLOB(),
               type_=sa.LargeBinary(),
               existing_nullable=False)
    op.alter_column('item_photos', 'medium_data',
               existing_type=mysql.MEDIUMBLOB(),
               type_=sa.LargeBinary(),
               existing_nullable=False)
    op.alter_column('item_photos', 'original_data',
               existing_type=mysql.MEDIUMBLOB(),
               type_=sa.LargeBinary(),
               existing_nullable=False)
    # ### end Alembic commands ###

    print("Migration completed successfully!\n")


def downgrade() -> None:
    """
    Downgrade database schema:
    WARNING: This downgrade re-adds the quantity column but CANNOT reverse
    the item splitting operation. All items will have quantity=1 after downgrade.
    Downgrading this migration will result in data loss (split items remain split).
    """

    print("\n" + "="*80)
    print("WARNING: Downgrading migration - Remove quantity field")
    print("="*80)
    print("This downgrade re-adds the quantity column with default value 1.")
    print("It CANNOT reverse the item splitting operation.")
    print("Items that were split will remain as separate items with quantity=1.")
    print("="*80 + "\n")

    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('item_photos', 'original_data',
               existing_type=sa.LargeBinary(),
               type_=mysql.MEDIUMBLOB(),
               existing_nullable=False)
    op.alter_column('item_photos', 'medium_data',
               existing_type=sa.LargeBinary(),
               type_=mysql.MEDIUMBLOB(),
               existing_nullable=False)
    op.alter_column('item_photos', 'thumbnail_data',
               existing_type=sa.LargeBinary(),
               type_=mysql.MEDIUMBLOB(),
               existing_nullable=False)
    op.add_column('inventory_items', sa.Column('quantity', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False, server_default='1'))
    # ### end Alembic commands ###

    print("Downgrade completed. All items now have quantity=1.\n")
